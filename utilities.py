import nle.nethack as nethack
import glyphs as gd

class ActiveRunState():
    def __init__(self):
        rs = None

    def set_active(self, run_state):
        self.rs = run_state

ARS = ActiveRunState()

ACTION_LOOKUP = {}

for i, action in enumerate(nethack.ACTIONS):
    ACTION_LOOKUP[action] = i

def keypress_action(ascii_ord):
    action = ACTION_LOOKUP[ascii_ord]
    if action is None:
        raise Exception("Bad keypress")
    return action
