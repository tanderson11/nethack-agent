import nle.nethack as nethack
import glyphs as gd

def keypress_action(ascii_ord):
    action = nethack.ACTIONS.index(ascii_ord)
    if action is None:
        raise Exception("Bad keypress")
    return action