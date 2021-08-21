import enum

import numpy as np

import environment
import glyphs as gd
import physics
import utilities

class Branches(enum.Enum):
    DungeonsOfDoom = 0
    GnomishMines = 2
    Quest = 3
    Sokoban = 4

INDEX_TO_BRANCH = {
    Branches.DungeonsOfDoom.value: Branches.DungeonsOfDoom,
    Branches.GnomishMines.value: Branches.GnomishMines,
    Branches.Quest.value: Branches.Quest,
    Branches.Sokoban.value: Branches.Sokoban,
}

class DMap():
    def __init__(self):
        self.dlevels = {}

    def make_level_map(self, dungeon_number, level_number, glyphs, initial_player_location):
        lmap = DLevelMap(dungeon_number, level_number, glyphs)
        self.dlevels[(dungeon_number, level_number)] = lmap

        # if we just made the map of level 1 of dungeons of doom, add the staircase on our square
        if dungeon_number == 0 and level_number == 1:
            lmap.add_feature(initial_player_location, gd.get_by_name(gd.CMapGlyph, 'upstair'))

        return lmap

class Staircase():
    def __init__(self, dcoord, location, to_dcoord, to_location, direction):
        self.start_dcoord = dcoord
        self.start_location = location

        self.end_dcoord = to_dcoord
        self.end_location = to_location

        self.direction = direction

class DLevelMap():
    @staticmethod
    def glyphs_to_dungeon_features(glyphs, prior):
        # This treats the gd.CMapGlyph.OFFSET as unobserved. No way, AFAICT, to
        # distinguish between solid stone that we've seen with our own eyes vs. not
        return np.where(
            (glyphs > gd.CMapGlyph.OFFSET) & (glyphs < gd.CMapGlyph.OFFSET + gd.CMapGlyph.COUNT),
            glyphs,
            prior
        )

    def __init__(self, dungeon_number, level_number, glyphs):
        self.dungeon_number = dungeon_number
        if environment.env.debug and not self.dungeon_number in INDEX_TO_BRANCH:
            import pdb; pdb.set_trace()
        self.level_number = level_number
        self.need_downstairs = True
        self.need_upstairs = True

        # These are our map layers
        self.dungeon_feature_map = np.zeros_like(glyphs)
        self.visits_count_map = np.zeros_like(glyphs)
        self.staircases = {}
        self.warning_engravings = {}

    
    def update(self, player_location, glyphs):
        self.dungeon_feature_map = self.glyphs_to_dungeon_features(glyphs, self.dungeon_feature_map)
        # This is expensive. If we don't get long-term utility from these, should delete it
        if self.need_downstairs or self.need_upstairs:
            unique, counts = np.unique(self.dungeon_feature_map, return_counts=True)
            counted_elements = dict(zip(unique, counts))
            if self.need_upstairs and counted_elements.get(gd.get_by_name(gd.CMapGlyph, 'upstair').numeral, None):
                self.need_upstairs = False
            if self.need_downstairs and counted_elements.get(gd.get_by_name(gd.CMapGlyph, 'dnstair').numeral, None):
                self.need_downstairs = False
        self.visits_count_map[player_location] += 1

    def get_dungeon_glyph(self, location):
        loc = self.dungeon_feature_map[location]
        if loc:
            return gd.GLYPH_NUMERAL_LOOKUP[loc]
        return None

    def add_feature(self, location, glyph):
        if not isinstance(glyph, gd.CMapGlyph):
            raise Exception("Bad feature glyph")
        self.dungeon_feature_map[location] = glyph.numeral
        if glyph.is_downstairs:
            self.need_downstairs = False
        elif glyph.is_upstairs:
            self.need_upstairs = False

    def add_traversed_staircase(self, location, to_dcoord, to_location, direction):
        try:
            return self.staircases[location]
        except KeyError:
            if direction != 'up' and direction != 'down':
                raise Exception("Strange direction " + direction)
            staircase = Staircase(
                (self.dungeon_number, self.level_number),
                location,
                to_dcoord,
                to_location,
                direction)
            self.add_feature(location, gd.get_by_name(gd.CMapGlyph, 'upstair' if direction == 'up' else 'dnstair'))
            self.staircases[location] = staircase
            return staircase


class FloodMap():
    @staticmethod
    def flood_one_level_from_mask(mask):
        flooded_mask = np.full_like(mask, False, dtype='bool')

        # for every square
        it = np.nditer(mask, flags=['multi_index'])
        for b in it: 
            # if we occupy it
            if b: 
                # take a radius one box around it
                row_slice, col_slice = utilities.centered_slices_bounded_on_array(it.multi_index, (1, 1), flooded_mask)
                # and flood all those squares
                flooded_mask[row_slice, col_slice] = True

        return flooded_mask


