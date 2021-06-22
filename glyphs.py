import pdb

import numpy as np

import environment

# all the ones I've found so far
PLAYER_GLYPHS = range(327, 342)
# WALL_GLPYHS = 2360, 2361 = vertical + horizontal
# 2362, 2363, 2364, 2365 corners
WALL_GLYPHS = range(2360, 2366)
DOWNSTAIRS_GLYPH = 2383
DOOR_GLYPHS = range(2374, 2376)

def is_player_glyph(glyph):
	return glyph in PLAYER_GLYPHS
#is_player_glyph = np.vectorize(is_player_glyph)

def is_walkable_glyph(glyph):
	return glyph not in WALL_GLYPHS and glyph != 0
#is_walkable_glyph = np.vectorize(is_walkable_glyph)

def find_player_location(observation):
    player_location = np.array(np.where(np.isin(observation['glyphs'], PLAYER_GLYPHS))).squeeze()

    if not player_location.any(): # if we didn't locate the player (possibly because our player glyph range isn't wide enough)
        if environment.env.debug: pdb.set_trace()
        pass
    return tuple(player_location)