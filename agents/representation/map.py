from collections import defaultdict
from dataclasses import dataclass
import enum
from typing import NamedTuple, List
import json
import os

import numpy as np
import scipy.signal

import environment
import agents.representation.glyphs as gd
import agents.representation.inventory as inventory
import agents.representation.physics as physics
import utilities
import agents.representation.constants as constants
from agents.representation.spoilers.special_levels.sokoban_solutions import SOKOBAN_SOLUTIONS

import functools
from utilities import ARS

# TODO: I am not sure these ints are constant across nethack games
class Branches(enum.IntEnum):
    DungeonsOfDoom = 0
    Gehennom = 1
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
    next_new_branch: Branches

class DMap():
    def __init__(self):
        self.dlevels = {}
        self.target_dcoords = {
            Branches.DungeonsOfDoom: DCoord(Branches.DungeonsOfDoom, 1),
            Branches.Sokoban: DCoord(Branches.Sokoban, 1),
        }
        self.branch_connections = {}
        self.oracle_level = None
        self.special_level_searcher = SpecialLevelSearcher(ALL_SPECIAL_LEVELS)
        self.handled_facts = {}

    def report_special_fact_handled(self, fact):
        self.handled_facts[fact.name] = True
        if fact.name == 'sokoban_prize':
            #import pdb; pdb.set_trace()
            self.target_dcoords.pop(Branches.Sokoban)

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
            if level_map and level_map.special_level and not level_map.solved:
                new_targets[Branches.Sokoban] = current_dcoord

        # Mines
        if character.eager_for_mines1():
            new_targets[Branches.GnomishMines] = DCoord(Branches.GnomishMines, 1)
        if character.ready_for_mines() and character.inventory.get_item(inventory.Gem, identity_selector=lambda i: i.name() == 'luckstone') is None:
            new_targets[Branches.GnomishMines] = DCoord(Branches.GnomishMines, 20)

        self.target_dcoords.update(new_targets)


    def add_branch_traversal(self, start_dcoord, end_dcoord):
        exists = self.branch_connections.get((start_dcoord, end_dcoord), False)
        if exists:
            return
        
        self.branch_connections[(start_dcoord, end_dcoord)] = True
        self.branch_connections[(end_dcoord, start_dcoord)] = True

    def make_level_map(self, dcoord, time, glyphs, initial_player_location):
        lmap = DLevelMap(self.special_level_searcher, dcoord, time)
        self.dlevels[dcoord] = lmap

        # if we just made the map of level 1 of dungeons of doom, add the staircase on our square
        if dcoord.branch == Branches.DungeonsOfDoom and dcoord.level == 1:
            lmap.add_feature(initial_player_location, gd.get_by_name(gd.CMapGlyph, 'upstair'))

        lmap.update(True, time, initial_player_location, glyphs)

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
        if current_dcoord.branch == Branches.Sokoban:
            #import pdb; pdb.set_trace()
            pass
        if current_dcoord.branch == target_dcoord.branch:
            return DungeonHeading(
                direction=DirectionThroughDungeon(np.sign(target_dcoord.level - current_dcoord.level)),
                target_branch=target_dcoord.branch,
                next_new_branch=None,
            )

        # We are now in the case that we need a branch connection.
        # This pathfinding logic assumes that either
        # (A) We need a single branch connection or
        # (B) We need two, where we go through the Dungeons of Doom
        initial_start=None
        final_start=None
        one_and_only_start=None
        for connection_start, connection_end in self.branch_connections.keys():
            # if not relevant in any way, continue
            if connection_start.branch != current_dcoord.branch and connection_end.branch != target_dcoord.branch:
                continue

            if connection_end.branch == target_dcoord.branch:
                if connection_start.branch == current_dcoord.branch:
                    one_and_only_start = connection_start
                elif connection_start.branch == Branches.DungeonsOfDoom:
                    final_start = connection_start
                continue # don't want to grab this as our initial leg and double count it

            if (
                current_dcoord.branch != Branches.DungeonsOfDoom and
                (connection_start.branch == current_dcoord.branch and connection_end.branch == Branches.DungeonsOfDoom)
            ):
                initial_start = connection_start

        if one_and_only_start is not None:
            return DungeonHeading(
                direction=DirectionThroughDungeon(np.sign(one_and_only_start.level - current_dcoord.level)),
                target_branch=target_dcoord.branch,
                next_new_branch=target_dcoord.branch,
            )

        if initial_start is None or final_start is None:
            return None

        return DungeonHeading(
            direction=DirectionThroughDungeon(np.sign(initial_start.level - current_dcoord.level)),
            target_branch=target_dcoord.branch,
            next_new_branch=final_start.branch,
        )

