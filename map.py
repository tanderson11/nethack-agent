from collections import defaultdict
from dataclasses import dataclass
import enum
from typing import NamedTuple
import json
import os

import numpy as np
import scipy.signal

import environment
import glyphs as gd
import inventory
import physics
import utilities
import constants

import functools
from utilities import ARS

# TODO: I am not sure these ints are constant across nethack games
class Branches(enum.IntEnum):
    DungeonsOfDoom = 0
    GnomishMines = 2
    Quest = 3
    Sokoban = 4
    FortLudios = 5
    MysteryBranch = 128

@dataclass
class DCoord():
    branch_numeral: int
    level: int

    def __post_init__(self):
        try:
            self.branch = Branches(self.branch_numeral)
        except ValueError:
            if environment.env.debug:
                import pdb; pdb.set_trace()
            self.branch = Branches.MysteryBranch
    
    def __eq__(self, y):
        return (self.branch_numeral == y.branch_numeral) and (self.level == y.level)

    def __hash__(self):
        return hash((self.branch_numeral, self.level))

class DirectionThroughDungeon(enum.IntEnum):
        up =  -1
        flat = 0
        down = 1

class DungeonHeading(NamedTuple):
    direction: DirectionThroughDungeon
    target_branch: Branches

class DMap():
    def __init__(self):
        self.dlevels = {}
        self.target_dcoords = {
            Branches.DungeonsOfDoom: DCoord(Branches.DungeonsOfDoom, 1),
            Branches.Sokoban: DCoord(Branches.Sokoban, 1),
        }
        self.branch_connections = {}
        self.oracle_level = None

    def update_target_dcoords(self, character):
        new_targets = {}

        # Dungeons of Doom
        current_dcoord = self.target_dcoords[Branches.DungeonsOfDoom]
        current_map = self.dlevels.get(current_dcoord, None)
        if current_map is None or not current_map.clear:
            new_targets[Branches.DungeonsOfDoom] = current_dcoord
        elif not character.desperate_for_food() and character.comfortable_depth() <= current_dcoord.level:
            new_targets[Branches.DungeonsOfDoom] = current_dcoord
        else:
            if character.desperate_for_food():
                print("Going deeper looking for food")
            first_novel_dcoord = current_dcoord
            while True:
                level_map = self.dlevels.get(first_novel_dcoord, None)
                if level_map is None or not level_map.clear:
                    break
                first_novel_dcoord = DCoord(first_novel_dcoord.branch, first_novel_dcoord.level + 1)
            new_targets[Branches.DungeonsOfDoom] = first_novel_dcoord

        # Sokoban
        current_dcoord = self.target_dcoords.get(Branches.Sokoban, None)
        if current_dcoord is None:
            pass
        else:
            level_map = self.dlevels.get(current_dcoord, None)
            if level_map and not level_map.clear:
                new_targets[Branches.Sokoban] = current_dcoord

        # Mines
        if character.ready_for_mines() and character.inventory.get_item(inventory.Gem, identity_selector=lambda i: i.name() == 'luckstone') is None:
            new_targets[Branches.GnomishMines] = DCoord(Branches.GnomishMines, 20)

        self.target_dcoords = new_targets        


    def add_branch_traversal(self, start_dcoord, end_dcoord):
        exists = self.branch_connections.get((start_dcoord, end_dcoord), False)
        if exists:
            return
        
        self.branch_connections[(start_dcoord, end_dcoord)] = True
        self.branch_connections[(end_dcoord, start_dcoord)] = True

    def make_level_map(self, dcoord, glyphs, initial_player_location):
        lmap = DLevelMap(dcoord)
        self.dlevels[dcoord] = lmap

        # if we just made the map of level 1 of dungeons of doom, add the staircase on our square
        if dcoord.branch == Branches.DungeonsOfDoom and dcoord.level == 1:
            lmap.add_feature(initial_player_location, gd.get_by_name(gd.CMapGlyph, 'upstair'))

        lmap.update(initial_player_location, glyphs)

        return lmap

    def add_top_target(self, target_dcoord):
        self.target_dcoords.append(target_dcoord)

    def dungeon_direction_to_best_target(self, current_dcoord):
        for branch in [Branches.Sokoban, Branches.GnomishMines, Branches.DungeonsOfDoom]:
            dcoord = self.target_dcoords.get(branch, None)
            if dcoord is None:
                continue
            heading = self.dungeon_direction_to_target(current_dcoord, dcoord)
            if heading is not None:
                return heading
        raise Exception("Can't figure out how to get anywhere")

    def dungeon_direction_to_target(self, current_dcoord, target_dcoord):
        if current_dcoord.branch == target_dcoord.branch:
            return DungeonHeading(DirectionThroughDungeon(np.sign(target_dcoord.level - current_dcoord.level)), target_dcoord.branch)

        initial_start=None
        final_start=None
        one_and_only_start=None
        #import pdb; pdb.set_trace()
        for start_dcoord, end_dcoord in self.branch_connections.keys():
            # if not relevant in any way, continue
            if start_dcoord.branch != current_dcoord.branch and end_dcoord.branch != target_dcoord.branch:
                continue

            if end_dcoord.branch == target_dcoord.branch:
                if start_dcoord.branch == current_dcoord.branch:
                    one_and_only_start = start_dcoord
                else:
                    final_start = start_dcoord
                continue # don't want to grab this as our initial leg and double count it

            if current_dcoord.branch != Branches.DungeonsOfDoom and (start_dcoord.branch == current_dcoord.branch and end_dcoord.branch == Branches.DungeonsOfDoom):
                initial_start = start_dcoord

        if one_and_only_start is not None:
            return DungeonHeading(DirectionThroughDungeon(np.sign(one_and_only_start.level - current_dcoord.level)), target_dcoord.branch)

        if initial_start is None or final_start is None:
            return None

        return DungeonHeading(DirectionThroughDungeon(np.sign(initial_start.level - current_dcoord.level)), target_dcoord.branch)

