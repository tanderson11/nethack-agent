import sys
import os
import subprocess
import json
import ast

import nh_git

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise ValueError("expected commit sha as first argument")

    commit_sha = sys.argv[1]
    issue = None
    if len(sys.argv) == 3:
        issue = sys.argv[2]
    elif len(sys.argv) > 3:
        raise ValueError("expected at most two arguments (sha, issue)")

    cherry_pick_output = nh_git.cherry_pick(commit_sha)

    for line in cherry_pick_output.split('\n'):
        for word in line.split(' '):
            if 'seeds.json' in word:
                with open(word, 'r') as f:
                    seeds = json.load(f)
                agent_seed = ast.literal_eval(seeds['agent_seed']) # eval to bytes
                core_seed  = seeds['core_seed']
                disp_seed  = seeds['disp_seed']
                print(f"Agent seed: {agent_seed}")
                print(f"Core seed: {core_seed} Disp seed: {disp_seed}")
            elif 'environment.json' in word:
                os.environ["NLE_DEV_USE_JSON_ENV"] = word
            elif f".csv" in word:
                seeded_runs_path = os.path.join(os.path.dirname(__file__), "seeded_runs")
                print("Copying replay to seeded_runs/")
                subprocess.check_output(['cp', word, seeded_runs_path])
    import play_seeded
    nh_git.revert(commit_sha)

    play_seeded.play_seed(agent_seed, core_seed, disp_seed, respond_to_issue=issue)