class Staircase():
    def __init__(self, dcoord, location, to_dcoord, to_location, direction):
        self.start_dcoord = dcoord
        self.start_location = location

        self.end_dcoord = to_dcoord
        self.end_location = to_location

        self.direction = direction

    def matches_heading(self, heading):
        return (
            (self.end_dcoord.branch == heading.next_new_branch and not self.start_dcoord.branch == self.end_dcoord.branch) or
            (self.direction == heading.direction and self.end_dcoord.branch == self.start_dcoord.branch)
        )

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

    def __init__(self, special_level_searcher, dcoord, time):
        self.dcoord = dcoord
        self.special_level_searcher = special_level_searcher
        self.special_level = None
        self.clear = False
        self.diggable_floor = True
        self.teleportable = True

        self.downstairs_count = 0
        self.upstairs_count = 0
        self.downstairs_target = 1
        self.upstairs_target = 1

        self.player_location = None
        self.player_location_mask = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')

        self.time_of_recent_arrival = time
        self.time_of_new_square = time

        # These are our map layers
        self.dungeon_feature_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.visits_count_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.searches_count_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.special_room_map = np.full(constants.GLYPHS_SHAPE, constants.SpecialRoomTypes.NONE.value)
        self.owned_doors = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.edible_corpse_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.lootable_squares_map = np.full(constants.GLYPHS_SHAPE, True, dtype='bool')
        self.boulder_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.obvious_mimics = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.fountain_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.altar_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.travel_attempt_count_map = np.zeros(constants.GLYPHS_SHAPE, dtype=int)
        self.exhausted_travel_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.traps_to_avoid = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')
        self.embedded_object_map = np.full(constants.GLYPHS_SHAPE, False, dtype='bool')

        self.staircases = {}
        self.edible_corpse_dict = defaultdict(list)
        self.warning_engravings = {}
        self.special_facts = {}

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
    
    def update(self, changed_level, time, player_location, glyphs, last_action_menu=False):

        if changed_level:
            self.time_of_recent_arrival = time

        self.dungeon_feature_map = self.glyphs_to_dungeon_features(glyphs, self.dungeon_feature_map)

        self.boulder_map = (glyphs == gd.RockGlyph.OFFSET)
        self.obvious_mimics = gd.RandomClassGlyph.class_mask(glyphs)
        if self.dcoord.branch == Branches.Sokoban and self.special_level is not None:
            self.obvious_mimics |= ~self.sokoban_boulders & self.boulder_map

        # Basic terrain types

        offsets = np.where(
            self.dungeon_feature_map != 0,
            self.dungeon_feature_map - gd.CMapGlyph.OFFSET,
            0 # solid stone / unseen
        )

        self.walls = gd.CMapGlyph.is_wall_check(offsets)
        self.observed_walls = gd.CMapGlyph.is_observed_wall_check(offsets)
        self.room_floor = gd.CMapGlyph.is_room_floor_check(offsets)
        self.safely_walkable = gd.CMapGlyph.is_safely_walkable_check(offsets)
        self.doors = gd.CMapGlyph.is_door_check(offsets)
        self.traps_to_avoid = gd.CMapGlyph.is_trap_to_avoid_check(offsets)
        if self.special_level:
            self.traps_to_avoid |= self.special_level.traps_to_avoid
        self.fountain_map = (offsets == 31)
        self.altar_map = (offsets == 27)

        # Solid stone and fog of war both show up here
        self.fog_of_war = (offsets == 0)
        adjacent_to_fog = FloodMap.flood_one_level_from_mask(self.fog_of_war)

        # once we're happy with our Sokoban performance and don't need to seed, switch this to using the dungeon feature map
        self.possible_secrets = gd.CMapGlyph.is_possible_secret_check(glyphs - gd.CMapGlyph.OFFSET)
        if self.special_level is not None:
            self.possible_secrets &= self.special_level.potential_secret_doors

        if np.count_nonzero(gd.CMapGlyph.is_poorly_understood_check(offsets)):
            if environment.env.debug: import pdb; pdb.set_trace()
            pass

        # This is expensive. If we don't get long-term utility from these, should delete it
        self.update_stair_counts()
        old_player_location = self.player_location
        self.player_location = player_location
        if self.visits_count_map[self.player_location] == 0:
            self.time_of_new_square = time
        if environment.env.debug and not self.clear and (time - self.time_of_new_square > 1_000) and (time - self.time_of_recent_arrival > 1_000):
            #import pdb; pdb.set_trace()
            pass
        if self.visits_count_map[self.player_location] == 0:
            self.visits_count_map[self.player_location] += 1
        else:
            if last_action_menu is False:
                self.visits_count_map[self.player_location] += 1
        self.player_location_mask[old_player_location] = False
        self.player_location_mask[player_location] = True


        # flood special rooms in case new squares have been discovered
        for special_room_type in constants.SpecialRoomTypes:
            if special_room_type != constants.SpecialRoomTypes.NONE:
                room_mask = self.special_room_map == special_room_type.value
                if not room_mask.any():
                    continue
                expanded_mask = self.expand_mask_along_room_floor(room_mask)
                self.add_room(expanded_mask, special_room_type)

        reachable = (
            (self.safely_walkable | self.doors) &
            (~self.owned_doors) &
            (self.special_room_map == constants.SpecialRoomTypes.NONE.value) &
            (~self.embedded_object_map)
        )

        self.frontier_squares = (
            (self.visits_count_map == 0) &
            reachable &
            (adjacent_to_fog)
        )

        self.clear = (np.count_nonzero(self.frontier_squares & ~self.exhausted_travel_map) == 0)

        if self.special_level is None:
            self.special_level = self.special_level_searcher.match_level(self, player_location)
            if self.dcoord.branch == Branches.Sokoban and environment.env.debug:
                import pdb; pdb.set_trace()
            if self.special_level is not None:
                self.diggable_floor = self.special_level.diggable_floor
                self.teleportable = self.special_level.teleportable
                if self.special_level.branch == Branches.Sokoban:
                    self.sokoban_boulders = self.special_level.initial_boulders
                    self.sokoban_move_index = 0
                    self.solved = False

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

    def log_stethoscope_search(self, location):
        self.searches_count_map[location] = 1000

    def log_search(self, player_location):
        if player_location != self.player_location:
            if environment.env.debug:
                import pdb; pdb.set_trace()
            raise Exception("Player locations should match")
        search_mask = FloodMap.flood_one_level_from_mask(self.player_location_mask)
        self.searches_count_map[search_mask] += 1

    @staticmethod
    def is_square_mask(absolute_square):
        mask = np.full(constants.GLYPHS_SHAPE, False, dtype=bool)
        mask[absolute_square] = True
        return mask

    def listen_for_special_engraving(self, player_location, message):
        if self.special_level is None:
            return None
        if self.special_level.special_engravings is None:
            return None
        if self.visits_count_map[player_location] != 1:
            return None
        for engraving,fact_name in self.special_level.special_engravings.items():
            if engraving not in message:
                continue
            #import pdb; pdb.set_trace()
            facts = SPECIAL_FACTS[fact_name]
            self.add_special_facts(player_location, facts)
            return facts

    def report_special_fact_handled(self, player_location, fact):
        self.special_facts[player_location].remove(fact)
        if len(self.special_facts[player_location]) == 0:
            self.special_facts[player_location] = None

    def add_special_facts(self, location, facts):
        self.special_facts[location] = facts

