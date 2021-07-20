import numpy as np
import utilities
import nle.nethack as nethack

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
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.NW]: (-1, -1),
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.N]: (-1, 0),
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.NE]: (-1, 1),
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.W]: (0, -1),
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.E]: (0, 1),
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.SW]: (1, -1),
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.S]: (1, 0),
    utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.SE]: (1, 1),
}

action_deltas = action_to_delta.values()

diagonal_moves = utilities.vectorized_map(lambda dir: utilities.ACTION_LOOKUP[dir] > 3 and utilities.ACTION_LOOKUP[dir] < 8, action_grid)

def offset_location_by_action(location, action):
     delta = action_to_delta[action]
     new_loc = (location[0] + delta[0], location[1] + delta[1])
     return new_loc