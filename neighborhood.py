from dataclasses import dataclass, field
from typing import NamedTuple

import enum

from astar import AStar
import math
from nle import nethack
import numpy as np
import scipy.signal

import constants
import environment
import glyphs as gd
import map
import physics
import utilities
from utilities import ARS
from physics import Square
from typing import NamedTuple, Tuple, List
import inventory

class Targets(NamedTuple):
    monsters: list
    directions: list
    absolute_positions: list

@dataclass
class CurrentSquare:
    dcoord: Tuple[int, int]
    location: Tuple[int, int]
    arrival_time: int
    glyph_under_player: gd.Glyph = None
    stack_on_square: bool = False
    item_on_square: inventory.Item = None
    failed_moves_on_square: List[int] = field(default_factory=list)
    special_facts: list = None

class ViewField(enum.Enum):
    Local = enum.auto()
    Extended = enum.auto()

class Neighborhood(): # goal: mediates all access to glyphs by advisors
    extended_vision = 3

    def zoom_glyph_alike(self, glyph_alike, zoom_to):
        if glyph_alike.shape != constants.GLYPHS_SHAPE:
            raise Exception("Bad glyph alike")
        if zoom_to == ViewField.Local:
            return glyph_alike[self.vision][self.neighborhood_view]
        elif zoom_to == ViewField.Extended:
            return glyph_alike[self.vision]
        else:
            raise Exception("Bad view field")

    @staticmethod
    def extended_position_to_absolute(extended_position, player_location_in_extended, absolute_player_location):
        offset = extended_position - player_location_in_extended
        return absolute_player_location + offset

    def __init__(self, time, current_square, glyphs, level_map, character, latest_monster_flight, am_hallu):
        ###################
        ### COPY FIELDS ###
        ###################

        self.current_player_square = current_square
        absolute_player_location = Square(*current_square.location)

        self.previous_glyph_on_player = current_square.glyph_under_player
        self.item_on_player = current_square.item_on_square
        self.absolute_player_location = absolute_player_location
        self.dcoord = level_map.dcoord
        self.level_map = level_map
        self.dungeon_glyph_on_player = self.level_map.get_dungeon_glyph(absolute_player_location)
        self.stack_on_square = current_square.stack_on_square

        on_doorway = bool(self.dungeon_glyph_on_player and self.dungeon_glyph_on_player.is_open_door)

        #############################
        ### FULL EXTENT OF VISION ###
        #############################
        self.vision = utilities.centered_slices_bounded_on_array(
            absolute_player_location, (self.extended_vision, self.extended_vision), glyphs
        )
        vision_start = Square(self.vision[0].start, self.vision[1].start)

        extended_visible_raw_glyphs = glyphs[self.vision]
        self.vision_glyphs = extended_visible_raw_glyphs
        # index of player in the full vision
        player_location_in_extended = absolute_player_location - vision_start
        self.player_location_in_extended = player_location_in_extended

        ####################
        # SHOPKEEPER STUFF #
        ####################
        if not am_hallu:
            # don't create shops while we're hallucinating
            is_shopkeeper = gd.MonsterGlyph.shopkeeper_mask(extended_visible_raw_glyphs)
            shopkeeper_present = is_shopkeeper.any()

            if shopkeeper_present:
                it = np.nditer(is_shopkeeper, flags=['multi_index'])
                for b in it:
                    if b: # if this is a shopkeeper
                        absolute_shopkeeper_position = self.extended_position_to_absolute(Square(*it.multi_index), self.player_location_in_extended, absolute_player_location)
                        level_map.add_room_from_square(absolute_shopkeeper_position, constants.SpecialRoomTypes.shop)

        extended_special_rooms = level_map.special_room_map[self.vision]
        self.in_shop = extended_special_rooms[self.player_location_in_extended] == constants.SpecialRoomTypes.shop.value

        ###################################
        ### RELATIVE POSITION IN VISION ###
        ###################################

        extended_visits = level_map.visits_count_map[self.vision]
        extended_open_door = gd.CMapGlyph.open_door_mask(extended_visible_raw_glyphs)
        self.extended_embeds = self.zoom_glyph_alike(
            level_map.embedded_object_map,
            ViewField.Extended
        )
        dungeon_features = self.zoom_glyph_alike(self.level_map.dungeon_feature_map, ViewField.Extended)
        extended_walkable_tile = np.where(
            dungeon_features != 0,
            gd.walkable(dungeon_features),
            False
        )
        extended_walkable_tile &= ~self.extended_embeds
        extended_walkable_tile[self.player_location_in_extended] = False # in case we turn invisible

        self.extended_boulders = self.zoom_glyph_alike(
            level_map.boulder_map,
            ViewField.Extended
        )
        self.obvious_mimics = self.zoom_glyph_alike(self.level_map.obvious_mimics, ViewField.Extended)
        extended_nasty_traps = self.zoom_glyph_alike(self.level_map.traps_to_avoid, ViewField.Extended)

        extended_is_monster = gd.monster_like_mask(extended_visible_raw_glyphs)
        extended_is_monster[player_location_in_extended] = False # player does not count as a monster anymore
        if self.level_map.dcoord.branch == map.Branches.Sokoban:
            extended_is_monster[self.obvious_mimics] = True

        imprudent = extended_nasty_traps | (extended_special_rooms == constants.SpecialRoomTypes.vault_closet.value) | self.obvious_mimics | extended_is_monster
        if level_map.dcoord.branch == map.Branches.Sokoban:
            imprudent |= self.extended_boulders
        prudent_walkable = extended_walkable_tile & ~imprudent
        if extended_nasty_traps.any():
            #import pdb; pdb.set_trace()
            pass
        self.extended_walkable = extended_walkable_tile
        self.imprudent = imprudent

        self.extended_is_monster = extended_is_monster
        #import pdb; pdb.set_trace()
        monsters = np.where(extended_is_monster, extended_visible_raw_glyphs, False)
        extended_is_dangerous_monster = np.full_like(monsters, False, dtype=bool)
        extended_is_dangerous_monster[self.extended_is_monster] = utilities.vectorized_map(
            lambda g: isinstance(gd.GLYPH_NUMERAL_LOOKUP[g], gd.MonsterGlyph) and character.fearful_tier(gd.GLYPH_NUMERAL_LOOKUP[g].monster_spoiler.tier),
            monsters[self.extended_is_monster]
        )
        #if extended_is_dangerous_monster.any():
            #import pdb; pdb.set_trace()
        #    pass
        self.extended_is_dangerous_monster = extended_is_dangerous_monster
        self.extended_is_peaceful_monster = gd.MonsterGlyph.always_peaceful_mask(extended_visible_raw_glyphs)
        self.extended_possible_secret_mask = self.zoom_glyph_alike(self.level_map.possible_secrets, ViewField.Extended)
        self.extended_has_item_stack = gd.stackable_mask(extended_visible_raw_glyphs)

        self.extended_is_hostile_monster = self.extended_is_monster & ~self.extended_is_peaceful_monster

        # radius 1 box around player in vision glyphs
        neighborhood_view = utilities.centered_slices_bounded_on_array(player_location_in_extended, (1, 1), extended_visible_raw_glyphs)
        self.neighborhood_view = neighborhood_view

        ##############################
        ### RESTRICTED ACTION GRID ###
        ##############################

        # a window into the action grid of the size size and shape as our window into the glyph grid (ie: don't include actions out of bounds on the map)
        action_grid_rows, action_grid_cols = utilities.move_slice_center(player_location_in_extended, (1,1), neighborhood_view) # move center to (1,1) (action grid center)
        action_grid_view = (action_grid_rows, action_grid_cols)
        action_grid_start = Square(action_grid_rows.start, action_grid_cols.start)

        self.action_grid = physics.action_grid[action_grid_view]
        self.diagonal_moves = physics.diagonal_moves[action_grid_view]

        ########################################
        ### RELATIVE POSITION IN ACTION GRID ###
        ########################################

        self.local_player_location = Square(1,1) - action_grid_start # not always guranteed to be (1,1) if we're at the edge of the map

        #######################
        ### THE LOCAL STUFF ###
        #######################

        self.glyphs = extended_visible_raw_glyphs[neighborhood_view]
        self.visits = extended_visits[neighborhood_view]
        is_open_door = extended_open_door[neighborhood_view]
        self.is_monster = (self.extended_is_hostile_monster)[neighborhood_view]
        self.n_adjacent_monsters = np.count_nonzero(self.is_monster)

        #floating_eyes = gd.MonsterGlyph.floating_eye_mask(self.raw_glyphs)
        #if floating_eyes.any():
        #    import pdb; pdb.set_trace()

        self.local_possible_secret_mask = self.extended_possible_secret_mask[neighborhood_view]
        self.local_walkable_feature = self.extended_walkable[neighborhood_view]
        self.local_prudent_walkable = prudent_walkable[neighborhood_view].copy()
        self.local_prudent_walkable &= ~(self.diagonal_moves & is_open_door) & ~(self.diagonal_moves & on_doorway) # don't move diagonally into open doors

        if level_map.dcoord.branch == map.Branches.Sokoban:
            # Corrections to what is moveable in Sokoban
            self.local_prudent_walkable &= ~(self.diagonal_moves)

        for f in current_square.failed_moves_on_square:
            failed_target = physics.offset_location_by_action(self.local_player_location, f)
            try:
                self.local_prudent_walkable[failed_target] = False
            except IndexError:
                if environment.env.debug: import pdb; pdb.set_trace()

        #########################################
        ### MAPS DERVIED FROM EXTENDED VISION ###
        #########################################
        self.make_monsters(character)
        self.threat_map = map.ThreatMap(extended_visible_raw_glyphs, self.monsters, self.monsters_idx, player_location_in_extended)
        self.extended_threat = self.threat_map.melee_damage_threat + self.threat_map.ranged_damage_threat

        #########################################
        ### LOCAL PROPERTIES OF EXTENDED MAPS ###
        #########################################
        self.threat = self.extended_threat[neighborhood_view]
        self.threat_on_player = self.threat[self.local_player_location]

        ####################
        ### CORPSE STUFF ###
        ####################
        self.fresh_corpse_on_square_glyph = level_map.next_corpse(self.absolute_player_location)

    def count_adjacent_searches(self, search_threshold):
        below_threshold_mask = self.level_map.searches_count_map[self.vision] < search_threshold
        adjacencies = scipy.signal.convolve2d(self.extended_possible_secret_mask & below_threshold_mask, np.ones((3,3)), mode='same')
        return adjacencies[self.neighborhood_view]

    class Path(NamedTuple):
        path_action: int
        delta: tuple
        threat: float

    def path_to_targets(self, target_mask, target_monsters=False, be_prudent=True):
        if be_prudent:
            target_mask = target_mask & ~self.imprudent
        if not target_mask.any():
            return None
        if be_prudent:
            walkable_mesh = self.extended_walkable & ~self.extended_boulders & ~self.extended_is_monster & ~self.imprudent
        else:
            walkable_mesh = self.extended_walkable & ~self.extended_boulders & ~self.extended_is_monster

        if target_monsters:
            # we only need to be adjacent to monsters to attack them
            target_mask = map.FloodMap.flood_one_level_from_mask(target_mask)

        pathfinder = Pathfinder(
            walkable_mesh=walkable_mesh,
            doors=self.zoom_glyph_alike(self.level_map.doors, ViewField.Extended),
            current_square = self.current_player_square,
            diagonal=self.level_map.dcoord.branch != map.Branches.Sokoban,
        )
        it = np.nditer(target_mask, flags=['multi_index'])

        shortest_path = None
        shortest_length = None

        for is_target in it:
            if is_target:
                # start, goal
                path_iterator = pathfinder.astar(self.player_location_in_extended, Square(*it.multi_index))
                if path_iterator is None:
                    path = None
                    path_length = None
                else:
                    path = list(path_iterator)
                    path_length = len(path)
                if shortest_path is None or (shortest_length and path_length and shortest_length > path_length):
                    shortest_path = path
                    shortest_length = path_length

        if shortest_path is None or len(shortest_path) == 1: # couldn't pathfind to any / already on target
            return None
        else:
            first_square_in_path = shortest_path[1] # the 0th square is just your starting location

            delta = first_square_in_path - self.player_location_in_extended

            threat = 0.
            for square in shortest_path:
                threat += self.extended_threat[square]

            path_action = physics.delta_to_action[delta]
            return self.Path(path_action, delta, threat)

    def path_to_nearest_monster(self):
        monsters = self.extended_is_hostile_monster.copy()
        monsters[self.neighborhood_view] = False
        return self.path_to_targets(monsters, target_monsters=True)

    def path_to_nearest_weak_monster(self):
        weak_monsters = (~self.extended_is_dangerous_monster) & self.extended_is_hostile_monster
        weak_monsters[self.neighborhood_view] = False # only care about distant weak monsters

        return self.path_to_targets(weak_monsters, target_monsters=True)

    def path_to_tactical_square(self):
        tactical_squares = gd.CMapGlyph.tactical_square_mask(self.vision_glyphs)
        return self.path_to_targets(tactical_squares)

    def desirable_object_on_space(self, character):
        item_recognized = self.item_on_player is not None and self.item_on_player.identity is not None

        if item_recognized:
            return self.item_on_player.desirable(character)

        if self.in_shop:
            return False

        desirable_object_on_space = (
            (isinstance(self.previous_glyph_on_player, gd.ObjectGlyph) or isinstance(self.previous_glyph_on_player, gd.CorpseGlyph)) and
            self.previous_glyph_on_player.desirable_glyph(character)
        )

        return desirable_object_on_space

    def path_invisible_monster(self):
        invisible_monsters = gd.InvisibleGlyph.class_mask(self.vision_glyphs)
        return self.path_to_targets(invisible_monsters, target_monsters=True)
    
    def path_obvious_mimics(self):
        return self.path_to_targets(self.obvious_mimics, target_monsters=True)

    def path_next_sokoban_square(self):
        sokoban_square = self.level_map.special_level.sokoban_solution[self.level_map.sokoban_move_index].start_square
        sokoban_square += self.level_map.special_level.initial_offset
        is_next_square = self.zoom_glyph_alike(
            self.level_map.is_square_mask(sokoban_square),
            ViewField.Extended
        )
        if is_next_square.any():
            #import pdb; pdb.set_trace()
            pass
        return self.path_to_targets(is_next_square)

    def path_to_desirable_objects(self):
        desirable_corpses = self.zoom_glyph_alike(
            self.level_map.edible_corpse_map,
            ViewField.Extended
        )
        lootable_squares = self.zoom_glyph_alike(
            self.level_map.lootable_squares_map,
            ViewField.Extended
        )
        return self.path_to_targets(self.extended_has_item_stack & ~self.extended_boulders & ~self.extended_embeds & (desirable_corpses | lootable_squares))

    def path_to_unvisited_shop_sqaures(self):
        unvisited_squares = self.zoom_glyph_alike(
            self.level_map.visits_count_map == 0,
            ViewField.Extended
        )

        shop_squares = self.zoom_glyph_alike(
            self.level_map.special_room_map == constants.SpecialRoomTypes.shop.value,
            ViewField.Extended
        )

        return self.path_to_targets(unvisited_squares & shop_squares)


    def lootable_current_square(self):
        return self.level_map.lootable_squares_map[self.absolute_player_location]

    def make_monsters(self, character):
        # all the monsters in vision
        self.monsters_idx = np.where(self.extended_is_hostile_monster)
        monsters = self.vision_glyphs[self.monsters_idx]
        self.monsters = np.array([gd.GLYPH_NUMERAL_LOOKUP[g] for g in monsters])
        # just the adjacent monsters
        self.adjacent_monsters_idx = np.where(self.is_monster)
        adjacent_monsters = self.glyphs[self.adjacent_monsters_idx]
        self.adjacent_monsters = np.array([gd.GLYPH_NUMERAL_LOOKUP[g] for g in adjacent_monsters])
        
        #import pdb; pdb.set_trace()
    
    def count_monsters(self, selector, adjacent=True):
        if adjacent:
            count = 0
            for m in self.adjacent_monsters:
                if selector(m):
                    count += 1
            return count
        count = 0
        for m in self.monsters:
            if selector(m):
                count += 1
        return count

    def at_dead_end(self):
        # Consider the 8-location square surrounding the player
        # We define a dead end as a situation where a single edge holds all
        # the walkable locations
        walkable_count = np.count_nonzero(self.local_walkable_feature)

        if walkable_count > 3:
            return False
        elif walkable_count > 1:
            edge_counts = [
                np.count_nonzero(self.local_walkable_feature[0,:]),
                np.count_nonzero(self.local_walkable_feature[-1,:]),
                np.count_nonzero(self.local_walkable_feature[:,0]),
                np.count_nonzero(self.local_walkable_feature[:,-1]),
            ]
            if not walkable_count in edge_counts: # i.e. if no edge holds all of them
                return False

        return True

    def at_likely_secret(self):
        if self.at_dead_end():
            return True
        if self.level_map.special_level is None:
            return False
        if self.level_map.special_level.adjacent_to_secret[self.absolute_player_location]:
            return True
        return False

    def safe_detonation(self, monster, monster_square, source_type="local"):
        if not isinstance(monster, gd.MonsterGlyph):
            return True
        if not monster.has_death_throes:
            return True
        #import pdb; pdb.set_trace()
        if source_type == 'local':
            source_square = monster_square + self.player_location_in_extended - self.local_player_location
        elif source_type == 'extended':
            source_square = monster_square
        adjacent_to_mon_rows, adjacent_to_mon_cols = utilities.rectangle_defined_by_corners(source_square+physics.Square(-1, -1),source_square+physics.Square(1, 1))
        adjacent_to_mon_glyphs = self.vision_glyphs[adjacent_to_mon_rows, adjacent_to_mon_cols]
        if np.count_nonzero(gd.PetGlyph.class_mask(adjacent_to_mon_glyphs) | gd.MonsterGlyph.always_peaceful_mask(adjacent_to_mon_glyphs)) > 0:
            return False
        # don't attack gas spores next to gas spores
        if np.count_nonzero(gd.MonsterGlyph.gas_spore_mask(adjacent_to_mon_glyphs)) > 1:
            return False
        
        return True

    def target_monsters(self, monster_selector, attack_range=physics.AttackRange(), allow_anger=False, include_adjacent=True):
        if attack_range.type == 'melee':
            satisfying_monsters = []
            satisfying_directions = []
            absolute_positions = []
            for i, monster in enumerate(self.adjacent_monsters):
                monster_square = physics.Square(self.adjacent_monsters_idx[0][i], self.adjacent_monsters_idx[1][i])
                #if monster_selector(monster): import pdb; pdb.set_trace()
                if monster_selector(monster) and (allow_anger or self.safe_detonation(monster, monster_square)):
                    satisfying_monsters.append(monster)
                    direction = self.action_grid[monster_square]
                    satisfying_directions.append(direction)
                    absolute_positions.append(monster_square + self.absolute_player_location - self.local_player_location)

            if len(satisfying_directions) == 0: return None
            #import pdb; pdb.set_trace()
            return Targets(satisfying_monsters, satisfying_directions, absolute_positions)
        else:
            satisfying_monsters = []
            satisfying_directions = []
            absolute_positions = []
            player_mask = np.full_like(self.vision_glyphs, False, dtype=bool)
            player_mask[self.player_location_in_extended] = True
            can_hit_mask = self.threat_map.calculate_ranged_can_hit_mask(player_mask, self.vision_glyphs, attack_range=attack_range, include_adjacent=include_adjacent, stop_on_monsters=True, reject_peaceful=True, stop_on_boulders=False)
            for i, monster in enumerate(self.monsters):
                monster_square = physics.Square(self.monsters_idx[0][i], self.monsters_idx[1][i])
                if can_hit_mask[monster_square] and monster_selector(monster) and (allow_anger or self.safe_detonation(monster, monster_square, source_type='extended')):
                    satisfying_monsters.append(monster)
                    offset = physics.Square(*np.sign(np.array(monster_square - self.player_location_in_extended)))
                    direction = physics.delta_to_action[offset]
                    satisfying_directions.append(direction)
                    absolute_positions.append(monster_square + self.absolute_player_location - self.player_location_in_extended)

            if len(satisfying_directions) == 0: return None
            #import pdb; pdb.set_trace()
            return Targets(satisfying_monsters, satisfying_directions, absolute_positions)