class FloodMap():
    @staticmethod
    def flood_one_level_from_mask(mask):
        if not mask.dtype == np.dtype('bool'):
            raise Exception("Bad mask")

        flooded_mask = scipy.signal.convolve2d(mask, np.ones((3,3)), mode='same')

        return (flooded_mask >= 1)

class ThreatMap(FloodMap):
    INVISIBLE_DAMAGE_THREAT = 6 # gotta do something lol

    def __init__(self, character, raw_visible_glyphs, monsters, monster_squares, player_location_in_vision):
        # take the section of the observed glyphs that is relevant
        self.raw_glyph_grid = raw_visible_glyphs
        self.monsters = monsters
        self.monster_squares = monster_squares
        self.player_location_in_glyph_grid = player_location_in_vision

        self.calculate_threat(character)
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

    def calculate_threat(self, character):
        melee_n_threat = np.zeros_like(self.raw_glyph_grid)
        melee_damage_threat = np.zeros_like(self.raw_glyph_grid, dtype=float)
        melee_threat_type = np.zeros_like(self.raw_glyph_grid, dtype=int)

        ranged_n_threat = np.zeros_like(self.raw_glyph_grid)
        ranged_damage_threat = np.zeros_like(self.raw_glyph_grid, dtype=float)
        ranged_threat_type = np.zeros_like(self.raw_glyph_grid, dtype=int)

        for i, monster in enumerate(self.monsters):
            monster_square = physics.Square(self.monster_squares[0][i], self.monster_squares[1][i])
            if isinstance(monster, gd.SwallowGlyph):
                swallowing_monster = gd.GLYPH_NUMERAL_LOOKUP[monster.swallowing_monster_offset]
                # while we're swallowed, all threat can be homogeneous
                engulf_damage, engulf_types = swallowing_monster.monster_spoiler.expected_engulf_damage_to_character(character)
                melee_damage_threat.fill(engulf_damage)
                melee_threat_type.fill(engulf_types)
                # we're only ever threatened once while swallowed
                melee_n_threat.fill(1)

            is_invis = isinstance(monster, gd.InvisibleGlyph)
            if isinstance(monster, gd.MonsterGlyph) or is_invis:
                if not (isinstance(monster, gd.MonsterGlyph) and monster.single_always_peaceful()): # always peaceful monsters don't need to threaten
                    ### SHARED ###
                    can_occupy_mask = self.calculate_can_occupy(monster, monster_square, self.raw_glyph_grid)
                    ###

                    ### MELEE ###
                    if is_invis or monster.has_melee:
                        can_hit_mask = self.calculate_melee_can_hit(can_occupy_mask)

                        melee_n_threat[can_hit_mask] += 1 # monsters threaten their own squares in this implementation OK? TK 

                        if isinstance(monster, gd.MonsterGlyph):
                            melee_damage, melee_types = monster.monster_spoiler.expected_melee_damage_to_character(character)
                            melee_damage_threat[can_hit_mask] += melee_damage
                            melee_threat_type[can_hit_mask] = np.bitwise_or(melee_threat_type[can_hit_mask], melee_types)
                        elif is_invis:
                            melee_damage_threat[can_hit_mask] += self.INVISIBLE_DAMAGE_THREAT # how should we imagine the threat of invisible monsters?
                        else:
                            assert False, "what kinda monster is this?"
                    ###

                    ### RANGED ###
                    if is_invis or monster.has_ranged: # let's let invisible monsters threaten at range so we rush them down someday
                        can_hit_mask = self.calculate_ranged_can_hit_mask(can_occupy_mask, self.raw_glyph_grid)
                        ranged_n_threat[can_hit_mask] += 1
                        if is_invis:
                            ranged_damage_threat[can_hit_mask] += self.INVISIBLE_DAMAGE_THREAT
                        else:
                            ranged_damage, ranged_types = monster.monster_spoiler.expected_ranged_damage_to_character(character)
                            ranged_damage_threat[can_hit_mask] += ranged_damage
                            ranged_threat_type[can_hit_mask] = np.bitwise_or(ranged_threat_type[can_hit_mask], ranged_types)
                    ###

        self.melee_n_threat = melee_n_threat
        self.melee_damage_threat = melee_damage_threat
        self.melee_threat_type = melee_threat_type

        self.ranged_n_threat = ranged_n_threat
        self.ranged_damage_threat = ranged_damage_threat
        self.ranged_threat_type = ranged_threat_type

        #if self.ranged_threat_type.any():
        #    import pdb; pdb.set_trace()

    @classmethod
    def calculate_ranged_can_hit_mask(cls, can_occupy_mask, glyph_grid, attack_range=None, **kwargs):
        # TODO make gaze attacks hit everywhere
        it = np.nditer(can_occupy_mask, flags=['multi_index'])
        masks = []
        for b in it: 
            if b:
                can_hit_from_loc = cls.raytrace_from(physics.Square(*it.multi_index), glyph_grid, **kwargs)
                masks.append(can_hit_from_loc)
        return np.logical_or.reduce(masks)

    @staticmethod
    def raytrace_from(source, glyph_grid, include_adjacent=False, stop_on_monsters=False, reject_peaceful=False, stop_on_boulders=True):
        row_lim = glyph_grid.shape[0]
        col_lim = glyph_grid.shape[1]

        blocking_geometry = gd.CMapGlyph.wall_mask(glyph_grid) | gd.CMapGlyph.closed_door_mask(glyph_grid)
        if stop_on_boulders:
            blocking_geometry |= gd.RockGlyph.boulder_mask(glyph_grid)
        if reject_peaceful:
            blocking_geometry |= (gd.PetGlyph.class_mask(glyph_grid) | gd.MonsterGlyph.always_peaceful_mask(glyph_grid))
        if stop_on_monsters:
            blocking_geometry |= gd.MonsterGlyph.class_mask(glyph_grid)

        ray_offsets = physics.action_deltas

        masks = []
        for offset in ray_offsets:
            ray_mask = np.full_like(glyph_grid, False, dtype='bool')

            current = source
            current = current + physics.Square(*offset) # initial bump so that ranged attacks don't threaten adjacent squares
            while 0 <= current[0] < row_lim and 0 <= current[1] < col_lim:
                blocked = blocking_geometry[current]
                ray_mask[current] = True # moved before blocking since technically you can hit things in walls with ranged attacks
                if blocked: # is this the full extent of what blocks projectiles/rays?
                    break # should we do anything with bouncing rays


                current = (current[0]+offset[0], current[1]+offset[1])

            masks.append(ray_mask)

        can_hit_mask = np.logical_or.reduce(masks)

        if not include_adjacent:
            adjacent_rows, adjacent_cols = utilities.centered_slices_bounded_on_array(source, (1,1), can_hit_mask)
            can_hit_mask[adjacent_rows, adjacent_cols] = False
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
        # '.': 'room', # Too much confusion about room / dark room
        # '~': 'darkroom', # Too much confusion about room / dark room
        '<': 'upstair', # Probably needs configuration (ladder)
        '>': 'dnstair', # Probably needs configuration (ladder)
        '{': 'fountain',
        # '}': 'pool', # No moat glyph? Skipping this because swimming/flying monsters cover it
        # '#': '', # Not sure if corridors will be a thing. Drawbridge definitely is.
        '_': 'altar',
        'T': 'tree',
        'F': 'bars',
        'I': 'ice',
        'L': 'lava',
        '\\': 'throne',
    }

