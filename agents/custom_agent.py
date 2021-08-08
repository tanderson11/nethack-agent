from pdb import run
import base64
import csv
from dataclasses import dataclass
import enum
import os
import re

import numpy as np
import pandas as pd
import itertools

from nle import nethack
from agents.base import BatchedAgent

from typing import NamedTuple

from astar import AStar
import math

import advisors as advs
import advisor_sets

import menuplan
import utilities
import physics
import inventory as inv
import constants

from utilities import ARS
from character import Character
import constants
import glyphs as gd
from map import DMap, ThreatMap
import environment

from collections import Counter

if environment.env.debug:
    import pdb

# Config variable that are screwing with me
# pile_limit

ACCEPTABLE_CORPSE_AGE = 40

class BLStats():
    bl_meaning = [
        'hero_col', 'hero_row', 'strength_25', 'strength_125', 'dexterity', 'constitution',
        'intelligence', 'wisdom', 'charisma', 'score', 'hitpoints', 'max_hitpoints', 'depth', 
        'gold', 'energy', 'max_energy', 'armor_class', 'monster_level', 'experience_level', 
        'experience_points', 'time', 'hunger_state', 'encumberance', 'dungeon_number', 'level_number',
        'condition'
    ]

    def __init__(self, raw):
        self.raw = raw

    def get(self, key):
        return self.raw[self.__class__.bl_meaning.index(key)]

    def make_attributes(self):
        strength_25 = self.get('strength_25')

        if strength_25 != 25 and strength_25 not in range(3,20):
            import pdb; pdb.set_trace()
            raise Exception('Surprising strength_25')

        strength_pct = 0
        if strength_25 > 18 and strength_25 != 25:
            strength_pct = self.get('strength_125') - 18

        if strength_pct > 100:
            if environment.env.debug: import pdb; pdb.set_trace()
            raise Exception('Surprising strength pct')

        attr_dict = {
            'strength': min(strength_25, 18),
            'strength_pct': strength_pct,
            'dexterity': self.get('dexterity'),
            'constitution': self.get('constitution'),
            'intelligence': self.get('intelligence'),
            'wisdom': self.get('wisdom'),
            'charisma': self.get('charisma')
        }

        attributes = constants.Attributes(**attr_dict)
        return attributes

    def check_condition(self, bit_mask):
        return (bit_mask & self.get('condition')) == bit_mask

    def am_hallu(self):
        return (nethack.BL_MASK_HALLU & self.get('condition')) == nethack.BL_MASK_HALLU

class RecordedMonsterEvent():
    def __init__(self, time, monster_name):
        self.time = time
        self.monster_name = monster_name

        self.monster_glyph = gd.get_by_name(gd.MonsterAlikeGlyph, self.monster_name)

    @classmethod
    def involved_monster(cls, message):
        match = re.search(cls.pattern, message)
        if match is None:
            return None
        monster_name = match[cls.name_field]
        return monster_name

class RecordedMonsterFlight(RecordedMonsterEvent):
    pattern = re.compile("(^|. +|! +)(The )?([a-zA-Z -]+?) turns to flee.")
    name_field = 3

class RecordedMonsterDeath(RecordedMonsterEvent):
    pattern = re.compile("You kill the (poor )?(invisible )?(saddled )?(.+?)( of .+?)?!")
    name_field = 4

    def __init__(self, square, time, monster_name):
        self.square = square # doesn't know about dungeon levels
        super().__init__(time, monster_name)
        self.can_corpse = bool(self.monster_glyph.corpse_spoiler)

class Message():
    known_lost_messages = set([
        "Things that are here:",
        "There is a doorway here.",
        "There is an open door here.",
        "Things that you feel here:",
        "Other things that are here:",
        "There is a staircase up here.",
        "There is a staircase down here.",
        "Other things that you feel here:",
        "Hello Agent, welcome to NetHack!  You are a neutral female gnomish", # see issue_report_1
        "There is a fountain here.",
        "There is a grave here.",
        "There is a broken door here.",
        "There is a sink here.",
        "Pick up what?",
        "paperback book named",
        "staircase down",
        # Implement There is an altar to Chih Sung-tzu (neutral) here.
        ])

    class Feedback():
        def __init__(self, message):
            self.diagonal_out_of_doorway_message = "You can't move diagonally out of an intact doorway." in message.message
            self.diagonal_into_doorway_message = "You can't move diagonally into an intact doorway." in message.message
            self.collapse_message = "You collapse under your load" in message.message
            self.boulder_in_vain_message = "boulder, but in vain." in message.message
            self.boulder_blocked_message = "Perhaps that's why you cannot move it." in message.message
            self.carrying_too_much_message = "You are carrying too much to get through." in message.message
            #no_hands_door_message = "You can't open anything -- you have no hands!" in message.message
            
            #"Can't find dungeon feature"
            #self.failed_move =  self.diagonal_into_doorway_message or self.collapse_message or self.boulder_in_vain_message
            self.nothing_to_eat = "You don't have anything to eat." in message.message
            self.nevermind = "Never mind." in message.message

    def __init__(self, message, tty_chars, misc_observation):
        self.raw_message = message
        self.tty_chars = tty_chars
        self.message = ''
        self.yn_question = (misc_observation[0] == 1)
        self.getline = (misc_observation[1] == 1)
        self.has_more = (misc_observation[2] == 1)

        if np.count_nonzero(message) > 0:
            try:
                self.message = bytes(message).decode('ascii').rstrip('\x00')
            except UnicodeDecodeError:
                if environment.env.debug: pdb.set_trace()

        ascii_top_line = bytes(tty_chars[0]).decode('ascii')
        potential_message = ascii_top_line.strip(' ')
        if not self.message and potential_message:
            if not (self.has_more or potential_message.startswith("You read: ") or potential_message in self.__class__.known_lost_messages):
                #print(f"NLE missed this message: {potential_message}")
                pass
            self.message = potential_message

        self.feedback = self.__class__.Feedback(self)

    def __bool__(self):
        return bool(self.message)