class Staircase():
    def __init__(self, dcoord, location, to_dcoord, to_location, direction):
        self.start_dcoord = dcoord
        self.start_location = location

        self.end_dcoord = to_dcoord
        self.end_location = to_location

        self.direction = direction

    def matches_heading(self, heading):
        return (self.end_dcoord.branch == heading.target_branch and not self.start_dcoord.branch == self.end_dcoord.branch) or (self.direction == heading.direction and self.end_dcoord.branch == self.start_dcoord.branch)

class TimedCorpse(NamedTuple):
    ACCEPTABLE_CORPSE_AGE = 50

    time: int
    monster_glyph: gd.MonsterGlyph

class DLevelMap():
    @staticmethod
    def glyphs_to_dungeon_features(glyphs, prior):
        # This treats the gd.CMapGlyph.OFFSET as unobserved. No way, AFAICT, to
        # distinguish between solid stone that we've seen with our own eyes vs. not

        dungeon_features = np.where(
            gd.CMapGlyph.class_mask_without_stone(glyphs),
            glyphs,
            prior
        )

        # our prior for monsters and objects is room floor
        #import pdb; pdb.set_trace()
        dungeon_features[(dungeon_features == 0) & ((gd.MonsterGlyph.class_mask(glyphs)) | (gd.ObjectGlyph.class_mask(glyphs)))] = gd.CMapGlyph.OFFSET + 19
        return dungeon_features

    def __init__(self, dcoord):
        self.dcoord = dcoord

        self.downstairs_count = 0
        self.upstairs_count = 0
        self.downstairs_target = 1
        self.upstairs_target = 1

        self.player_location = None
        self.player_location_mask = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')

        # These are our map layers
        self.dungeon_feature_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.visits_count_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.searches_count_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.special_room_map = np.full(constants.GLYPHS_SHAPE, constants.SpecialRoomTypes.NONE.value)
        self.owned_doors = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.edible_corpse_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.lootable_squares_map = np.full(constants.GLYPHS_SHAPE, True, dtype='bool')
        self.boulder_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.fountain_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.travel_attempt_count_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.exhausted_travel_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')


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
        try:
            self.edible_corpse_dict[square].pop(0)
        except:
            if environment.env.debug: import pdb; pdb.set_trace()
            return
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
        self.fountain_map = (glyphs == gd.CMapGlyph.OFFSET + 31)

        # Solid stone and fog of war both show up here
        self.fog_of_war = (glyphs == gd.CMapGlyph.OFFSET)
        adjacent_to_fog = FloodMap.flood_one_level_from_mask(self.fog_of_war)

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


        # flood special rooms in case new squares have been discovered
        for special_room_type in constants.SpecialRoomTypes:
            if special_room_type != constants.SpecialRoomTypes.NONE:
                room_mask = self.special_room_map == special_room_type.value
                expanded_mask = self.expand_mask_along_room_floor(room_mask)
                self.add_room(expanded_mask, special_room_type)

        reachable = (
            (self.safely_walkable | self.doors) &
            (~self.owned_doors) &
            (self.special_room_map == constants.SpecialRoomTypes.NONE.value)
        )

        self.frontier_squares = (
            (self.visits_count_map == 0) &
            reachable &
            (adjacent_to_fog)
        )

        self.clear = (np.count_nonzero(self.frontier_squares & ~self.exhausted_travel_map) == 0)

    def expand_mask_along_room_floor(self, mask):
        while True:
            new_mask = FloodMap.flood_one_level_from_mask(mask)
            new_mask = new_mask & self.room_floor

            if (new_mask == mask).all():
                break
            else:
                mask = new_mask

        return mask

    def build_room_mask_from_square(self, square_in_room):
        room_mask = np.full_like(self.dungeon_feature_map, False, dtype=bool)
        room_mask[square_in_room] = True

        return self.expand_mask_along_room_floor(room_mask)

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
        #import pdb; pdb.set_trace()
        for offset in physics.ortholinear_offsets:
            offset_loc = engraving_location[0] + offset[0], engraving_location[1] + offset[1]
            if self.doors[offset_loc]:
                self.owned_doors[offset_loc] = True

    def add_vault_closet(self, engraving_location):
        for offset in physics.ortholinear_offsets:
            adjacent_coord = (engraving_location[0] + offset[0], engraving_location[1] + offset[1])
            if self.walls[adjacent_coord] or self.doors[adjacent_coord]:
                room_mask = np.full_like(self.walls, False, dtype=bool)
                room_mask[engraving_location[0] + 2 * offset[0], engraving_location[1] + 2 * offset[1]] = True
                self.add_room(room_mask, constants.SpecialRoomTypes.vault_closet)

    def add_traversed_staircase(self, location, to_dcoord, to_location, direction):
        location = physics.Square(*location)
        try:
            existing = self.staircases[location]
            if existing.direction != direction:
                raise Exception("Conflicting staircases")
        except KeyError:
            staircase = Staircase(
                self.dcoord,
                location,
                to_dcoord,
                to_location,
                direction)
            self.add_feature(location, gd.get_by_name(gd.CMapGlyph, 'upstair' if direction == DirectionThroughDungeon.up else 'dnstair'))
            self.staircases[location] = staircase
            if staircase.start_dcoord.branch == Branches.DungeonsOfDoom and staircase.end_dcoord.branch == Branches.GnomishMines:
                self.downstairs_target += 1
                self.update_stair_counts()
            elif staircase.start_dcoord.branch == Branches.DungeonsOfDoom and staircase.end_dcoord.branch == Branches.Sokoban:
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
        if not mask.dtype == np.dtype('bool'):
            raise Exception("Bad mask")

        flooded_mask = scipy.signal.convolve2d(mask, np.ones((3,3)), mode='same')

        return (flooded_mask >= 1)

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
    def calculate_can_occupy(cls, monster, start, raw_glyph_grid):
        walkable = gd.walkable(raw_glyph_grid)
        if isinstance(monster, gd.MonsterGlyph):
            free_moves = np.ceil(monster.monster_spoiler.speed / monster.monster_spoiler.__class__.NORMAL_SPEED) - 1 # -1 because we are interested in move+hit turns not just move turns
            #print("speed, free_moves:", monster.monster_spoiler.speed, free_moves)
        elif isinstance(monster, gd.InvisibleGlyph):
            free_moves = 0
        
        mons_square_mask = np.full_like(raw_glyph_grid, False, dtype='bool')
        mons_square_mask[start] = True
        can_occupy_mask = mons_square_mask

        if free_moves > 0: # if we can move+attack, we need to know where we can move
            already_checked_mask = np.full_like(raw_glyph_grid, False, dtype='bool')

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
                        can_occupy_mask = self.__class__.calculate_can_occupy(glyph, it.multi_index, self.raw_glyph_grid)
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

