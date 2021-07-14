import nle.nethack as nethack
import glyphs as gd
import numpy as np

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

def have_item_oclasses(oclasses, inventory):
    for oclass in oclasses:
        if gd.ObjectGlyph.OBJECT_CLASSES.index(oclass) in inventory['inv_oclasses']: return True
    return False

def vectorized_map(f, nd_array):
    return np.array(list(map(f, nd_array.ravel()))).reshape(nd_array.shape)