from abc import ABC, abstractmethod
from typing import Optional, Any

import environment

class BatchedAgent(ABC):
    """
    This is an abstract base clase for you to load your models and perform rollouts on a
    batched set of environments.
    """
    def __init__(self, num_envs: int , num_actions: int, debug_envs: "Optional[list[Any]]" = None):
        self.num_envs = num_envs
        self.num_actions = num_actions
        if debug_envs and not environment.env.debug:
            raise Exception("This should only be here in debug mode")
        self.debug_envs = debug_envs

    @abstractmethod
    def batched_step(self, observations, rewards, dones, infos):
        """
        Perform a batched step on lists of environment outputs.

        :param observations: a list of observations 
        :param rewards: a list of rewards 
        :param dones: a list of dones 
        :param observations: a list of infos
        
        returns: an iterable of actions 
        """
        pass

