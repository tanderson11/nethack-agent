## This file is intended to emulate the evaluation on AIcrowd

# IMPORTANT - Differences to expect
# * All the environment's functions are not available
# * The run might be slower than your local run
# * Resources might vary from your local machine

import numpy as np
import pandas as pd
import os

from submission_config import SubmissionConfig, TestEvaluationConfig

from rollout import run_batched_rollout
from envs.batched_env import BatchedEnv

import environment
import parse_ttyrec

def evaluate():
    env_make_fn = SubmissionConfig.MAKE_ENV_FN
    num_envs = SubmissionConfig.NUM_ENVIRONMENTS
    Agent = SubmissionConfig.AGENT

    num_episodes = TestEvaluationConfig.NUM_EPISODES

    batched_env = BatchedEnv(env_make_fn=env_make_fn, num_envs=num_envs)

    agent = Agent(num_envs, batched_env.num_actions, batched_env.envs if environment.env.debug else None)

    ascensions, scores = run_batched_rollout(num_episodes, batched_env, agent)
    print(
        f"Ascensions: {ascensions} "
        f"Median Score: {np.median(scores)}, "
        f"Mean Score: {np.mean(scores)}"
    )

    if environment.env.debug:
        return batched_env.envs[0].savedir


if __name__ == "__main__":
    path = evaluate()

    if path is not None:
        files = [os.path.join(path,f) for f in os.listdir(path) if os.path.isfile(os.path.join(path,f)) and f.endswith('.ttyrec.bz2')]
        for f in files:
            if f.endswith('{}.ttyrec.bz2'.format(environment.env.num_episodes)): # rm this junk file
                print("Removing {}".format(f))
                os.remove(f)
        outpath = os.path.join(path, "deaths.csv")
        score_df = parse_ttyrec.parse_dir(path, outpath=outpath)

        log_df = pd.read_csv(os.path.join(path, "log.csv"))
        df = score_df.join(log_df, rsuffix='_log')

        with open(os.path.join(path, "joint_log.csv"), 'w') as f:
            df.to_csv(f)