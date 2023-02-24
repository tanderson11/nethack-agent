import numpy as np
import utilities
import nle.nethack as nethack
from typing import NamedTuple

class Square(NamedTuple):
    row: int
    col: int

    def __add__(self, x):
        return self.__class__(self[0]+x[0], self[1]+x[1])

    def __sub__(self, x):
        return self.__class__(self[0]-x[0], self[1]-x[1])


    #def __eq__(self, x):
    #    return (self[0] == x[0]) and (self[1] == x[1])

class AttackRange(NamedTuple):
    type: str = 'melee'
    range: int = 1

action_grid = np.array([
    nethack.actions.CompassDirection.NW,
    nethack.actions.CompassDirection.N,
    nethack.actions.CompassDirection.NE,
    nethack.actions.CompassDirection.W,
    nethack.actions.MiscDirection.WAIT, # maybe this should be None so we can catch unexpected behavior?
    nethack.actions.CompassDirection.E,
    nethack.actions.CompassDirection.SW,
    nethack.actions.CompassDirection.S,
    nethack.actions.CompassDirection.SE,
]).reshape(3,3)

action_to_delta = {
    nethack.actions.CompassDirection.NW: (-1, -1),
    nethack.actions.CompassDirection.N: (-1, 0),
    nethack.actions.CompassDirection.NE: (-1, 1),
    nethack.actions.CompassDirection.W: (0, -1),
    nethack.actions.CompassDirection.E: (0, 1),
    nethack.actions.CompassDirection.SW: (1, -1),
    nethack.actions.CompassDirection.S: (1, 0),
    nethack.actions.CompassDirection.SE: (1, 1),
}

delta_to_action = {v:k for k,v in action_to_delta.items()}

action_deltas = action_to_delta.values()

direction_actions = set([
    nethack.actions.CompassDirection.NW,
    nethack.actions.CompassDirection.N,
    nethack.actions.CompassDirection.NE,
    nethack.actions.CompassDirection.W,
    nethack.actions.CompassDirection.E,
    nethack.actions.CompassDirection.SW,
    nethack.actions.CompassDirection.S,
    nethack.actions.CompassDirection.SE,
])

diagonal_direction_actions = set([
    nethack.actions.CompassDirection.NW,
    nethack.actions.CompassDirection.NE,
    nethack.actions.CompassDirection.SW,
    nethack.actions.CompassDirection.SE,
])

diagonal_moves = utilities.vectorized_map(lambda dir: dir in diagonal_direction_actions, action_grid)

def offset_location_by_action(location, action):
     delta = action_to_delta[action]
     new_loc = (location[0] + delta[0], location[1] + delta[1])
     return new_loc


ortholinear_offsets = [(1,0), (0,1), (-1, 0), (0, -1)]