class PotentialWallDecoder(SpecialLevelDecoder):
    CHARACTER_SET = [
        '-',
        '|',
        'S', # secret door
        'D', # maybe wall, maybe door
        'H', # maybe wall, maybe open
    ]

class DoorDecoder(SpecialLevelDecoder):
    CHARACTER_SET = ['+']

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

class RoomDecoder(SpecialLevelDecoder):
    CHARACTER_SET = ['.', '~'] # Lit, Dark

class IgnoredFeatureDecoder(SpecialLevelDecoder):
    CHARACTER_SET = ['}', '#']

class UnobservedDecoder(SpecialLevelDecoder):
    CHARACTER_SET = [' ']

KNOWN_WIKI_ENCODINGS = set()

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
    boulder_decoder = BoulderDecoder()
    unobserved_decoder = UnobservedDecoder()

    def __repr__(self) -> str:
        return self.id

    def __init__(self, config_data, nethack_wiki_encoding, initial_offset=(0,0)):
        self.level_name = config_data['level_name']
        self.level_variant = config_data['level_variant']
        self.id = f"{self.level_name}/{self.level_variant}"
        self.branch = Branches.__members__[config_data['branch']]
        self.min_branch_level = config_data['min_branch_level']
        self.max_branch_level = config_data['max_branch_level']
        self.teleportable = config_data['properties']['teleportable']
        self.diggable_floor = config_data['properties']['diggable_floor']
        try:
            self.special_engravings = config_data['special_engravings']
            print(self.special_engravings)
        except KeyError:
            self.special_engravings = None
        self.initial_offset = physics.Square(*initial_offset)

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
        self.adjacent_to_secret = FloodMap.flood_one_level_from_mask(self.potential_secret_doors)
        self.traps_to_avoid = self.traps_to_avoid_decoder.decode(nethack_wiki_encoding)
        self.unobserved = self.unobserved_decoder.decode(nethack_wiki_encoding)

        if self.branch == Branches.Sokoban:
            self.sokoban_solution = SOKOBAN_SOLUTIONS[(self.level_name, self.level_variant)]
            self.traps_to_avoid = np.full_like(self.traps_to_avoid, False, dtype=bool)
            self.initial_boulders = self.boulder_decoder.decode(nethack_wiki_encoding)

    def offset_in_level(self, absolute):
        return absolute - self.initial_offset

