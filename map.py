from collections import defaultdict
import enum
from typing import NamedTuple

import numpy as np

import environment
import glyphs as gd
import physics
import utilities
import constants

from utilities import ARS

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
        lmap = DLevelMap(dungeon_number, level_number)
        self.dlevels[(dungeon_number, level_number)] = lmap

        # if we just made the map of level 1 of dungeons of doom, add the staircase on our square
        if dungeon_number == 0 and level_number == 1:
            lmap.add_feature(initial_player_location, gd.get_by_name(gd.CMapGlyph, 'upstair'))

        lmap.update(initial_player_location, glyphs)

        return lmap

class Staircase():
    def __init__(self, dcoord, location, to_dcoord, to_location, direction):
        self.start_dcoord = dcoord
        self.start_branch = INDEX_TO_BRANCH[dcoord[0]]
        self.start_location = location

        self.end_dcoord = to_dcoord
        self.end_location = to_location
        self.end_branch = INDEX_TO_BRANCH[to_dcoord[0]]

        self.direction = direction

class TimedCorpse(NamedTuple):
    ACCEPTABLE_CORPSE_AGE = 40

    time: int
    monster_glyph: gd.MonsterGlyph

class DLevelMap():
    @staticmethod
    def glyphs_to_dungeon_features(glyphs, prior):
        # This treats the gd.CMapGlyph.OFFSET as unobserved. No way, AFAICT, to
        # distinguish between solid stone that we've seen with our own eyes vs. not

        dungeon_features = np.where(
            gd.CMapGlyph.class_mask(glyphs),
            glyphs,
            prior
        )

        # our prior for monsters and objects is room floor
        #import pdb; pdb.set_trace()
        dungeon_features[(dungeon_features == 0) & ((gd.MonsterGlyph.class_mask(glyphs)) | (gd.ObjectGlyph.class_mask(glyphs)))] = gd.CMapGlyph.OFFSET + 19
        return dungeon_features

    def __init__(self, dungeon_number, level_number):
        self.dungeon_number = dungeon_number
        if environment.env.debug and not self.dungeon_number in INDEX_TO_BRANCH:
            import pdb; pdb.set_trace()
        self.level_number = level_number
        self.dcoord = (self.dungeon_number, self.level_number)
        self.branch = INDEX_TO_BRANCH[dungeon_number]
        self.downstairs_count = 0
        self.upstairs_count = 0
        self.downstairs_target = 1
        self.upstairs_target = 1

        self.player_location = None
        self.player_location_mask = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')

        # These are our map layers
        self.dungeon_feature_map = np.zeros(constants.GLYPHS_SHAPE)
        self.visits_count_map = np.zeros(constants.GLYPHS_SHAPE)
        self.searches_count_map = np.zeros(constants.GLYPHS_SHAPE)
        self.special_room_map = np.full(constants.GLYPHS_SHAPE, constants.SpecialRoomTypes.NONE.value)
        self.owned_doors = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.edible_corpse_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.lootable_squares_map = np.full(constants.GLYPHS_SHAPE, True, dtype='bool')
        self.boulder_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')

        self.staircases = {}
        self.edible_corpse_dict = defaultdict(list)
        self.warning_engravings = {}

    def record_edible_corpse(self, square, time, monster_glyph):
        self.edible_corpse_dict[square].append(TimedCorpse(time=time, monster_glyph=monster_glyph))
        self.edible_corpse_map[square] = True

    def garbage_collect_corpses(self, time):
        new_dict = defaultdict(list)
        for k, v in self.edible_corpse_dict.items():
            still_good = [corpse for corpse in v if corpse.time > (time - corpse.ACCEPTABLE_CORPSE_AGE)]
            if still_good:
                new_dict[k] = still_good
            else:
                self.edible_corpse_map[k] = False
        self.edible_corpse_dict = new_dict

    def next_corpse(self, square):
        if not self.edible_corpse_map[square]:
            return None
        return self.edible_corpse_dict[square][0].monster_glyph

    def record_eat_succeeded_or_failed(self, square):
        self.edible_corpse_dict[square].pop(0)
        if not self.edible_corpse_dict[square]:
            # Ate it empty
            del(self.edible_corpse_dict[square])
            self.edible_corpse_map[square] = False

    def need_egress(self):
        return (self.downstairs_count < self.downstairs_target) or (self.upstairs_count < self.upstairs_target)

    def update_stair_counts(self):
        if self.need_egress():
            # If we're missing stairs let's count and try to find them
            unique, counts = np.unique(self.dungeon_feature_map, return_counts=True)
            counted_elements = dict(zip(unique, counts))
            self.upstairs_count = counted_elements.get(gd.get_by_name(gd.CMapGlyph, 'upstair').numeral, 0)
            self.downstairs_count = counted_elements.get(gd.get_by_name(gd.CMapGlyph, 'dnstair').numeral, 0)
        if self.upstairs_count > self.upstairs_target:
            print(f"Found a branch at {self.dcoord}")
            self.upstairs_target = self.upstairs_count
        if self.downstairs_count > self.downstairs_target:
            print(f"Found a branch at {self.dcoord}")
            self.downstairs_target = self.downstairs_count
    
    def update(self, player_location, glyphs):
        self.dungeon_feature_map = self.glyphs_to_dungeon_features(glyphs, self.dungeon_feature_map)

        self.boulder_map = (glyphs == gd.RockGlyph.OFFSET)

        # Basic terrain types

        offsets = np.where(
            self.dungeon_feature_map != 0,
            self.dungeon_feature_map - gd.CMapGlyph.OFFSET,
            0 # solid stone / unseen
        )

        self.walls = gd.CMapGlyph.is_wall_check(offsets)
        self.room_floor = gd.CMapGlyph.is_room_floor_check(offsets)
        self.safely_walkable = gd.CMapGlyph.is_safely_walkable_check(offsets)
        self.doors = gd.CMapGlyph.is_door_check(offsets)

        if np.count_nonzero(gd.CMapGlyph.is_poorly_understood_check(offsets)):
            if environment.env.debug: import pdb; pdb.set_trace()
            pass

        # This is expensive. If we don't get long-term utility from these, should delete it
        self.update_stair_counts()
        old_player_location = self.player_location
        self.player_location = player_location
        self.visits_count_map[self.player_location] += 1
        self.player_location_mask[old_player_location] = False
        self.player_location_mask[player_location] = True

    def build_room_mask_from_square(self, square_in_room):
        room_mask = np.full_like(self.dungeon_feature_map, False, dtype=bool)
        room_mask[square_in_room] = True

        while True:
            new_mask = FloodMap.flood_one_level_from_mask(room_mask)
            new_mask = new_mask & self.room_floor

            if (new_mask == room_mask).all():
                break
            else:
                room_mask = new_mask

        return room_mask

    def add_room(self, room_mask, room_type):
        self.special_room_map[room_mask] = room_type.value

    def add_room_from_square(self, square_in_room, room_type):
        room_mask = self.build_room_mask_from_square(square_in_room)
        self.add_room(room_mask, room_type)
        #import pdb; pdb.set_trace()

    def get_dungeon_glyph(self, location):
        loc = self.dungeon_feature_map[location]
        if loc:
            return gd.GLYPH_NUMERAL_LOOKUP[loc]
        return None

    def add_feature(self, location, glyph):
        if not isinstance(glyph, gd.CMapGlyph):
            raise Exception("Bad feature glyph")
        self.dungeon_feature_map[location] = glyph.numeral
        if glyph.is_downstairs or glyph.is_upstairs:
            self.update_stair_counts()

    def add_warning_engraving(self, location):
        self.warning_engravings[location] = True

        # vault closet engravings appear on the floor
        if self.room_floor[location] == True:
            self.add_vault_closet(location)
        else:
            self.add_owned_door(location)


    def add_owned_door(self, engraving_location):
        import pdb; pdb.set_trace()
        for offset in physics.ortholinear_offsets:
            offset_loc = engraving_location[0] + offset[0], engraving_location[1] + offset[1]
            if self.doors[offset_loc]:
                self.owned_doors[offset_loc] = True

    def add_vault_closet(self, engraving_location):
        for offset in physics.ortholinear_offsets:
            if self.walls[engraving_location[0] + offset[0], engraving_location[1] + offset[1]]:
                room_mask = np.full_like(self.walls, False, dtype=bool)
                room_mask[engraving_location[0] + 2 * offset[0], engraving_location[1] + 2 * offset[1]] = True
                self.add_room(room_mask, constants.SpecialRoomTypes.vault_closet)

    def add_traversed_staircase(self, location, to_dcoord, to_location, direction):
        try:
            existing = self.staircases[location]
            if existing.direction != direction:
                if environment.env.debug:
                    #import pdb; pdb.set_trace()
                    pass
                # Some sort of bug
                # descend message lingers
                # b'fDS8NA==', 7138506629994509347, 7118309277316884218
                # raise Exception("Conflicting staircases")
                pass
        except KeyError:
            if direction != 'up' and direction != 'down':
                raise Exception("Strange direction " + direction)
            staircase = Staircase(
                self.dcoord,
                location,
                to_dcoord,
                to_location,
                direction)
            self.add_feature(location, gd.get_by_name(gd.CMapGlyph, 'upstair' if direction == 'up' else 'dnstair'))
            self.staircases[location] = staircase
            if staircase.start_branch == Branches.DungeonsOfDoom and staircase.end_branch == Branches.GnomishMines:
                self.downstairs_target += 1
                self.update_stair_counts()
            elif staircase.start_branch == Branches.DungeonsOfDoom and staircase.end_branch == Branches.Sokoban:
                self.upstairs_target += 1
                self.update_stair_counts()
            return staircase

    def log_search(self, player_location):
        if player_location != self.player_location:
            if environment.env.debug:
                import pdb; pdb.set_trace()
            raise Exception("Player locations should match")
        search_mask = FloodMap.flood_one_level_from_mask(self.player_location_mask)
        self.searches_count_map[search_mask] += 1


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
