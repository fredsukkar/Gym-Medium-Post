import gym
import numpy as np
import math
import pybullet as p
from simple_driving.resources.car import Car
from simple_driving.resources.plane import Plane
from simple_driving.resources.goal import Goal
import matplotlib.pyplot as plt
import time

RENDER_HEIGHT = 720
RENDER_WIDTH = 960

class SimpleDrivingEnv(gym.Env):
    metadata = {'render.modes': ['human', 'fp_camera', 'tp_camera']}

    def __init__(self, isDiscrete=True, renders=False):
        if (isDiscrete):
            self.action_space = gym.spaces.Discrete(9)
        else:
            self.action_space = gym.spaces.box.Box(
                low=np.array([-1, -.6], dtype=np.float32),
                high=np.array([1, .6], dtype=np.float32))
        self.observation_space = gym.spaces.box.Box(
            low=np.array([-40, -40, -1, -1, -5, -5, -10, -10], dtype=np.float32),
            high=np.array([40, 40, 1, 1, 5, 5, 10, 10], dtype=np.float32))
        self.np_random, _ = gym.utils.seeding.np_random()


        if renders:
            self.client = p.connect(p.GUI)
        else:
            self.client = p.connect(p.DIRECT)
        # Reduce length of episodes for RL algorithms

        self.reached_goal = False
        self._timeStep = 0.01
        self._actionRepeat = 50
        self._renders = renders
        self._isDiscrete = isDiscrete
        self.car = None
        self.goal_object = None
        self.goal = None
        self.done = False
        self.prev_dist_to_goal = None
        self.rendered_img = None
        self.render_rot_matrix = None
        self.reset()
        self._envStepCounter = 0

    def step(self, action):
        # Feed action to the car and get observation of car's state
        if (self._isDiscrete):
            fwd = [-1, -1, -1, 0, 0, 0, 1, 1, 1]
            steerings = [-0.6, 0, 0.6, -0.6, 0, 0.6, -0.6, 0, 0.6]
            throttle = fwd[action]
            steering_angle = steerings[action]
            action = [throttle, steering_angle]
        self.car.apply_action(action)
        for i in range(self._actionRepeat):
          p.stepSimulation()
          if self._renders:
            time.sleep(self._timeStep)

          carpos, carorn = p.getBasePositionAndOrientation(self.car.car)
          ballpos, ballorn = p.getBasePositionAndOrientation(self.goal_object.goal)
          car_ob = self.getExtendedObservation()

          if self._termination():
            self.done = True
            break
          self._envStepCounter += 1

        # Compute reward as L2 change in distance to goal
        # dist_to_goal = math.sqrt(((car_ob[0] - self.goal[0]) ** 2 +
                                  # (car_ob[1] - self.goal[1]) ** 2))
        dist_to_goal = math.sqrt(((carpos[0] - ballpos[0]) ** 2 +
                                  (carpos[1] - ballpos[1]) ** 2))
        # reward = max(self.prev_dist_to_goal - dist_to_goal, 0)
        reward = -dist_to_goal
        self.prev_dist_to_goal = dist_to_goal

        # Done by running off boundaries
        # if (carpos[0] >= 10 or carpos[0] <= -10 or
        #         carpos[1] >= 10 or carpos[1] <= -10):
        #     self.done = True
        # Done by reaching goal
        # elif dist_to_goal < 0.5 and not self.reached_goal:
        #     print("reached goal")
        #     # self.done = True
        #     self.reached_goal = True
        #     reward = 50

        ob = car_ob
        return ob, reward, self.done, dict()

    def seed(self, seed=None):
        self.np_random, seed = gym.utils.seeding.np_random(seed)
        return [seed]

    def reset(self):
        p.resetSimulation(self.client)
        p.setTimeStep(self._timeStep, self.client)
        p.setGravity(0, 0, -10)
        # Reload the plane and car
        Plane(self.client)
        self.car = Car(self.client)
        self._envStepCounter = 0

        # Set the goal to a random target
        x = (self.np_random.uniform(5, 9) if self.np_random.integers(2) else
             self.np_random.uniform(-9, -5))
        y = (self.np_random.uniform(5, 9) if self.np_random.integers(2) else
             self.np_random.uniform(-9, -5))
        self.goal = (x, y)
        self.done = False
        self.reached_goal = False

        # Visual element of the goal
        self.goal_object = Goal(self.client, self.goal)

        # Get observation to return
        carpos = self.car.get_observation()

        self.prev_dist_to_goal = math.sqrt(((carpos[0] - self.goal[0]) ** 2 +
                                           (carpos[1] - self.goal[1]) ** 2))
        car_ob = self.getExtendedObservation()
        return np.array(car_ob, dtype=np.float32)

    def render(self, mode='human'):
        if mode == "fp_camera":
            # Base information
            car_id, client_id = self.car.get_ids()
            proj_matrix = p.computeProjectionMatrixFOV(fov=80, aspect=1,
                                                       nearVal=0.01, farVal=100)
            pos, ori = [list(l) for l in
                        p.getBasePositionAndOrientation(car_id, client_id)]
            pos[2] = 0.2

            # Rotate camera direction
            rot_mat = np.array(p.getMatrixFromQuaternion(ori)).reshape(3, 3)
            camera_vec = np.matmul(rot_mat, [1, 0, 0])
            up_vec = np.matmul(rot_mat, np.array([0, 0, 1]))
            view_matrix = p.computeViewMatrix(pos, pos + camera_vec, up_vec)

            # Display image
            # frame = p.getCameraImage(100, 100, view_matrix, proj_matrix)[2]
            # frame = np.reshape(frame, (100, 100, 4))
            (_, _, px, _, _) = p.getCameraImage(width=RENDER_WIDTH,
                                                      height=RENDER_HEIGHT,
                                                      viewMatrix=view_matrix,
                                                      projectionMatrix=proj_matrix,
                                                      renderer=p.ER_BULLET_HARDWARE_OPENGL)
            frame = np.array(px)
            frame = frame[:, :, :3]
            return frame
            # self.rendered_img.set_data(frame)
            # plt.draw()
            # plt.pause(.00001)

        elif mode == "tp_camera":
            car_id, client_id = self.car.get_ids()
            base_pos, orn = p.getBasePositionAndOrientation(car_id, client_id)
            view_matrix = p.computeViewMatrixFromYawPitchRoll(cameraTargetPosition=base_pos,
                                                                    distance=20.0,
                                                                    yaw=40.0,
                                                                    pitch=-35,
                                                                    roll=0,
                                                                    upAxisIndex=2)
            proj_matrix = p.computeProjectionMatrixFOV(fov=60,
                                                             aspect=float(RENDER_WIDTH) / RENDER_HEIGHT,
                                                             nearVal=0.1,
                                                             farVal=100.0)
            (_, _, px, _, _) = p.getCameraImage(width=RENDER_WIDTH,
                                                      height=RENDER_HEIGHT,
                                                      viewMatrix=view_matrix,
                                                      projectionMatrix=proj_matrix,
                                                      renderer=p.ER_BULLET_HARDWARE_OPENGL)
            frame = np.array(px)
            frame = frame[:, :, :3]
            return frame
        else:
            return np.array([])

    def getExtendedObservation(self):
        # self._observation = []  #self._racecar.getObservation()
        carpos, carorn = p.getBasePositionAndOrientation(self.car.car)
        ballpos, ballorn = p.getBasePositionAndOrientation(self.goal_object.goal)
        invCarPos, invCarOrn = p.invertTransform(carpos, carorn)
        ballPosInCar, ballOrnInCar = p.multiplyTransforms(invCarPos, invCarOrn, ballpos, ballorn)

        observation = [ballPosInCar[0], ballPosInCar[1]]
        return observation

    def _termination(self):
        return self._envStepCounter > 1500

    def close(self):
        p.disconnect(self.client)