class SpecialLevelSearcher():
    def __init__(self, all_special_levels: List[SpecialLevelMap]):
        self.lookup = defaultdict(lambda: defaultdict(lambda: []))
        self.level_found = {}
        self.ruled_out_for_dcoord = defaultdict(lambda: set())
        for level in all_special_levels:
            self.level_found[level.level_name] = False
            for depth in range(level.min_branch_level, level.max_branch_level + 1):
                self.lookup[level.branch][depth].append(level)

    def match_level(self, level_map: DLevelMap, player_location, verbose=True):
        possible_matches = self.lookup[level_map.dcoord.branch][level_map.dcoord.level]
        for possible_match in possible_matches:
            if possible_match.id in self.ruled_out_for_dcoord[level_map.dcoord]:
                continue
            verbose_message = f"Trying to match {level_map.dcoord} to {possible_match.id} on pre-offset location of {(player_location[0] - possible_match.initial_offset[0], player_location[1] - possible_match.initial_offset[1])}"

            too_many_walls = (level_map.observed_walls & ~possible_match.potential_walls & ~possible_match.unobserved)
            if np.count_nonzero(too_many_walls):
                self.ruled_out_for_dcoord[level_map.dcoord].add(possible_match.id)
                if verbose:
                    print(f"{verbose_message} -- Miss on extra walls")
                continue

            mismatched_features = (
                (level_map.dungeon_feature_map != possible_match.cmap_glyphs) &
                (possible_match.cmap_glyphs != 2359) &
                (level_map.dungeon_feature_map != 0)
            )
            if np.count_nonzero(mismatched_features):
                if verbose:
                    print(f"{verbose_message} -- Miss on mismatched features")
                continue

            wall_hits = (level_map.observed_walls & possible_match.potential_walls)

            if np.count_nonzero(wall_hits) > 8:
                print(f"{verbose_message} -- HIT")
                #import pdb; pdb.set_trace()
                self.level_found[possible_match.level_name] = True
                return possible_match
            else:
                if verbose:
                    print(f"{verbose_message} -- Miss on {np.count_nonzero(wall_hits)} wall hits")

