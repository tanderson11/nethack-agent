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

@dataclass
class CurrentSquare:
    dcoord: Tuple[int, int]
    location: Tuple[int, int]
    arrival_time: int
    glyph_under_player: gd.Glyph = None
    stack_on_square: bool = False
    failed_moves_on_square: List[int] = field(default_factory=list)

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

    def __init__(self, time, current_square, glyphs, level_map, character, latest_monster_flight):
        ###################
        ### COPY FIELDS ###
        ###################

        absolute_player_location = Square(*current_square.location)

        self.previous_glyph_on_player = current_square.glyph_under_player
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
        extended_visible_glyphs = utilities.vectorized_map(lambda n: gd.GLYPH_NUMERAL_LOOKUP[n], extended_visible_raw_glyphs)

        # index of player in the full vision
        player_location_in_extended = absolute_player_location - vision_start
        self.player_location_in_extended = player_location_in_extended

        ####################
        # SHOPKEEPER STUFF #
        ####################
        is_shopkeeper = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.is_shopkeeper, extended_visible_glyphs)
        shopkeeper_present = is_shopkeeper.any()

        if shopkeeper_present and on_doorway:
            it = np.nditer(is_shopkeeper, flags=['multi_index'])
            for b in it:
                if b: # if this is a shopkeeper
                    absolute_shopkeeper_position = self.extended_position_to_absolute(Square(*it.multi_index), self.player_location_in_extended, absolute_player_location)
                    level_map.add_room_from_square(absolute_shopkeeper_position, constants.SpecialRoomTypes.shop)

        extended_special_rooms = level_map.special_room_map[self.vision]

        ###################################
        ### RELATIVE POSITION IN VISION ###
        ###################################

        extended_visits = level_map.visits_count_map[self.vision]
        extended_open_door = utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_open_door, extended_visible_glyphs)
        extended_walkable_tile = gd.walkable(extended_visible_raw_glyphs)

        extended_walkable_tile &= ~(extended_special_rooms == constants.SpecialRoomTypes.vault_closet.value)  # don't go into vault closets
        if extended_special_rooms[self.player_location_in_extended] != constants.SpecialRoomTypes.shop.value:
            extended_walkable_tile &= ~(extended_special_rooms == constants.SpecialRoomTypes.shop.value)  # don't step on shop sqaures unless you are in a shop
        extended_walkable_tile[self.player_location_in_extended] = False # in case we turn invisible

        self.extended_boulders = self.zoom_glyph_alike(
            level_map.boulder_map,
            ViewField.Extended
        )

        if level_map.dcoord.branch == map.Branches.Sokoban:
            # Corrections to what is moveable in Sokoban
            extended_walkable_tile &= ~(self.extended_boulders)

        extended_is_monster = gd.MonsterGlyph.where_is(extended_visible_raw_glyphs) | gd.SwallowGlyph.where_is(extended_visible_raw_glyphs) | gd.InvisibleGlyph.where_is(extended_visible_raw_glyphs) | gd.WarningGlyph.where_is(extended_visible_raw_glyphs)
        extended_is_monster[player_location_in_extended] = False # player does not count as a monster anymore
        self.extended_is_monster = extended_is_monster
        extended_is_dangerous_monster = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.monster_spoiler.dangerous_to_player(character, time, latest_monster_flight), extended_visible_glyphs)
        extended_is_dangerous_monster[player_location_in_extended] = False
        self.extended_is_dangerous_monster = extended_is_dangerous_monster
        self.extended_is_peaceful_monster = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.always_peaceful, extended_visible_glyphs)
        self.extended_possible_secret_mask = utilities.vectorized_map(
            lambda g: isinstance(g, gd.CMapGlyph) and g.possible_secret_door,
            extended_visible_glyphs
        )
        self.extended_has_item_stack = utilities.vectorized_map(
            lambda g: gd.stackable_glyph(g),
            extended_visible_glyphs
        )

        # radius 1 box around player in vision glyphs
        neighborhood_view = utilities.centered_slices_bounded_on_array(player_location_in_extended, (1, 1), extended_visible_glyphs)
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

        self.raw_glyphs = extended_visible_raw_glyphs[neighborhood_view]
        self.glyphs = extended_visible_glyphs[neighborhood_view]
        self.visits = extended_visits[neighborhood_view]
        is_open_door = extended_open_door[neighborhood_view]
        self.is_monster = extended_is_monster[neighborhood_view]
        self.n_adjacent_monsters = np.count_nonzero(self.is_monster)

        self.local_possible_secret_mask = self.extended_possible_secret_mask[neighborhood_view]

        walkable_tile = extended_walkable_tile[neighborhood_view]

        # in the narrow sense
        self.walkable = walkable_tile
        self.walkable &= ~(self.diagonal_moves & is_open_door) & ~(self.diagonal_moves & on_doorway) # don't move diagonally into open doors

        if level_map.dcoord.branch == map.Branches.Sokoban:
            # Corrections to what is moveable in Sokoban
            self.walkable &= ~(self.diagonal_moves)

        for f in current_square.failed_moves_on_square:
            failed_target = physics.offset_location_by_action(self.local_player_location, f)
            try:
                self.walkable[failed_target] = False
            except IndexError:
                if environment.env.debug: import pdb; pdb.set_trace()


        # we're not calculating the true walkable mesh in extended vision, but we can at least add our local calculation
        # to help with pathfinding (which depends on an extended walkable mesh)
        extended_walkable_tile[neighborhood_view] = self.walkable
        self.extended_walkable = extended_walkable_tile

        #########################################
        ### MAPS DERVIED FROM EXTENDED VISION ###
        #########################################
        self.threat_map = map.ThreatMap(extended_visible_raw_glyphs, extended_visible_glyphs, player_location_in_extended)
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

    def path_to_targets(self, target_mask):
        if target_mask.any():
            pathfinder = Pathfinder(
                walkable_mesh=((self.extended_walkable & ~self.extended_boulders) | target_mask), # pretend the targets are walkable so we can actually reach them in pathfinding
                doors = self.zoom_glyph_alike(self.level_map.doors, ViewField.Extended)
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
        monsters = self.extended_is_monster & (~self.extended_is_peaceful_monster)
        monsters[self.neighborhood_view] = False
        return self.path_to_targets(monsters)

    def path_to_nearest_weak_monster(self):
        weak_monsters = (~self.extended_is_dangerous_monster) & self.extended_is_monster & (~self.extended_is_peaceful_monster)
        weak_monsters[self.neighborhood_view] = False # only care about distant weak monsters

        return self.path_to_targets(weak_monsters)

    def desirable_object_on_space(self, global_identity_map, character):
        desirable_object_on_space = (
            (isinstance(self.previous_glyph_on_player, gd.ObjectGlyph) or isinstance(self.previous_glyph_on_player, gd.CorpseGlyph)) and
            self.previous_glyph_on_player.desirable_glyph(global_identity_map, character)
        )

        return desirable_object_on_space

    def path_to_desirable_objects(self):
        desirable_corpses = self.zoom_glyph_alike(
            self.level_map.edible_corpse_map,
            ViewField.Extended
        )
        lootable_squares = self.zoom_glyph_alike(
            self.level_map.lootable_squares_map,
            ViewField.Extended
        )
        return self.path_to_targets(self.extended_has_item_stack & ~self.extended_boulders & (desirable_corpses | lootable_squares))

    def lootable_current_square(self):
        return self.level_map.lootable_squares_map[self.absolute_player_location]

class Pathfinder(AStar):
    def __init__(self, walkable_mesh, doors):
        self.walkable_mesh = walkable_mesh
        self.doors = doors

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
            if walkable and (not door_box[current_square] or is_orthogonal) and (not door_box[square] or is_orthogonal):
                neighboring_walkable_squares.append(square + upper_left)

        return neighboring_walkable_squares

    def distance_between(self, n1, n2):
        return 1 # diagonal moves are strong!

    def heuristic_cost_estimate(self, current, goal):
        return math.hypot(*(current - goal))
