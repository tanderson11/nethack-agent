## This file is intended to emulate the evaluation on AIcrowd

# IMPORTANT - Differences to expect
# * All the environment's functions are not available
# * The run might be slower than your local run
# * Resources might vary from your local machine

from typing import Any, NamedTuple, List
import csv
from dataclasses import dataclass
from multiprocessing import Process, Queue
import os
import queue
import time

import numpy as np
import pandas as pd
from tqdm import tqdm

from submission_config import SubmissionConfig, TestEvaluationConfig

from envs.batched_env import InstrumentedEnv

import environment
import parse_ttyrec

class RolloutResults(NamedTuple):
    runners: int
    ascensions: int
    scores: List[int]
    log_paths: str
    crash_seeds: List[Any]

seed_whitelist = []
if environment.env.use_seed_whitelist:
    with open(os.path.join(os.path.dirname(__file__), "seeded_runs", "seed_whitelist.csv"), newline='') as csvfile:
        seed_reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for i, row in enumerate(seed_reader):
            if i == 0:
                assert row[0] == 'core'
                assert row[1] == 'display'
                continue
            seed_whitelist.append((int(row[0]), int(row[1])))

def evaluate(runner_index, num_episodes=TestEvaluationConfig.NUM_EPISODES, runner_queue=None):
    env_make_fn = SubmissionConfig.MAKE_ENV_FN
    Agent = SubmissionConfig.AGENT

    seeds = seed_whitelist[(runner_index * num_episodes):((runner_index + 1) * num_episodes)]
    # If you want to manually try a single seed
    #seeds = [(4051645496201203180, 1168582581147282503)]

    instrumented_env = InstrumentedEnv(env_make_fn=env_make_fn, seeds=seeds)
    agent = Agent(instrumented_env.env if environment.env.log_runs else None)

    ascension_count = 0
    scores = []
    crash_seeds = []
    episode_count = 0
    pbar = tqdm(total=num_episodes)

    while episode_count < num_episodes:
        seed = None
        if instrumented_env.seeded():
            core, disp, _ = instrumented_env.env.get_seeds()
            seed = (core, disp, agent.run_state.seed)
        ascension, crashed, score = instrumented_env.run_episode(agent)
        scores.append(score)
        ascension_count += int(ascension)
        if crashed:
            crash_seeds.append(seed)
        episode_count += 1
        pbar.update(1)

    pbar.close()

    log_paths = []
    if environment.env.log_runs:
        log_paths.append(instrumented_env.env.savedir)

    results = RolloutResults(
        runners=1,
        ascensions=ascension_count,
        scores=scores,
        log_paths=log_paths,
        crash_seeds=crash_seeds,
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
        runners=results_1.runners + results_2.runners,
        ascensions=results_1.ascensions + results_2.ascensions,
        scores=results_1.scores + results_2.scores,
        log_paths=results_1.log_paths + results_2.log_paths,
        crash_seeds=results_1.crash_seeds + results_2.crash_seeds,
    )

def run_multiple(num_runners):
    overall_results = RolloutResults(
        runners=0,
        ascensions=0,
        scores=[],
        log_paths=[],
        crash_seeds=[],
    )
    runners : List[Runner] = []
    episodes_per_runner = TestEvaluationConfig.NUM_EPISODES // num_runners + 1
    for i in range(0, num_runners):
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
    crashed_runners = 0

    while done_runners < num_runners:
        time.sleep(30)
        for runner in runners:
            if runner.done:
                continue
            runner.process.join(timeout=1)
            if runner.process.exitcode is not None:
                try:
                    new_results = runner.queue.get(timeout=1)
                    overall_results = merge_results(overall_results, new_results)
                except queue.Empty:
                    crashed_runners += 1
                    pass
                runner.done = True
                done_runners += 1

    return overall_results, crashed_runners, episodes_per_runner


if __name__ == "__main__":
    if environment.env.num_runners > 1:
        overall_results, crashed_runners, episodes_per_runner = run_multiple(environment.env.num_runners)
    else:
        overall_results = evaluate(0, TestEvaluationConfig.NUM_EPISODES)
        episodes_per_runner = TestEvaluationConfig.NUM_EPISODES
        crashed_runners = 0

    print(
        f"Runners: {overall_results.runners}, "
        f"Crashed runners: {crashed_runners}, "
        f"Crashed runs: {len(overall_results.crash_seeds)}, "
        f"Runs: {len(overall_results.scores)}, "
        f"Ascensions: {overall_results.ascensions}, "
        f"Median Score: {np.median(overall_results.scores)}, "
        f"Above {environment.env.max_score}: {(np.asarray(overall_results.scores) >= environment.env.max_score).sum()}, "
        f"Mean Score: {np.mean(overall_results.scores)}, "
        f"Min Score: {min(overall_results.scores)}, "
        f"Max Score: {max(overall_results.scores)}, "
    )

    print(f"Crash seeds: {overall_results.crash_seeds}")

    joint_log_df = None

    for path in overall_results.log_paths:
        files = [os.path.join(path,f) for f in os.listdir(path) if os.path.isfile(os.path.join(path,f)) and f.endswith('.ttyrec.bz2')]
        for f in files:
            if f.endswith('{}.ttyrec.bz2'.format(episodes_per_runner)): # rm this junk file
                print("Removing {}".format(f))
                os.remove(f)
        outpath = os.path.join(path, "deaths.csv")
        try:
            score_df = parse_ttyrec.parse_dir(path, outpath=outpath)
        except Exception as e:
            print(f"TTYREC parse failed with {e}. Failing gracefully")
        else:
            log_df = pd.read_csv(os.path.join(path, "log.csv"))
            df = score_df.join(log_df, rsuffix='_log')
            if joint_log_df is None:
                joint_log_df = df
            else:
                joint_log_df = joint_log_df.append(df, ignore_index=True)

    if joint_log_df is not None:
        parse_ttyrec.print_stats_from_log(joint_log_df)

        with open(os.path.join(overall_results.log_paths[0], "joint_log.csv"), 'w') as f:
            joint_log_df.to_csv(f)

        joint_log_df = joint_log_df[~pd.isna(joint_log_df['scummed'])]
        joint_log_df = joint_log_df[~joint_log_df['scummed'].astype(bool)]

        print(
            f"Runs: {len(joint_log_df.index)}, "
            f"Ascensions: {joint_log_df['ascended'].sum()}, "
            f"Median Score: {joint_log_df['score_log'].median()}, "
            f"Above {environment.env.max_score}: {(np.asarray(joint_log_df['score_log']) >= environment.env.max_score).sum()}, "
            f"Mean Score: {joint_log_df['score_log'].mean()}, "
            f"Min Score: {joint_log_df['score_log'].min()}, "
            f"Max Score: {joint_log_df['score_log'].max()}, "
            f"Max depth: {joint_log_df['depth_log'].max()}, "
            f"Max experience: {joint_log_df['explevel'].max()}, "
        )