class ThreatMap(FloodMap):
    INVISIBLE_DAMAGE_THREAT = 6 # gotta do something lol

    def __init__(self, raw_visible_glyphs, visible_glyphs, player_location_in_vision):
        # take the section of the observed glyphs that is relevant
        self.glyph_grid = visible_glyphs
        self.raw_glyph_grid = raw_visible_glyphs
        self.player_location_in_glyph_grid = player_location_in_vision

        self.calculate_threat()
        #self.calculate_implied_threat()

    @classmethod
    def calculate_can_occupy(cls, monster, start, glyph_grid):
        #print(monster)
        if isinstance(monster, gd.MonsterGlyph):
            free_moves = np.ceil(monster.monster_spoiler.speed / monster.monster_spoiler.__class__.NORMAL_SPEED) - 1 # -1 because we are interested in move+hit turns not just move turns
            #print("speed, free_moves:", monster.monster_spoiler.speed, free_moves)
        elif isinstance(monster, gd.InvisibleGlyph):
            free_moves = 0
        
        mons_square_mask = np.full_like(glyph_grid, False, dtype='bool')
        mons_square_mask[start] = True
        can_occupy_mask = mons_square_mask

        if free_moves > 0: # if we can move+attack, we need to know where we can move
            walkable = utilities.vectorized_map(lambda g: g.walkable(monster), glyph_grid)
            already_checked_mask = np.full_like(glyph_grid, False, dtype='bool')

        while free_moves > 0:
            # flood from newly identified squares that we can occupy
            flooded_mask = cls.flood_one_level_from_mask(can_occupy_mask & ~already_checked_mask)
            # remember where we've already looked (for efficiency, not correctness)
            already_checked_mask = can_occupy_mask
            # add new squares that are also walkable to places we can occupy
            can_occupy_mask = can_occupy_mask | (flooded_mask & walkable)
            # use up a move
            free_moves -= 1
            #pdb.set_trace()

        return can_occupy_mask  

    @classmethod
    def calculate_melee_can_hit(cls, can_occupy_mask):
        can_hit_mask = cls.flood_one_level_from_mask(can_occupy_mask)

        return can_hit_mask

    def calculate_threat(self):
        melee_n_threat = np.zeros_like(self.glyph_grid)
        melee_damage_threat = np.zeros_like(self.glyph_grid)

        ranged_n_threat = np.zeros_like(self.glyph_grid)
        ranged_damage_threat = np.zeros_like(self.glyph_grid)

        it = np.nditer(self.raw_glyph_grid, flags=['multi_index'])
        for g in it: # iterate over glyph grid
            glyph = self.glyph_grid[it.multi_index]
            if it.multi_index != self.player_location_in_glyph_grid:
                try:
                    isinstance(glyph, gd.MonsterGlyph) and glyph.has_melee
                except AttributeError:
                    if environment.env.debug: import pdb; pdb.set_trace() # probably a long worm tail lol

                if isinstance(glyph, gd.SwallowGlyph):
                    melee_damage_threat.fill(gd.GLYPH_NUMERAL_LOOKUP[glyph.swallowing_monster_offset].monster_spoiler.engulf_attack_bundle.max_damage) # while we're swallowed, all threat can be homogeneous
                    melee_n_threat.fill(1) # we're only ever threatened once while swallowed

                is_invis = isinstance(glyph, gd.InvisibleGlyph)
                if isinstance(glyph, gd.MonsterGlyph) or is_invis:
                    if not (isinstance(glyph, gd.MonsterGlyph) and glyph.always_peaceful): # always peaceful monsters don't need to threaten
                        ### SHARED ###
                        can_occupy_mask = self.__class__.calculate_can_occupy(glyph, it.multi_index, self.glyph_grid)
                        ###

                        ### MELEE ###
                        if is_invis or glyph.has_melee:
                            can_hit_mask = self.__class__.calculate_melee_can_hit(can_occupy_mask)

                            melee_n_threat[can_hit_mask] += 1 # monsters threaten their own squares in this implementation OK? TK 
                        
                            if isinstance(glyph, gd.MonsterGlyph):
                                melee_damage_threat[can_hit_mask] += glyph.monster_spoiler.melee_attack_bundle.max_damage

                            if is_invis:
                                melee_damage_threat[can_hit_mask] += self.__class__.INVISIBLE_DAMAGE_THREAT # how should we imagine the threat of invisible monsters?
                        ###

                        ### RANGED ###
                        if is_invis or glyph.has_ranged: # let's let invisible monsters threaten at range so we rush them down someday
                            can_hit_mask = self.__class__.calculate_ranged_can_hit_mask(can_occupy_mask, self.glyph_grid)
                            ranged_n_threat[can_hit_mask] += 1
                            if is_invis:
                                ranged_damage_threat[can_hit_mask] += self.__class__.INVISIBLE_DAMAGE_THREAT
                            else:
                                ranged_damage_threat[can_hit_mask] += glyph.monster_spoiler.ranged_attack_bundle.max_damage
                        ###

        self.melee_n_threat = melee_n_threat
        self.melee_damage_threat = melee_damage_threat

        self.ranged_n_threat = ranged_n_threat
        self.ranged_damage_threat = ranged_damage_threat

    @classmethod
    def calculate_ranged_can_hit_mask(cls, can_occupy_mask, glyph_grid):
        it = np.nditer(can_occupy_mask, flags=['multi_index'])
        masks = []
        for b in it: 
            if b:
                can_hit_from_loc = cls.raytrace_threat(it.multi_index, glyph_grid)
                masks.append(can_hit_from_loc)
        return np.logical_or.reduce(masks)

    @staticmethod
    def raytrace_threat(source, glyph_grid):
        row_lim = glyph_grid.shape[0]
        col_lim = glyph_grid.shape[1]

        ray_offsets = physics.action_deltas

        masks = []
        for offset in ray_offsets:
            ray_mask = np.full_like(glyph_grid, False, dtype='bool')

            current = source
            current = (current[0]+2*offset[0], current[1]+2*offset[1]) # initial bump so that ranged attacks don't threaten adjacent squares
            while 0 <= current[0] < row_lim and 0 <= current[1] < col_lim:
                glyph = glyph_grid[current]
                if isinstance(glyph, gd.CMapGlyph) and glyph.is_wall: # is this the full extent of what blocks projectiles/rays?
                    break # should we do anything with bouncing rays
                ray_mask[current] = True

                current = (current[0]+offset[0], current[1]+offset[1])

            masks.append(ray_mask)

        can_hit_mask = np.logical_or.reduce(masks)
        return can_hit_mask