class Neighborhood(): # goal: mediates all access to glyphs by advisors
    extended_vision = 3
    def __init__(self, time, absolute_player_location, observation, dcoord, level_map, character, last_movement_action, previous_glyph_on_player, latest_monster_death, latest_monster_flight, failed_moves_on_square, feedback):
        ###################
        ### COPY FIELDS ###
        ###################

        blstats = BLStats(observation['blstats'])
        self.last_movement_action = last_movement_action
        self.previous_glyph_on_player = previous_glyph_on_player
        self.absolute_player_location = absolute_player_location
        self.dcoord = dcoord
        self.level_map = level_map

        on_doorway = isinstance(previous_glyph_on_player, gd.CMapGlyph) and previous_glyph_on_player.is_open_door or feedback.diagonal_out_of_doorway_message

        #############################
        ### FULL EXTENT OF VISION ###
        #############################
        row_vision, col_vision = utilities.centered_slices_bounded_on_array(
            absolute_player_location, (self.extended_vision, self.extended_vision), observation['glyphs']
        )
        extended_visible_raw_glyphs = observation['glyphs'][row_vision, col_vision]
        extended_visible_glyphs = utilities.vectorized_map(lambda n: gd.GLYPH_NUMERAL_LOOKUP[n], extended_visible_raw_glyphs)
        extended_visits = level_map.visits_map[row_vision, col_vision]
        extended_open_door = utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_open_door, extended_visible_glyphs)
        extended_walkable_tile = utilities.vectorized_map(lambda g: g.walkable(character), extended_visible_glyphs)

        ###################################
        ### RELATIVE POSITION IN VISION ###
        ###################################

        # index of player in the full vision
        player_location_in_extended = (absolute_player_location[0]-row_vision.start, absolute_player_location[1]-col_vision.start)
        self.player_location_in_extended = player_location_in_extended

        extended_is_monster = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) or isinstance(g, gd.SwallowGlyph) or isinstance(g, gd.InvisibleGlyph) or isinstance(g, gd.WarningGlyph), extended_visible_glyphs)
        extended_is_monster[player_location_in_extended] = False # player does not count as a monster anymore
        self.extended_is_monster = extended_is_monster
        extended_is_dangerous_monster = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.monster_spoiler.dangerous_to_player(character, time, latest_monster_flight), extended_visible_glyphs)
        extended_is_dangerous_monster[player_location_in_extended] = False
        self.extended_is_dangerous_monster = extended_is_dangerous_monster

        self.monster_present = extended_is_monster.any()

        # radius 1 box around player in vision glyphs
        neighborhood_rows, neighborhood_cols = utilities.centered_slices_bounded_on_array(player_location_in_extended, (1, 1), extended_visible_glyphs)
        neighborhood_view = (neighborhood_rows, neighborhood_cols)
        self.neighborhood_view = neighborhood_view

        ####################
        # SHOPKEEPER STUFF #
        ####################
        is_shopkeeper = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.is_shopkeeper, extended_visible_glyphs)
        shopkeeper_present = is_shopkeeper.any()

        extended_shop = np.full_like(extended_visible_glyphs, False, dtype='bool')
        if shopkeeper_present and on_doorway:
            it = np.nditer(is_shopkeeper, flags=['multi_index'])
            for b in it:
                if b: # if this is a shopkeeper
                    # draw the rectangle containing the player and shopkeeper
                    shop_row_slice, shop_col_slice = utilities.rectangle_defined_by_corners(player_location_in_extended, it.multi_index)
                    # check if that rectangle contains another doorway
                    # if it doesn't, assume we're at the shop entrance
                    if not extended_open_door[shop_row_slice, shop_col_slice].any():
                        extended_shop[shop_row_slice, shop_col_slice] = True

        ##############################
        ### RESTRICTED ACTION GRID ###
        ##############################

        # a window into the action grid of the size size and shape as our window into the glyph grid (ie: don't include actions out of bounds on the map)
        action_grid_rows, action_grid_cols = utilities.move_slice_center(player_location_in_extended, (1,1), neighborhood_view) # move center to (1,1) (action grid center)
        action_grid_view = (action_grid_rows, action_grid_cols)

        self.action_grid = physics.action_grid[action_grid_view]
        self.diagonal_moves = physics.diagonal_moves[action_grid_view]

        ########################################
        ### RELATIVE POSITION IN ACTION GRID ###
        ########################################

        self.local_player_location = (1-action_grid_rows.start, 1-action_grid_cols.start) # not always guranteed to be (1,1) if we're at the edge of the map
        self.player_location_mask = np.full_like(self.action_grid, False, dtype='bool')
        self.player_location_mask[self.local_player_location] = True

        #######################
        ### THE LOCAL STUFF ###
        #######################

        self.raw_glyphs = extended_visible_raw_glyphs[neighborhood_view]
        self.glyphs = extended_visible_glyphs[neighborhood_view]
        self.visits = extended_visits[neighborhood_view]
        is_open_door = extended_open_door[neighborhood_view]
        shop = extended_shop[neighborhood_view]
        self.is_monster = extended_is_monster[neighborhood_view]
        self.is_dangerous_monster = extended_is_dangerous_monster[neighborhood_view]

        walkable_tile = extended_walkable_tile[neighborhood_view]

        # in the narrow sense
        self.walkable = walkable_tile & ~(self.diagonal_moves & is_open_door) & ~(self.diagonal_moves & on_doorway) & ~shop # don't move diagonally into open doors
        self.walkable[self.local_player_location] = False # in case we turn invisible

        for f in failed_moves_on_square:
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
        self.threat_map = ThreatMap(extended_visible_raw_glyphs, extended_visible_glyphs, player_location_in_extended)
        self.extended_threat = self.threat_map.melee_damage_threat + self.threat_map.ranged_damage_threat
        self.extended_n_threat = self.threat_map.melee_n_threat + self.threat_map.ranged_n_threat

        #########################################
        ### LOCAL PROPERTIES OF EXTENDED MAPS ###
        #########################################
        self.n_threat = self.extended_n_threat[neighborhood_view]
        self.threat = self.extended_threat[neighborhood_view]

        self.threat_on_player = self.threat[self.local_player_location]
        ####################
        ### CORPSE STUFF ###
        ####################
        
        self.has_fresh_corpse = np.full_like(self.action_grid, False, dtype='bool')
        self.fresh_corpse_on_square_glyph = None
        if latest_monster_death and latest_monster_death.can_corpse and (time - latest_monster_death.time < ACCEPTABLE_CORPSE_AGE):
            corpse_difference = (latest_monster_death.square[0] - absolute_player_location[0], latest_monster_death.square[1] - absolute_player_location[1])
            corpse_relative_location = (self.local_player_location[0] + corpse_difference[0], self.local_player_location[1] + corpse_difference[1])
            # is corpse nearby?
            if corpse_relative_location[0] in range(0, action_grid_rows.stop-action_grid_rows.start) and corpse_relative_location[1] in range(0, action_grid_cols.stop-action_grid_cols.start):
                self.has_fresh_corpse[corpse_relative_location] = True

        if self.has_fresh_corpse[self.local_player_location]:
            #import pdb; pdb.set_trace()
            self.fresh_corpse_on_square_glyph = latest_monster_death.monster_glyph

    class Path(NamedTuple):
        path_action: int
        delta: tuple
        threat: float

    def path_to_targets(self, target_mask):
        if target_mask.any():
            pathfinder = Pathfinder(self.extended_walkable | target_mask) # pretend the targets are walkable so we can actually reach them in pathfinding
            it = np.nditer(target_mask, flags=['multi_index'])

            shortest_path = None
            shortest_length = None

            for is_target in it:
                if is_target:
                    # start, goal
                    path_iterator = pathfinder.astar(self.player_location_in_extended, it.multi_index)
                    if path_iterator is None:
                        path = None
                        path_length = None
                    else:
                        path = list(path_iterator)
                        path_length = len(path)
                    if shortest_path is None or (shortest_length and path_length and shortest_length > path_length):
                        shortest_path = path
                        shortest_length = path_length

            if shortest_path is None: # couldn't pathfind to any
                return None
            else:
                first_square_in_path = shortest_path[1] # the 0th square is just your starting location
                delta = (first_square_in_path[0]-self.player_location_in_extended[0], first_square_in_path[1]-self.player_location_in_extended[1])

                threat = 0.
                for square in shortest_path:
                    threat += self.extended_threat[square]

                path_action = nethack.ACTIONS[physics.delta_to_action[delta]] # TODO make this better with an action object
                return self.Path(path_action, delta, threat)

    def path_to_nearest_monster(self):
        monsters = self.extended_is_monster.copy()
        monsters[self.neighborhood_view] = False
        return self.path_to_targets(monsters)

    def path_to_nearest_weak_monster(self):
        weak_monsters = (~self.extended_is_dangerous_monster) & self.extended_is_monster
        weak_monsters[self.neighborhood_view] = False # only care about distant weak monsters

        return self.path_to_targets(weak_monsters)