class Pathfinder(AStar):
    def __init__(self, walkable_mesh, doors, current_square, diagonal=True):
        self.walkable_mesh = walkable_mesh
        self.doors = doors
        self.diagonal = diagonal
        self.player_square = current_square

    def neighbors(self, node):
        box_slices = utilities.centered_slices_bounded_on_array(node, (1,1), self.walkable_mesh) # radius 1 square
        upper_left = Square(box_slices[0].start, box_slices[1].start)
        current_square = node - upper_left
        walkable_box = self.walkable_mesh[box_slices]
        door_box = self.doors[box_slices]

        neighboring_walkable_squares = []
        it = np.nditer(walkable_box, flags=['multi_index'])
        for walkable in it:
            square = Square(*it.multi_index)
            #import pdb; pdb.set_trace()
            is_orthogonal = np.sum(np.abs(square-current_square)) == 1
            if walkable and (self.diagonal or is_orthogonal) and (not door_box[current_square] or is_orthogonal) and (not door_box[square] or is_orthogonal):
                neighboring_walkable_squares.append(square + upper_left)

        if current_square == self.player_square.location:
            for f in self.player_square.failed_moves_on_square:
                failed_target = physics.offset_location_by_action(current_square, f)
                try:
                    #import pdb; pdb.set_trace()
                    neighboring_walkable_squares.remove(failed_target)
                except ValueError:
                    pass

        return neighboring_walkable_squares

    def distance_between(self, n1, n2):
        return 1 # diagonal moves are strong!

    def heuristic_cost_estimate(self, current, goal):
        return math.hypot(*(current - goal))
