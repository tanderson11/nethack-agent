import aicrowd_gym
import numpy as np

from collections.abc import Iterable

import environment

def log_new_run(batch_number, env):
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
        if environment.env.debug:
            [env.unwrapped.seed(None, None, False) for env in self.envs]
        self.num_actions = self.envs[0].action_space.n

    def batch_step(self, actions):
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
                if environment.env.debug:
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
        # [env.unwrapped.seed(core=1723886515033083678, disp=8907974946124747376, reseed=False) for env in self.envs]
        observation = [env.reset() for env in self.envs]
        [log_new_run(i, env) for i, env in enumerate(self.envs)]
        return observation


if __name__ == '__main__':

    num_envs = 4
    batched_env = BatchedEnv(
        env_make_fn=lambda:aicrowd_gym.make('NetHackChallenge-v0'), 
        num_envs=4
    )
    
    observations = batched_env.batch_reset()
    num_actions = batched_env.envs[0].action_space.n
    for _ in range(50):
        actions = np.random.randint(num_actions, size=num_envs)
        observations, rewards, dones, infos = batched_env.batch_step(actions)
        for done_idx in np.where(dones)[0]:
            observations[done_idx] = batched_env.single_env_reset(done_idx) 