class Pathfinder(AStar):
    def __init__(self, walkable_mesh):
        self.walkable_mesh = walkable_mesh

    def neighbors(self, node):
        box_slices = utilities.centered_slices_bounded_on_array(node, (1,1), self.walkable_mesh) # radius 1 square
        upper_left = (box_slices[0].start, box_slices[1].start)
        box = self.walkable_mesh[box_slices]

        neighboring_walkable_squares = []
        it = np.nditer(box, flags=['multi_index'])
        for walkable in it:

            if walkable:
                neighboring_walkable_squares.append((it.multi_index[0]+upper_left[0] , it.multi_index[1]+upper_left[1]))

        return neighboring_walkable_squares

    def distance_between(self, n1, n2):
        return 1 # diagonal moves are strong!

    def heuristic_cost_estimate(self, current, goal):
        return math.hypot(current[0]-goal[0], current[1]-goal[1])

background_advisor = advs.BackgroundActionsAdvisor()
BackgroundMenuPlan = menuplan.MenuPlan(
    "background", background_advisor, [
        menuplan.PhraseMenuResponse('"Hello stranger, who are you?" - ', "Val"),
        menuplan.EscapeMenuResponse("Call a "),
        menuplan.EscapeMenuResponse("Call an "),
        menuplan.NoMenuResponse("Really attack"),
        menuplan.NoMenuResponse("Shall I remove"),
        menuplan.NoMenuResponse("Would you wear it for me?"),
        menuplan.EscapeMenuResponse("zorkmids worth of damage!"),
        menuplan.EscapeMenuResponse("little trouble lifting"),
        menuplan.PhraseMenuResponse("For what do you wish?", "blessed +2 silver dragon scale mail"),
    ])

