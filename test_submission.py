## This file is intended to emulate the evaluation on AIcrowd

# IMPORTANT - Differences to expect
# * All the environment's functions are not available
# * The run might be slower than your local run
# * Resources might vary from your local machine

from typing import NamedTuple, List
from dataclasses import dataclass
from multiprocessing import Process, Queue
import os
import queue
import time

import numpy as np
import pandas as pd

from submission_config import SubmissionConfig, TestEvaluationConfig

from rollout import run_batched_rollout
from envs.batched_env import BatchedEnv

import environment
import parse_ttyrec

class RolloutResults(NamedTuple):
    ascensions: int
    scores: List[int]
    log_paths: str

def evaluate(id, num_episodes=TestEvaluationConfig.NUM_EPISODES, runner_queue=None):
    env_make_fn = SubmissionConfig.MAKE_ENV_FN
    num_envs = SubmissionConfig.NUM_ENVIRONMENTS
    Agent = SubmissionConfig.AGENT

    batched_env = BatchedEnv(env_make_fn=env_make_fn, num_envs=num_envs)

    agent = Agent(num_envs, batched_env.num_actions, batched_env.envs if environment.env.log_runs else None)

    ascensions, scores = run_batched_rollout(num_episodes, batched_env, agent)

    log_paths = []
    if environment.env.log_runs:
        log_paths.append(batched_env.envs[0].savedir)

    results = RolloutResults(
        ascensions=ascensions,
        scores=scores,
        log_paths=log_paths,
    )

    if runner_queue:
        runner_queue.put(results)

    return results

@dataclass
class Runner:
    id: int
    process: Process
    queue: Queue
    done: bool = False

def merge_results(results_1: RolloutResults, results_2: RolloutResults):
    return RolloutResults(
        ascensions=results_1.ascensions + results_2.ascensions,
        scores=results_1.scores + results_2.scores,
        log_paths=results_1.log_paths + results_2.log_paths,
    )

if __name__ == "__main__":
    overall_results = RolloutResults(
        ascensions=0,
        scores=[],
        log_paths=[],
    )
    runners : List[Runner] = []
    episodes_per_runner = TestEvaluationConfig.NUM_EPISODES // environment.env.num_runners + 1
    for i in range(0, environment.env.num_runners):
        runner_queue = Queue()
        runner = Runner(
            id=i,
            process=Process(target=evaluate, args=(i, episodes_per_runner, runner_queue)),
            queue=runner_queue,
        )
        runners.append(runner)

    for runner in runners:
        runner.process.start()

    done_runners = 0

    while done_runners < environment.env.num_runners:
        time.sleep(30)
        for runner in runners:
            if runner.done:
                continue
            try:
                new_results = runner.queue.get(timeout=1)
                overall_results = merge_results(overall_results, new_results)
            except queue.Empty:
                pass
            runner.process.join(timeout=1)
            if runner.process.exitcode is not None:
                runner.done = True
                done_runners += 1

    for path in overall_results.log_paths:
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

        df = df[~df['scummed']]

        print(
            f"Runs: {len(df.index)}, "
            f"Ascensions: {df['ascended'].sum()}, "
            f"Median Score: {df['score_log'].median()}, "
            f"Mean Score: {df['score_log'].mean()}, "
            f"Min Score: {df['score_log'].min()}, "
            f"Max Score: {df['score_log'].max()}, "
            f"Max depth: {df['depth_log'].max()}, "
            f"Max experience: {df['explevel'].max()}, "
        )