class SpecialLevelDecoder():
    CHARACTER_SET = None
    CHARACTER_MAPPING = None

    def __init__(self):
        if self.CHARACTER_SET:
            self.character_set = set(map(lambda x: ord(x), self.CHARACTER_SET))
        else:
            self.character_mapping = {}
            for k, v in self.CHARACTER_MAPPING.items():
                self.character_mapping[ord(k)] = gd.get_by_name(gd.CMapGlyph, v).numeral

    def decode_to_bool(self, encoding):
        retval = np.zeros(constants.GLYPHS_SHAPE, dtype=bool)
        for x in range(constants.GLYPHS_SHAPE[0]):
            for y in range(constants.GLYPHS_SHAPE[1]):
                if encoding[x, y] in self.character_set:
                    retval[x, y] = True
        return retval

    def decode_to_int(self, encoding):
        retval = np.full(constants.GLYPHS_SHAPE, 2359, dtype=int)
        for x in range(constants.GLYPHS_SHAPE[0]):
            for y in range(constants.GLYPHS_SHAPE[1]):
                val = self.character_mapping.get(encoding[x, y], None)
                if val is not None:
                    retval[x, y] = val
        return retval

    def decode(self, encoding):
        if self.CHARACTER_SET:
            return self.decode_to_bool(encoding)
        else:
            return self.decode_to_int(encoding)

