from typing import NamedTuple
import os
import constants

class EnvironmentVariable(NamedTuple):
    num_environments: int
    num_episodes: int
    debug: bool
    log_runs: bool
    target_roles: set[str]

def try_cast(type, var):
    if var is None:
        return None
    return type(var)

def parse_target_roles(raw_str):
    if not raw_str:
        return set()

    return set([constants.BaseRole[s] for s in raw_str.split(',')])

env = EnvironmentVariable(
    num_environments=try_cast(int, os.getenv("NLE_DEV_NUM_ENVIRONMENTS")),
    num_episodes=try_cast(int, os.getenv("NLE_DEV_NUM_EPISODES")),
    debug=(os.getenv("NLE_DEV_DEBUG") == "true"),
    log_runs=((os.getenv("NLE_DEV_DEBUG") == "true") or (os.getenv("NLE_DEV_LOG_RUNS") == "true")),
    target_roles=parse_target_roles(os.getenv("NLE_DEV_TARGET_ROLES")),
)
