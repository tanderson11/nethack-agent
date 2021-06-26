import nle.nethack as nethack
import glyphs as gd

ACTION_LOOKUP = {}

for i, action in enumerate(nethack.ACTIONS):
    ACTION_LOOKUP[action] = i

def keypress_action(ascii_ord):
    action = ACTION_LOOKUP[ascii_ord]
    if action is None:
        raise Exception("Bad keypress")
    return action