class CMapGlyphDecoder(SpecialLevelDecoder):
    CHARACTER_MAPPING = {
        '.': 'room', # Probably needs configuration (lit, dark, etc.)
        '<': 'upstair', # Probably needs configuration (ladder)
        '>': 'dnstair', # Probably needs configuration (ladder)
        '{': 'fountain',
        '}': 'pool', # I don't think there's a separate moat glyph
        '#': 'sink',
        '_': 'altar',
        'T': 'tree',
        'F': 'bars',
        'I': 'ice',
        'L': 'lava',
    }

class PotentialWallDecoder(SpecialLevelDecoder):
    CHARACTER_SET = [
        '-',
        '|',
        'S', # secret door
        'D', # maybe wall, maybe door
        'H', # maybe wall, maybe open
    ]

class PotentialSecretDoorDecoder(SpecialLevelDecoder):
    CHARACTER_SET = ['S']

# You should edit the map file to not include traps you're fine stepping on
# e.g. various unavoidable squeaky boards
class TrapsToAvoidDecoder(SpecialLevelDecoder):
    CHARACTER_SET = ['^']

class IDAbleStackDecoder(SpecialLevelDecoder):
    CHARACTER_SET = ['*']

class BoulderDecoder(SpecialLevelDecoder):
    CHARACTER_SET = ['0']

