import aicrowd_gym
import numpy as np

from collections.abc import Iterable

import environment

def log_new_run(batch_number, env):
    if not (environment.env.print_seed or environment.env.debug): return
    env = env.unwrapped
    core_seed, disp_seed, reseed = env.get_seeds()
    print(f"[{batch_number} {env._episode} {reseed} {core_seed} {disp_seed}] Starting run.")

class BatchedEnv:
    def __init__(self, env_make_fn, num_envs=32):
        """
        Creates multiple copies of the environment with the same env_make_fn function
        """
        self.num_envs = num_envs
        self.envs = [env_make_fn() for _ in range(self.num_envs)]
        if environment.env.print_seed or environment.env.debug:
            [env.unwrapped.seed(None, None, False) for env in self.envs]
        self.num_actions = self.envs[0].action_space.n

    def apply_batch_actions(self, actions):
        """
        Applies each action to each env in the same order as self.envs
        Actions should be iterable and have the same length as self.envs
        Returns lists of obsevations, rewards, dones, infos
        """
        assert isinstance(
            actions, Iterable), f"actions with type {type(actions)} is not iterable"
        assert len(
            actions) == self.num_envs, f"actions has length {len(actions)} which different from num_envs"

        observations, rewards, dones, infos = [], [], [], []
        for i, env, a in zip(range(len(self.envs)), self.envs, actions):
            observation, reward, done, info = env.step(a)
            if done:
                if environment.env.debug or environment.env.print_seed:
                    env.unwrapped.seed(None, None, False)
                observation = env.reset()
                log_new_run(i, env)
            observations.append(observation)
            rewards.append(reward)
            dones.append(done)
            infos.append(info)

        return observations, rewards, dones, infos

    def batch_reset(self):
        """
        Resets all the environments in self.envs
        """
        [env.unwrapped.seed(core=1920827579925652853, disp=73832244036727981, reseed=False) for env in self.envs]
        observation = [env.reset() for env in self.envs]
        [log_new_run(i, env) for i, env in enumerate(self.envs)]
        return observation
