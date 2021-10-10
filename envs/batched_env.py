import csv
import os

from collections.abc import Iterable
import pandas as pd

import environment

def log_new_run(env):
    if not (environment.env.print_seed or environment.env.debug): return
    env = env.unwrapped
    core_seed, disp_seed, reseed = env.get_seeds()
    print(f"[{env._episode} {reseed} {core_seed} {disp_seed}] Starting run.")

class BatchedEnv:
    def __init__(self, env_make_fn, num_envs=32):
        """
        Creates multiple copies of the environment with the same env_make_fn function
        """
        self.seeds = []
        if environment.env.use_seed_whitelist:
            with open(os.path.join(os.path.dirname(__file__), "..", "seeded_runs", "seed_whitelist.csv"), newline='') as csvfile:
                seed_reader = csv.reader(csvfile, delimiter=',', quotechar='"')
                for i, row in enumerate(seed_reader):
                    if i == 0:
                        assert row[0] == 'core'
                        assert row[1] == 'display'
                        continue
                    self.seeds.append((int(row[0]), int(row[1])))
        # If you want to manually try a single seed
        #self.seeds = [(1520908004125923785, 3165386160974918246)]
        self.num_envs = num_envs
        self.env_make_fn = env_make_fn
        self.envs = []
        self.initial_observations = []
        for _ in range(self.num_envs):
            env, observation = self.make_environment()
            self.envs.append(env)
            self.initial_observations.append(observation)
        self.num_actions = self.envs[0].action_space.n

    def next_seed(self):
        if not self.seeds:
            return None
        return self.seeds.pop(0)

    def make_environment(self):
        env = self.env_make_fn()
        observation = self.reset_environment(env)
        return env, observation

    def reset_environment(self, env):
        next_seed = self.next_seed()
        if next_seed:
            env.unwrapped.seed(next_seed[0], next_seed[1], False)
        else:
            if environment.env.use_seed_whitelist:
                print("Ran out of seeds!")
            if environment.env.debug or environment.env.print_seed:
                env.unwrapped.seed(None, None, False)

        observation = env.reset()
        log_new_run(env)
        return observation

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
                observation = self.reset_environment(env)
            observations.append(observation)
            rewards.append(reward)
            dones.append(done)
            infos.append(info)

        return observations, rewards, dones, infos