KNOWN_WIKI_ENCODINGS = set([ord(' ')])

for cls in SpecialLevelDecoder.__subclasses__():
    if cls.CHARACTER_SET:
        KNOWN_WIKI_ENCODINGS.update(map(ord, cls.CHARACTER_SET))
    else:
        KNOWN_WIKI_ENCODINGS.update(map(ord, cls.CHARACTER_MAPPING.keys()))

class SpecialLevelMap():
    cmap_glyph_decoder = CMapGlyphDecoder()
    potential_wall_decoder = PotentialWallDecoder()
    potential_secret_door_decoder = PotentialSecretDoorDecoder()
    traps_to_avoid_decoder = TrapsToAvoidDecoder()

    def __init__(self, config_data, nethack_wiki_encoding):
        self.level_name = config_data['level_name']
        self.level_variant = config_data['level_variant']
        self.branch = Branches.__members__[config_data['branch']]
        self.min_branch_level = config_data['min_branch_level']
        self.max_branch_level = config_data['max_branch_level']
        self.teleportable = config_data['properties']['teleportable']
        self.diggable_floor = config_data['properties']['diggable_floor']

        self.nethack_wiki_encoding = nethack_wiki_encoding
        if self.nethack_wiki_encoding.shape != constants.GLYPHS_SHAPE:
            raise Exception("Bad special level shape")

        for row in nethack_wiki_encoding:
            for char in row:
                if char not in KNOWN_WIKI_ENCODINGS:
                    raise Exception(f"Unknown character {chr(char)}")

        # These are our map layers
        self.cmap_glyphs = self.cmap_glyph_decoder.decode(nethack_wiki_encoding)
        self.potential_walls = self.potential_wall_decoder.decode(nethack_wiki_encoding)
        self.potential_secret_doors = self.potential_secret_door_decoder.decode(nethack_wiki_encoding)
        self.traps_to_avoid = self.traps_to_avoid_decoder.decode(nethack_wiki_encoding)

class SpecialLevelSearcher():
    def __init__(self, all_special_levels: list[SpecialLevelMap]):
        self.lookup = defaultdict(lambda: defaultdict(lambda: []))
        self.level_found = {}
        for level in all_special_levels:
            self.level_found[level.level_name] = False
            for depth in range(level.min_branch_level, level.max_branch_level + 1):
                self.lookup[level.branch][depth].append(level)

    def match_level(self, level_map: DLevelMap):
        possible_matches = self.lookup[level_map.dcoord.branch][level_map.dcoord.level]
        for possible_match in possible_matches:
            if np.count_nonzero(level_map.walls & ~possible_match.potential_walls):
                continue

            known_cmap_mask = (possible_match.cmap_glyphs != 2359)
            if np.count_nonzero((level_map.dungeon_feature_map != possible_match.cmap_glyphs)[known_cmap_mask]):
                continue

            if np.count_nonzero(level_map.walls & ~possible_match.potential_walls) > 8:
                return possible_match

class SpecialLevelLoader():
    @staticmethod
    def load(level_name):
        with open(os.path.join(os.path.dirname(__file__), "spoilers", "special_levels", f"{level_name}.txt"), 'r') as f:
            characters = f.readlines()
        with open(os.path.join(os.path.dirname(__file__), "spoilers", "special_levels", f"{level_name}.json"), 'r') as f:
            properties = json.load(f)
        return SpecialLevelMap(properties, SpecialLevelLoader.make_character_array(characters))

    @staticmethod
    def make_character_array(characters):
        # Space (i.e. ' ') means no observation
        retval = np.full(constants.GLYPHS_SHAPE, ord(' '), dtype=int)

        offset_x = 0
        offset_y = 0

        for line in characters:
            for character in line.strip("\n"):
                retval[offset_y, offset_x] = ord(character)
                offset_x += 1
            offset_x = 0
            offset_y += 1

        return retval

