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

##################################
### For neighborhoods and maps ###
##################################

def vectorized_map(f, nd_array):
    return np.array(list(map(f, nd_array.ravel()))).reshape(nd_array.shape)

def centered_slices_bounded_on_array(start, radii, target_array):
    row_slice_radius, col_slice_radius = radii
    col_lim = target_array.shape[1]
    row_lim = target_array.shape[0]

    row_start, col_start = start

    row_slice = slice(max(row_start-row_slice_radius, 0), min(row_start+row_slice_radius+1, row_lim)) # +1 because non-inclusive on upper end
    col_slice = slice(max(col_start-col_slice_radius, 0), min(col_start+col_slice_radius+1, col_lim))

    return row_slice, col_slice

def move_slice_center(old_center, new_center, slices):
    old_center_row, old_center_col = old_center
    new_center_row, new_center_col = new_center

    row_translate = old_center_row - new_center_row
    col_translate = old_center_col - new_center_col

    row_slice, col_slice = slices

    relative_row_slice = slice(row_slice.start-row_translate,row_slice.stop-row_translate)
    relative_col_slice = slice(col_slice.start-col_translate,col_slice.stop-col_translate)

    return relative_row_slice, relative_col_slice

def rectangle_defined_by_corners(corner1, corner2):
    x1,y1 = corner1
    x2,y2 = corner2
    row_slice = slice(min(x1,x2), max(x1,x2)+1)
    col_slice = slice(min(y1,y2), max(y1,y2)+1)

    return row_slice, col_slice