class RunState():
    def __init__(self, debug_env=None):
        self.reset()
        self.debug_env = debug_env
        self.log_path = None
        self.target_roles = environment.env.target_roles
        if environment.env.log_runs:
            self.log_root = debug_env.savedir
            self.log_path = os.path.join(self.log_root, "log.csv")
            with open(self.log_path, 'w') as log_file:
                writer = csv.DictWriter(log_file, fieldnames=self.LOG_HEADER)
                writer.writeheader()

    def print_action_log(self, num):
        return "||".join([nethack.ACTIONS[num].name for num in self.action_log[(-1 * num):]])

    LOG_HEADER = ['race', 'class', 'level', 'depth', 'branch', 'branch_level', 'time', 'hp', 'max_hp', 'AC', 'encumberance', 'hunger', 'message_log', 'action_log', 'score', 'last_pray_time', 'last_pray_reason', 'scummed', 'ascended']

    def log_final_state(self, final_reward, ascended):
        # self.blstats is intentionally one turn stale, i.e. wasn't updated after done=True was observed
        self.update_reward(final_reward)
        print_stats(True, self, self.blstats)
        if self.scumming:
            if not environment.env.debug:
                raise Exception("Should not scum except to debug")
            if not self.reward == 0:
                # Weird to scum and get reward > 0
                import pdb; pdb.set_trace()
        if not self.log_path:
            return
        with open(self.log_path, 'a') as log_file:
            writer = csv.DictWriter(log_file, fieldnames=self.LOG_HEADER)
            writer.writerow({
                'race': self.character.base_race,
                'class': self.character.base_class,
                'level': self.blstats.get('experience_level'),
                'depth': self.blstats.get('depth'),
                'branch': self.blstats.get('dungeon_number'),
                'branch_level': self.blstats.get('level_number'),
                'time': self.blstats.get('time'),
                'hp': self.blstats.get('hitpoints'),
                'max_hp': self.blstats.get('max_hitpoints'),
                'AC': self.blstats.get('armor_class'),
                'encumberance': self.blstats.get('encumberance'),
                'hunger': self.blstats.get('hunger_state'),
                'message_log': "||".join(self.message_log[-10:]),
                'action_log': self.print_action_log(10),
                'score': self.reward,
                'last_pray_time': self.character.last_pray_time,
                'last_pray_reason': str(self.character.last_pray_reason),
                'scummed': self.scumming,
                'ascended': ascended,
            })

        #import pdb; pdb.set_trace()

        self.update_counter_json("message_counter.json", self.message_log)
        self.update_counter_json("advisor_counter.json", [advice.advisor.__class__.__name__ for advice in self.advice_log if advice is not None])

    def update_counter_json(self, filename, counter_list):
        import json
        try:
            with open(os.path.join(self.log_root, filename), 'r') as counter_file:
                state = json.load(counter_file)
        except FileNotFoundError:
            state = {}

        counter = Counter(state)
        additional_counter = Counter(counter_list)
        counter.update(additional_counter)

        with open(os.path.join(self.log_root, filename), 'w') as counter_file:
            json.dump(counter, counter_file)

    def reset(self):
        self.reading_base_attributes = False
        self.scumming = False
        self.character = None
        self.gods_by_alignment = {}

        self.step_count = 0
        self.reward = 0
        self.time = None

        self.active_menu_plan = BackgroundMenuPlan
        self.message_log = []
        self.action_log = []
        self.advice_log = []
        self.actions_without_consequence = []

        self.last_non_menu_action = None
        self.last_non_menu_action_timestamp = None
        self.last_movement_action = None
        
        self.time_hung = 0
        self.time_stuck = 0
        self.failed_moves_on_square = []
        self.rng = self.make_seeded_rng()
        self.glyph_under_player = None
        self.time_did_advance = True

        self.neighborhood = None
        self.global_identity_map = gd.GlobalIdentityMap()

        self.latest_monster_death = None
        self.latest_monster_flight = None

        self.menu_plan_log = []

        # for mapping purposes
        self.dmap = DMap()
        #self.dmap = type('DMap', (), {"dungeon_number":0, "level_number":0,})()
        self.glyphs = None

    def make_seeded_rng(self):
        import random
        seed = base64.b64encode(os.urandom(4))
        #seed = b'G931Kg=='
        print(f"Seeding Agent's RNG {seed}")
        return random.Random(seed)

    attribute_pattern_1 = re.compile("You are an? [A-Z][a-z]+, a level 1 (female|male)? ?([a-z]+) ([A-Z][a-z]+).")
    attribute_pattern_2 = re.compile("You are (neutral|lawful|chaotic), on a mission for (.+?)  ")
    attribute_pattern_3 = re.compile("who is opposed by (.+?) \((neutral|lawful|chaotic)\) and (.+?) \((neutral|lawful|chaotic)\)")

    base_race_mapping = {
        'dwarven': 'dwarf',
        'human': 'human',
        'gnomish': 'gnome',
        'orcish': 'orc',
        'elven': 'elf',
    }

    class_to_sex_mapping = {
        'Caveman': 'male',
        'Cavewoman': 'female',
        'Priest': 'male',
        'Priestess': 'female',
        'Valkyrie': 'female',
    }

    def update_base_attributes(self, raw_screen_content):
        if not self.reading_base_attributes:
            raise Exception("Shouldn't be doing this")
        attribute_match_1 = re.search(self.attribute_pattern_1, raw_screen_content)
        attribute_match_2 = re.search(self.attribute_pattern_2, raw_screen_content)
        attribute_match_3 = re.search(self.attribute_pattern_3, raw_screen_content)
        if attribute_match_1[1] is None:
            base_sex = self.class_to_sex_mapping[attribute_match_1[3]]
        else:
            base_sex = attribute_match_1[1]

        base_class = attribute_match_1[3]
        if base_class == "Cavewoman" or base_class == "Caveman":
            base_class = "Caveperson" 
        if base_class == "Priest" or base_class == "Priestess":
            base_class = "Priest"

        base_race = self.base_race_mapping[attribute_match_1[2]]

        self.character = Character(
            base_sex=base_sex,
            base_race = constants.BaseRace[base_race],
            base_class = constants.BaseRole[base_class],
            base_alignment = attribute_match_2[1],
        )
        self.character.set_innate_intrinsics()

        self.gods_by_alignment[self.character.base_alignment] = attribute_match_2[2]
        self.gods_by_alignment[attribute_match_3[2]] = attribute_match_3[1]
        self.gods_by_alignment[attribute_match_3[4]] = attribute_match_3[3]
        self.reading_base_attributes = False

    def update_reward(self, reward):
        self.step_count += 1
        self.reward += reward

    def update_observation(self, observation):
        # we want to track when we are taking game actions that are progressing the game
        # time isn't a totally reliable metric for this, as game time doesn't advance after every action for fast players
        # our metric for time advanced: true if game time advanced or if neighborhood changed
        # neighborhood equality assessed by glyphs and player location

        blstats = BLStats(observation['blstats'].copy())

        # Potentially useful for checking stalls
        new_time = blstats.get('time')
        if self.time == new_time:
            self.time_hung += 1
        else:
            self.time_hung = 0
        if self.time_hung > 50:
            if environment.env.debug: pdb.set_trace()
            pass
        self.time = new_time
        self.glyphs = observation['glyphs'].copy() # does this need to be a copy?
        self.blstats = blstats

    def set_menu_plan(self, menu_plan):
        self.active_menu_plan = menu_plan

    def run_menu_plan(self, message):
        retval = self.active_menu_plan.interact(message)

        if retval is None and self.active_menu_plan.fallback:
            retval = self.active_menu_plan.fallback
            self.active_menu_plan = BackgroundMenuPlan
            return retval

        if self.active_menu_plan != BackgroundMenuPlan:
            if retval is None:
                self.active_menu_plan = BackgroundMenuPlan
                retval = self.active_menu_plan.interact(message)

        if retval is None and (message.yn_question or message.getline):
            if environment.env.debug:
                pass # not anymore, now we hit space blindly after interacting with the menu
                #import pdb; pdb.set_trace()
                # This should have been dealt with by our menu plan

        return retval

    def update_neighborhood(self, neighborhood):
        if self.neighborhood is not None:
            old_loc = self.neighborhood.absolute_player_location
        else:
            old_loc = None
        
        self.neighborhood = neighborhood

        if self.neighborhood is not None and old_loc == self.neighborhood.absolute_player_location:
            self.time_stuck += 1
        else:
            self.time_stuck = 0
            self.failed_moves_on_square = []

        if self.time_stuck > 200:
            pass
            #if environment.env.debug: import pdb; pdb.set_trace()

    def handle_message(self, message):
        self.message_log.append(message.message)

        if self.active_menu_plan is not None and self.active_menu_plan.listening_item:
            self.active_menu_plan.listening_item.process_message(message, self.last_non_menu_action)

        if message.feedback.nevermind or message.feedback.nothing_to_eat:
            eat_corpse_flag = False
            if self.advice_log[-1] is None:
                if isinstance(self.menu_plan_log[-1].advisor, advs.EatCorpseAdvisor): # why is this an instance and not a class?
                    eat_corpse_flag = True
            elif self.advice_log[-1].advisor == advs.EatCorpseAdvisor: # have to do this weird thing because we usually handle classes and not instances
                eat_corpse_flag = True

            if eat_corpse_flag:
                self.latest_monster_death = None

        if message.feedback.boulder_in_vain_message or message.feedback.diagonal_into_doorway_message or message.feedback.boulder_blocked_message or message.feedback.carrying_too_much_message:
            if self.last_movement_action is not None and self.last_movement_action == self.last_non_menu_action:
                assert self.last_movement_action in range(0,8), "Expected a movement action given failed_move flag but got {}".format(move)
                self.failed_moves_on_square.append(self.last_movement_action)
            else:
                if self.last_non_menu_action != utilities.ACTION_LOOKUP[nethack.actions.Command.TRAVEL]:
                    if environment.env.debug: import pdb; pdb.set_trace()
                    print("Failed move no advisor with menu_plan_log {} and message:{}".format(self.menu_plan_log[-5:], message.message))

    def log_action(self, action, menu_plan=None, advice=None):
        self.menu_plan_log.append(menu_plan)
        self.action_log.append(action)
        self.advice_log.append(advice)

        if action in range(0,8): #is a movement action; bad
            self.last_movement_action = action

        if menu_plan == None:
            self.last_non_menu_action = action
            self.last_non_menu_action_timestamp = self.time

    def check_gamestate_advancement(self, neighborhood):
        game_did_advance = True
        if self.time is not None and self.last_non_menu_action_timestamp is not None and self.time_hung > 4: # time_hung > 4 is a bandaid for fast characters
            if self.time - self.last_non_menu_action_timestamp == 0: # we keep this timestamp because we won't call this function every step: menu plans bypass it
                neighborhood_diverged = self.neighborhood.absolute_player_location != neighborhood.absolute_player_location or (self.neighborhood.glyphs != neighborhood.glyphs).any()
                #pdb.set_trace()
                if not neighborhood_diverged:
                    game_did_advance = False

        if game_did_advance: # we advanced the game state, forget the list of attempted actions
            self.actions_without_consequence = []
        else:
            self.actions_without_consequence.append(self.last_non_menu_action)

        return game_did_advance


