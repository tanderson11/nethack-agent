from typing import NamedTuple, Set
import os
import constants

class EnvironmentVariable(NamedTuple):
    num_environments: int
    num_episodes: int
    debug: bool
    print_seed: bool
    log_runs: bool
    target_roles: Set[str]
    wizard: bool
    use_seed_whitelist: bool
    max_score: int

def try_cast(type, var):
    if var is None:
        return None
    return type(var)

def parse_target_roles(raw_str):
    if not raw_str:
        return set()

    return set([constants.BaseRole[s] for s in raw_str.split(',')])

def make_environment(**kwargs):
    default_environment = {
        'num_environments': 1,
        'num_episodes':512,
        'debug': False,
        'log_runs': False,
        'print_seed': False,
        'target_roles': set(),
        'wizard': False,
        'use_seed_whitelist': False,
        'max_score': 3000,
    }

    environment = {
        'num_environments':try_cast(int, os.getenv("NLE_DEV_NUM_ENVIRONMENTS")),
        'num_episodes':try_cast(int, os.getenv("NLE_DEV_NUM_EPISODES")),
        'debug':(os.getenv("NLE_DEV_DEBUG") == "true"),
        'print_seed':(os.getenv("NLE_DEV_PRINT_SEED") == "true"),
        'log_runs':((os.getenv("NLE_DEV_LOG_RUNS") == "true")),
        'target_roles':parse_target_roles(os.getenv("NLE_DEV_TARGET_ROLES")),
        'wizard':(os.getenv("NLE_DEV_WIZARD") == "true"),
        'use_seed_whitelist':(os.getenv("NLE_USE_SEED_WHITELIST") == "true"),
        'max_score':try_cast(int, os.getenv("NLE_DEV_MAX_SCORE")),
    }
    default_environment.update({k:v for k,v in environment.items() if v is not None})
    default_environment.update(kwargs)

    return EnvironmentVariable(**default_environment)

env = make_environment()
print(env)