class SpecialLevelLoader():
    @staticmethod
    def load(level_name):
        with open(os.path.join(os.path.dirname(__file__), "spoilers", "special_levels", f"{level_name}.txt"), 'r') as f:
            characters = f.readlines()
        with open(os.path.join(os.path.dirname(__file__), "spoilers", "special_levels", f"{level_name}.json"), 'r') as f:
            properties = json.load(f)

        initial_offset = SpecialLevelLoader.make_initial_offset(level_name, characters, properties["geometry_horizontal"], properties["geometry_vertical"])
        return SpecialLevelMap(
            properties,
            SpecialLevelLoader.make_character_array(initial_offset, characters),
            initial_offset = initial_offset,
        )

    @staticmethod
    def make_initial_offset(level_name, characters, geometry_horizontal, geometry_vertical):
        if not (geometry_horizontal == "center"):
            raise Exception("Don't know how to handle other horizontal geometries yet")

        if not (geometry_vertical == "center" or geometry_vertical == "bottom"):
            raise Exception("Don't know how to handle other vertical geometries yet")

        map_height = len(characters)
        map_length = max(map(lambda x: len(x.strip("\n")), characters))

        initial_offset_x = (constants.GLYPHS_SHAPE[1] - map_length) // 2

        # TODO figure out this pattern at some point
        hardcoded_y_offsets = {
            11: 5,
            12: 5,
            13: 5,
            14: 5,
            17: 3,
            18: 3,
            19: 2,
            20: 1,
            21: 0,
        }

        hardcoded_x_offsets = {
            14: 32,
            15: 32,
            20: 30,
            26: 26,
            29: 24,
            63: 8,
            69: 5,
            75: 2,
            76: 2,
            77: 1,
        }

        if geometry_vertical == "center":
            offset_y = hardcoded_y_offsets[map_height]
        else:
            offset_y = 21 - map_height

        try:
            offset_x = hardcoded_x_offsets[map_length]
        except KeyError:
            print(f"Guessing offset for {level_name}. Should burn in {map_length}:{initial_offset_x}")
            offset_x = initial_offset_x

        #row, col
        return (offset_y, offset_x)

    @staticmethod
    def make_character_array(initial_offset, characters):
        initial_offset_y, initial_offset_x = initial_offset
        offset_x = initial_offset_x
        offset_y = initial_offset_y

        # Space (i.e. ' ') means no observation
        retval = np.full(constants.GLYPHS_SHAPE, ord(' '), dtype=int)

        for line in characters:
            for character in line.strip("\n"):
                retval[offset_y, offset_x] = ord(character)
                offset_x += 1
            offset_x = initial_offset_x
            offset_y += 1

        return retval