def print_stats(done, run_state, blstats):
    print(
        ("[Done] " if done else "") +
        f"After step {run_state.step_count}: " + \
        f"reward {run_state.reward}, " + \
        f"dlevel {blstats.get('level_number')}, " + \
        f"depth {blstats.get('depth')}, " + \
        f"elevel {blstats.get('experience_level')}, " + \
        f"time {blstats.get('time')}"
    )

class CustomAgent(BatchedAgent):
    """A example agent... that simple acts randomly. Adapt to your needs!"""

    def __init__(self, num_envs, num_actions, debug_envs=None):
        """Set up and load you model here"""
        super().__init__(num_envs, num_actions, debug_envs)
        if self.debug_envs:
            self.run_states = [RunState(self.debug_envs[i]) for i in range(0, num_envs)]
        else:
            self.run_states = [RunState() for i in range(0, num_envs)]

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)

        if done and run_state.step_count != 0:
            raise Exception("The runner framework should have reset the run state")

        run_state.update_reward(reward)

        blstats = BLStats(observation['blstats'])

        time = blstats.get('time')

        player_location = (blstats.get('hero_row'), blstats.get('hero_col'))

        # Our previous run finished, we are now at the start of a new run
        dungeon_number = blstats.get("dungeon_number")
        level_number = blstats.get("level_number")
        dcoord = (dungeon_number, level_number)

        if dungeon_number != 0:
            pass
            #if environment.env.debug: import pdb; pdb.set_trace()

        if run_state.neighborhood is not None: # don't exceute on first turn
            level_changed = (dcoord != run_state.neighborhood.dcoord)
        else:
            level_changed = True

        try:
            level_map = run_state.dmap.dlevels[dcoord]
        except KeyError:
            level_map = run_state.dmap.make_level_map(dungeon_number, level_number, observation['glyphs'], player_location)

            # if we just made the map of level 1 of dungeons of doom, add the staircase on our square
            if dungeon_number == 0 and level_number == 1:
                # EARTH PLANE DCOORD = ?
                EARTH_PLANE_DNUM = -1
                level_map.add_staircase(player_location, new_dcoord=(EARTH_PLANE_DNUM, 1), direction='up')

        level_map.update(player_location)

        if run_state.reading_base_attributes:
            raw_screen_content = bytes(observation['tty_chars']).decode('ascii')
            run_state.update_base_attributes(raw_screen_content)

            if environment.env.debug and run_state.target_roles and run_state.character.base_class not in run_state.target_roles:
                run_state.scumming = True

        # Two cases when we reset inventory: new run or something changed
        if run_state.character:
            if (run_state.character.inventory is None) or ((observation['inv_strs'] != run_state.character.inventory.inv_strs).any()):
                run_state.character.set_inventory(inv.PlayerInventory(run_state, observation, am_hallu=blstats.am_hallu()))

        # we're intentionally using the pre-update run_state here to get a little memory of previous glyphs
        if run_state.glyphs is not None:
            if level_changed: # if we jumped dungeon levels, we don't know the glyph; if our run state ended same thing
                run_state.glyph_under_player = None
            else:
                previous_glyph_on_player = gd.GLYPH_NUMERAL_LOOKUP[run_state.glyphs[player_location]]

                # Don't forget dungeon features just because we're now standing on them
                if not (isinstance(run_state.glyph_under_player, gd.CMapGlyph) and isinstance(previous_glyph_on_player, gd.MonsterGlyph)):
                    run_state.glyph_under_player = previous_glyph_on_player
        previous_glyph_on_player = run_state.glyph_under_player

        run_state.update_observation(observation) # moved after previous glyph futzing

        if run_state.step_count % 1000 == 0:
            print_stats(done, run_state, blstats)

        message = Message(observation['message'], observation['tty_chars'], observation['misc'])
        run_state.handle_message(message)

        if run_state.character: # None until we C-X at the start of game
            run_state.character.update_from_observation(blstats)

        killed_monster_name = RecordedMonsterDeath.involved_monster(message.message)
        if killed_monster_name:
            # TODO need to get better at knowing the square where the monster dies
            # currently bad at ranged attacks, confusion, and more
            if not run_state.last_non_menu_action == utilities.ACTION_LOOKUP[nethack.actions.Command.FIRE]:
                try:
                    delta = physics.action_to_delta[run_state.last_non_menu_action]
                except:
                    if environment.env.debug: import pdb; pdb.set_trace()

                try:
                    recorded_death = RecordedMonsterDeath(
                        (player_location[0] + delta[0], player_location[1] + delta[1]),
                        time,
                        killed_monster_name
                    )
                    if recorded_death.can_corpse:
                        run_state.latest_monster_death = recorded_death
                except Exception as e:
                    print("WARNING: {} for killed monster. Are we hallucinating?".format(str(e)))

        fleeing_monster_name = RecordedMonsterFlight.involved_monster(message.message)
        if fleeing_monster_name:
            try:
                recorded_flight = RecordedMonsterFlight(time, fleeing_monster_name)
                run_state.latest_monster_flight = recorded_flight
            except Exception as e:
                print("WARNING: {} for fleeing monster. Are we hallucinating?".format(str(e)))

        #create staircases. as of NLE 0.7.3, we receive the descend/ascend message while still in the old region
        if len(run_state.message_log) > 1 and ("You descend the" in run_state.message_log[-2] or "You climb" in run_state.message_log[-2]):
            print(run_state.message_log[-2])
            # create the staircases (idempotent)
            if "You descend the" in run_state.message_log[-2]:
                direction = ('down', 'up')
            elif "You climb" in run_state.message_log[-2]:
                direction = ('up', 'down')

            # staircase we just took
            previous_level_map = run_state.dmap.dlevels[run_state.neighborhood.dcoord]
            previous_level_map.add_staircase(run_state.neighborhood.absolute_player_location, new_dcoord=dcoord, new_location=player_location, direction=direction[0]) # start, end, end
            # staircase it's implied we've arrived on (probably breaks in the Valley)
            level_map.add_staircase(player_location, new_dcoord=run_state.neighborhood.dcoord, new_location=run_state.neighborhood.absolute_player_location, direction=direction[1]) # start, end, end 
            print("OLD DCOORD: {} NEW DCOORD: {}".format(run_state.neighborhood.dcoord, dcoord))

        if "Something is written here in the dust" in message.message:
            # TODO When we learn to write in the dust we need to be smarter about this
            level_map.warning_engravings[player_location] = True

        if "more skilled" in message.message or "most skilled" in message.message:
            print(message.message)

        if "corpse tastes" in message.message:
            print(message.message)

        if "You finish your dressing maneuver" in message.message or "You finish taking off" in message.message:
            print(message.message)

        if "It's a wall" in message.message and environment.env.debug:
            if environment.env.debug:
                pass
                #import pdb; pdb.set_trace() # we bumped into a wall but this shouldn't have been possible
                # examples of moments when this can happen: are blind and try to step into shop through broken wall that has been repaired by shopkeeper but we've been unable to see

        if "don't have anything to eat" in message.message and environment.env.debug:
            #import pdb; pdb.set_trace()
            pass

        ###################################################
        # We are done observing and ready to start acting #
        ###################################################

        menu_plan_retval = None
        if message:
            menu_plan_retval = run_state.run_menu_plan(message)
            ### GET MENU_PLAN RETVAL ###

        if menu_plan_retval is None and message.has_more and not run_state.active_menu_plan.in_interactive_menu:
            retval = utilities.ACTION_LOOKUP[nethack.actions.TextCharacters.SPACE]
            dummy_menu_plan = type('MenuPlan', (), {"name":"hit space if more", "advisor":background_advisor})()
            run_state.log_action(retval, menu_plan=dummy_menu_plan)
            return retval

        if menu_plan_retval is not None: # wait to return menu_plan retval, in case our click through more is supposed to override behavior in non-interactive menu plan
            run_state.log_action(menu_plan_retval, menu_plan=run_state.active_menu_plan)
            return menu_plan_retval

        if message.has_more:
            if environment.env.debug: pdb.set_trace() # should have been handled by our menu plan or by our blind mashing of space

        if not run_state.character:
            retval = utilities.ACTION_LOOKUP[nethack.actions.Command.ATTRIBUTES]
            run_state.reading_base_attributes = True
            dummy_menu_plan = type('MenuPlan', (), {"name":"look up attributes at game start", "advisor":background_advisor})()
            run_state.log_action(retval, menu_plan=dummy_menu_plan)
            return retval

        if run_state.scumming:
            retval = utilities.ACTION_LOOKUP[nethack.actions.Command.QUIT]
            scumming_menu_plan = menuplan.MenuPlan("scumming", self, [
                menuplan.YesMenuResponse("Really quit?")
            ])
            run_state.set_menu_plan(scumming_menu_plan)
            run_state.log_action(retval, menu_plan=scumming_menu_plan)
            return retval

        neighborhood = Neighborhood(
            time,
            player_location,
            observation,
            dcoord,
            level_map,
            run_state.character,
            run_state.last_movement_action,
            previous_glyph_on_player,
            run_state.latest_monster_death,
            run_state.latest_monster_flight,
            run_state.failed_moves_on_square,
            message.feedback
        )
        game_did_advance = run_state.check_gamestate_advancement(neighborhood)

        ############################
        ### NEIGHBORHOOD UPDATED ###
        ############################
        run_state.update_neighborhood(neighborhood)
        ############################

        oracle = advs.Oracle(run_state, run_state.character, neighborhood, message, blstats)

        for advisor in advisor_sets.new_advisors:
            advice = advisor.advice_on_conditions(run_state.rng, run_state, run_state.character, oracle)
            if advice is not None:
                #print(advice)
                if advice.action == nethack.actions.Command.PRAY:
                    run_state.character.last_pray_time = time
                    run_state.character.last_pray_reason = advice.advisor # advice.advisor because we want to be more specific inside composite advisors

                menu_plan = advice.menu_plan

                if game_did_advance is True or utilities.ACTION_LOOKUP[advice.action] not in run_state.actions_without_consequence:
                    break

        if isinstance(advice.advisor, advs.FallbackSearchAdvisor):
            #if environment.env.debug: import pdb; pdb.set_trace()
            print("WARNING: Fell through advisors to fallback search")

        retval = utilities.ACTION_LOOKUP[advice.action]

        run_state.log_action(retval, advice=advice) # don't log menu plan because this wasn't a menu plan action

        if menu_plan is not None:
            run_state.set_menu_plan(menu_plan)

        return retval

    def batched_step(self, observations, rewards, dones, infos):
        """
        Perform a batched step on lists of environment outputs.

        Each argument is a list of the respective gym output.
        Returns an iterable of actions.
        """
        actions = [self.step(self.run_states[i], observations[i], rewards[i], dones[i], infos[i]) for i in range(self.num_envs)]
        return actions
