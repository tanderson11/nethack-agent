from typing import NamedTuple
import os

class EnvironmentVariable(NamedTuple):
    num_environments: int
    num_episodes: int
    debug: bool
    log_runs: bool

def try_cast(type, var):
    if var is None:
        return None
    return type(var)

env = EnvironmentVariable(
    num_environments=try_cast(int, os.getenv("NLE_DEV_NUM_ENVIRONMENTS")),
    num_episodes=try_cast(int, os.getenv("NLE_DEV_NUM_EPISODES")),
    debug=(os.getenv("NLE_DEV_DEBUG") == "true"),
    log_runs=((os.getenv("NLE_DEV_DEBUG") == "true") or (os.getenv("NLE_DEV_LOG_RUNS") == "true")),
)
