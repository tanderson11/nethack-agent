from typing import NamedTuple, Set
import os
import agents.representation.constants as constants

class EnvironmentVariable(NamedTuple):
    num_environments: int
    num_runners: int
    num_episodes: int
    debug: bool
    print_seed: bool
    log_runs: bool
    log_video: bool
    make_replay: bool
    target_roles: Set[str]
    wizard: bool
    use_seed_whitelist: bool
    max_score: int

    def dump(self):
        self_dict = self._asdict()
        target_roles = self_dict['target_roles']
        self_dict['target_roles'] = [r.value for r in target_roles] if target_roles else []
        return self_dict

def try_cast(type, var):
    if var is None:
        return None
    return type(var)

def parse_target_roles(raw_str):
    if not raw_str:
        return set()

    return set([constants.BaseRole[s] for s in raw_str.split(',')])

def parse_target_roles_from_list(l):
    return set([constants.BaseRole[s] for s in l])

def make_environment(**kwargs):
    default_environment = {
        'num_environments': 1,
        'num_runners': 4,
        'num_episodes': 8192, # AIcrowd will cut the assessment early as needed
        'debug': False,
        'log_runs': False,
        'log_video': False,
        'make_replay': False,
        'print_seed': False,
        'target_roles': set(),
        'wizard': False,
        'use_seed_whitelist': False,
        'max_score': 3600,
    }

    environment = {
        'num_environments':try_cast(int, os.getenv("NLE_DEV_NUM_ENVIRONMENTS")),
        'num_runners': try_cast(int, os.getenv("NLE_DEV_NUM_RUNNERS")),
        'num_episodes':try_cast(int, os.getenv("NLE_DEV_NUM_EPISODES")),
        'debug':(os.getenv("NLE_DEV_DEBUG") == "true"),
        'print_seed':(os.getenv("NLE_DEV_PRINT_SEED") == "true"),
        'log_video':((os.getenv("NLE_DEV_LOG_VIDEO") == "true")),
        'log_runs':((os.getenv("NLE_DEV_LOG_RUNS") == "true")),
        'make_replay':((os.getenv("NLE_DEV_MAKE_REPLAY") == "true")),
        'target_roles':parse_target_roles(os.getenv("NLE_DEV_TARGET_ROLES")),
        'wizard':(os.getenv("NLE_DEV_WIZARD") == "true"),
        'use_seed_whitelist':(os.getenv("NLE_USE_SEED_WHITELIST") == "true"),
        'max_score':try_cast(int, os.getenv("NLE_DEV_MAX_SCORE")),
    }
    default_environment.update({k:v for k,v in environment.items() if v is not None})
    default_environment.update(kwargs)
    if 'target_roles' in kwargs.keys():
        default_environment.update({'target_roles': parse_target_roles_from_list(kwargs['target_roles'])})
    return EnvironmentVariable(**default_environment)

json_env = os.getenv("NLE_DEV_USE_JSON_ENV")
if json_env:
    import json
    with open(json_env, 'r') as f:
        env_dict = json.load(f)

    try:
        env_dict.pop('make_replay')
    except KeyError:
        pass
    env = make_environment(**env_dict)
else:
    env = make_environment()

print(env)
