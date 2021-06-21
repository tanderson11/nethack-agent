import numpy as np

# all the ones I've found so far
PLAYER_GLYPHS = range(327, 342)
# WALL_GLPYHS = 2360, 2361 = vertical + horizontal
# 2362, 2363, 2364, 2365 corners
WALL_GLYPHS = range(2360, 2366)

def is_player_glyph(glyph):
	return glyph in PLAYER_GLYPHS
#is_player_glyph = np.vectorize(is_player_glyph)

def is_walkable_glyph(glyph):
	return glyph not in WALL_GLYPHS and glyph != 0
#is_walkable_glyph = np.vectorize(is_walkable_glyph)