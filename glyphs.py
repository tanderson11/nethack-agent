import pdb

import numpy as np

import environment

# all the ones I've found so far
PLAYER_GLYPHS = range(327, 342)
# WALL_GLPYHS = 2360, 2361 = vertical + horizontal
# 2362, 2363, 2364, 2365 corners
WALL_GLYPHS = list(range(2360, 2366)) + [0]
DOWNSTAIRS_GLYPH = 2383
DOOR_GLYPHS = range(2374, 2376)