class SpecialFact():
    def __init__(self, name) -> None:
        self.name = name

class SingleItemFact(NamedTuple):
    item_class: type
    item_name: str

class StackFact(SpecialFact):
    def __init__(self, name, items) -> None:
        super().__init__(name)
        self.items = items

SPECIAL_FACTS = {
    "sokoban_prize": [StackFact("sokoban_prize", [SingleItemFact(inventory.Tool, "bag of holding"), SingleItemFact(inventory.Amulet, "amulet of reflection")])],
}

ALL_SPECIAL_LEVELS = [
    SpecialLevelLoader.load('sokoban_1a'),
    SpecialLevelLoader.load('sokoban_1b'),
    SpecialLevelLoader.load('sokoban_2a'),
    SpecialLevelLoader.load('sokoban_2b'),
    SpecialLevelLoader.load('sokoban_3a'),
    SpecialLevelLoader.load('sokoban_3b'),
    SpecialLevelLoader.load('sokoban_4a'),
    SpecialLevelLoader.load('sokoban_4b'),
    SpecialLevelLoader.load('mines_end_catacomb'),
    SpecialLevelLoader.load('mines_end_mimic'),
    SpecialLevelLoader.load('mines_end_winecellar'),
    SpecialLevelLoader.load('medusa_1'),
    SpecialLevelLoader.load('medusa_2'),
    SpecialLevelLoader.load('medusa_3'),
    SpecialLevelLoader.load('medusa_4'),
    SpecialLevelLoader.load('castle'),
    SpecialLevelLoader.load('valley'),
    SpecialLevelLoader.load('sanctum'),
]

if len(set(map(lambda x: x.id, ALL_SPECIAL_LEVELS))) < len(ALL_SPECIAL_LEVELS):
    raise Exception("Duplicated special level IDs")
