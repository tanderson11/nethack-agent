from pdb import run
import base64
import csv
import os
import re
from typing import NamedTuple

import numpy as np
import itertools

from nle import nethack
from agents.base import BatchedAgent

import advisors as advs
import advisor_sets

import menuplan
import utilities
import physics
import inventory as inv

import functools

from utilities import ARS
import glyphs as gd
import environment

if environment.env.debug:
    import pdb

# Config variable that are screwing with me
# pile_limit

ACCEPTABLE_CORPSE_AGE = 40

class BLStats():
    bl_meaning = [
        'hero_col', 'hero_row', 'strength_pct', 'strength', 'dexterity', 'constitution',
        'intelligence', 'wisdom', 'charisma', 'score', 'hitpoints', 'max_hitpoints', 'depth', 
        'gold', 'energy', 'max_energy', 'armor_class', 'monster_level', 'experience_level', 
        'experience_points', 'time', 'hunger_state', 'carrying_capacity', 'dungeon_number', 'level_number'
    ]

    def __init__(self, raw):
        self.raw = raw

    def get(self, key):
        return self.raw[self.__class__.bl_meaning.index(key)]

class RecordedMonsterDeath(): 
    def __init__(self, square, time, monster_name):
        self.square = square # doesn't know about dungeon levels
        self.time = time
        self.monster_name = monster_name

        self.monster_glyph = gd.get_by_name(gd.MonsterAlikeGlyph, self.monster_name)

        self.can_corpse = bool(self.monster_glyph.corpse_spoiler)

    death_log_line = re.compile("You kill the (poor )?(invisible )?(saddled )?(.+?)( of .+?)?!")

    @classmethod
    def killed_monster(cls, message):
        match = re.search(cls.death_log_line, message)
        if match is None:
            return None
        monster_name = match[4]
        return monster_name

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
        # Implement There is an altar to Chih Sung-tzu (neutral) here.
        ])

    class Feedback():
        def __init__(self, message):
            self.diagonal_out_of_doorway_message = "You can't move diagonally out of an intact doorway." in message.message
            self.diagonal_into_doorway_message = "You can't move diagonally into an intact doorway." in message.message
            self.collapse_message = "You collapse under your load" in message.message
            #boulder_in_vain_message = "boulder, but in vain." in message.message
            #boulder_blocked_message = "Perhaps that's why you cannot move it." in message.message
            #carrying_too_much_message = "You are carrying too much to get through." in message.message
            #no_hands_door_message = "You can't open anything -- you have no hands!" in message.message
            
            #"Can't find dungeon feature"
            self.failed_move = self.diagonal_out_of_doorway_message or self.diagonal_into_doorway_message or self.collapse_message
            self.nothing_to_eat = "You don't have anything to eat." in message.message
            self.nevermind = "Never mind." in message.message

    def __init__(self, message, tty_chars, misc_observation):
        self.raw_message = message
        self.tty_chars = tty_chars
        self.message = ''
        self.has_more = (misc_observation[2] == 1)
        self.interactive_menu_class = None

        if np.count_nonzero(message) > 0:
            try:
                self.message = bytes(message).decode('ascii').rstrip('\x00')
            except UnicodeDecodeError:
                if environment.env.debug: pdb.set_trace()

        ascii_top_line = bytes(tty_chars[0]).decode('ascii')
        potential_message = ascii_top_line.strip(' ')
        if not self.message and potential_message:
            if not (self.has_more or potential_message.startswith("You read: ") or potential_message in self.__class__.known_lost_messages):
                if not ARS.rs.active_menu_plan.expects_strange_messages:
                    if environment.env.debug: pdb.set_trace()
            self.message = potential_message

        self.interactive_menu_class = None
        if "Pick up what?" in self.message or (self.message in gd.ObjectGlyph.OBJECT_CLASS_LABEL_IN_INVENTORY):
            self.interactive_menu_class = menuplan.InteractiveInventoryMenu
        elif "Pick a skill to advance:" in self.message:
            self.interactive_menu_class = menuplan.InteractiveEnhanceSkillsMenu

        self.feedback = self.__class__.Feedback(self)

    def __bool__(self):
        return bool(self.message)

class DMap():
    def __init__(self, dungeon_number, level_number, glyphs, initial_player_location):
        self.dungeon_number = dungeon_number
        self.level_number = level_number

        self.visits_map = np.zeros_like(glyphs)
        self.visits_map[initial_player_location] += 1
    
    def update(self, player_location):
        self.visits_map[player_location] += 1

class ThreatMap():
    INVISIBLE_DAMAGE_THREAT = 6 # gotta do something lol

    def __init__(self, all_glyphs, player_location, neighborhood_row_slice, neighborhood_col_slice, vision):
        # take the section of the observed glyphs that is relevant
        large_row_window, large_col_window = utilities.centered_slices_bounded_on_array(player_location, (vision, vision), all_glyphs)
        player_location_in_glyph_grid = (player_location[0]-large_row_window.start, player_location[1]-large_col_window.start)
        translated_row_slice, translated_col_slice = utilities.move_slice_center(player_location, player_location_in_glyph_grid, (neighborhood_row_slice, neighborhood_col_slice))
        
        # a way for people to view map that's equivalent to neighborhood: ie. threat_map.melee_threat[threat_map.neighborhood_view].shape == neighborhood.glyphs.shape
        self.neighborhood_view = (translated_row_slice, translated_col_slice)

        self.raw_glyph_grid = all_glyphs[large_row_window,large_col_window]
        self.glyph_grid = utilities.vectorized_map(lambda n: gd.GLYPH_NUMERAL_LOOKUP[n], self.raw_glyph_grid) 
        self.player_location_in_glyph_grid = player_location_in_glyph_grid

        self.calculate_threat()
        #self.calculate_implied_threat()

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

class Neighborhood():
    row_offset_grid = np.array([
        [-1, -1, -1,],
        [0, 0, 0,],
        [1, 1, 1,],
    ])

    col_offset_grid = np.array([
        [-1, 0, 1,],
        [-1, 0, 1,],
        [-1, 0, 1,],
    ])

    def __init__(self, player_location, observation, dmap, character, previous_glyph_on_player, latest_monster_death, feedback):
        blstats = BLStats(observation['blstats'])
        self.player_location = player_location
        self.player_row, self.player_col = self.player_location

        neighborhood_size = 1

        row_slice, col_slice = utilities.centered_slices_bounded_on_array(player_location, (neighborhood_size, neighborhood_size), observation['glyphs'])

        # a window into the action grid of the size size and shape as our window into the glyph grid (ie: don't include actions out of bounds on the map)
        action_grid_row_slice, action_grid_col_slice = utilities.move_slice_center(player_location, (1,1), (row_slice,col_slice)) # move center to (1,1) (action grid center)

        self.action_grid = physics.action_grid[action_grid_row_slice, action_grid_col_slice]
        diagonal_moves = physics.diagonal_moves[action_grid_row_slice, action_grid_col_slice]

        self.raw_glyphs = observation['glyphs'][row_slice, col_slice]
        self.glyphs = utilities.vectorized_map(lambda g: gd.GLYPH_NUMERAL_LOOKUP.get(g), self.raw_glyphs)

        self.visits = dmap.visits_map[row_slice, col_slice]
        self.players_square_mask = self.action_grid == physics.action_grid[1,1] # if the direction is the direction towards our square, we're not interested

        x,y = np.where(self.players_square_mask)
        self.player_location_in_neighborhood = list(zip(x,y))[0]

        walkable_tile = utilities.vectorized_map(lambda g: g.walkable(character), self.glyphs)
        open_door = utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_open_door, self.glyphs)
        on_doorway = isinstance(previous_glyph_on_player, gd.CMapGlyph) and previous_glyph_on_player.is_open_door or feedback.diagonal_out_of_doorway_message

        self.walkable = walkable_tile & ~(diagonal_moves & open_door) & ~(diagonal_moves & on_doorway) # don't move diagonally into open doors

        self.previous_glyph_on_player = previous_glyph_on_player

        vision = 2
        self.threat_map = ThreatMap(observation['glyphs'], self.player_location, row_slice, col_slice, vision)
        self.n_threat = self.threat_map.melee_n_threat[self.threat_map.neighborhood_view]
        self.damage_threat = self.threat_map.melee_damage_threat[self.threat_map.neighborhood_view]
        self.threatened = self.n_threat > 0
        
        self.has_fresh_corpse = np.full_like(self.action_grid, False, dtype='bool')
        if latest_monster_death and latest_monster_death.can_corpse and (blstats.get('time') - latest_monster_death.time < ACCEPTABLE_CORPSE_AGE):
            absolute_row_offsets = self.__class__.row_offset_grid[action_grid_row_slice, action_grid_col_slice] + self.player_location[0]
            absolute_col_offsets = self.__class__.col_offset_grid[action_grid_row_slice, action_grid_col_slice] + self.player_location[1]

            self.has_fresh_corpse = (absolute_row_offsets == latest_monster_death.square[0]) & (absolute_col_offsets == latest_monster_death.square[1])

        self.fresh_corpse_on_square_glyph = None
        if latest_monster_death and latest_monster_death.can_corpse and (player_location == latest_monster_death.square) and (blstats.get('time') - latest_monster_death.time < ACCEPTABLE_CORPSE_AGE):
            self.fresh_corpse_on_square_glyph = latest_monster_death.monster_glyph

    def glyph_set_to_directions(self, glyph_set):
        matches = np.isin(self.raw_glyphs, glyph_set)
        directions = physics.action_grid[matches]

        return directions

    def is_monster(self):
        mons = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) or isinstance(g, gd.SwallowGlyph) or isinstance(g, gd.InvisibleGlyph), self.glyphs)
        return mons
 
background_advisor = advs.BackgroundActionsAdvisor()
BackgroundMenuPlan = menuplan.MenuPlan("background", background_advisor, {
    '"Hello stranger, who are you?" - ': utilities.keypress_action(ord('\r')),
    "Call a ": utilities.keypress_action(ord('\r')),
    "Call an ": utilities.keypress_action(ord('\r')),
    "Really attack": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC], # Attacking because don't know about peaceful monsters yet
    "Shall I remove": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "Would you wear it for me?": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "zorkmids worth of damage!": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "little trouble lifting": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "For what do you wish?": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC], # :(
})

class Character():
    def __init__(self, character_data):
        self.character = character_data

class CharacterData(NamedTuple):
    base_race: str
    base_class: str
    base_sex: str
    base_alignment: str

    def can_cannibalize(self):
        if self.base_race == 'orc':
            return False
        if self.base_class == 'Caveperson':
            return False
        return True

    def sick_from_tripe(self):
        if self.base_class == 'Caveperson':
            return False
        return True

class RunState():
    def __init__(self, debug_env=None):
        self.reset()
        self.debug_env = debug_env
        self.log_path = None
        if environment.env.debug:
            self.log_path = os.path.join(debug_env.savedir, "log.csv")
            with open(self.log_path, 'w') as log_file:
                writer = csv.DictWriter(log_file, fieldnames=self.LOG_HEADER)
                writer.writeheader()

    LOG_HEADER = ['race', 'class', 'level', 'depth', 'branch', 'branch_level', 'time', 'hp', 'max_hp', 'hunger', 'message_log', 'action_log', 'score']

    def log(self):
        if not self.log_path:
            return
        with open(self.log_path, 'a') as log_file:
            writer = csv.DictWriter(log_file, fieldnames=self.LOG_HEADER)
            writer.writerow({
                'race': self.character.character.base_race,
                'class': self.character.character.base_class,
                'level': self.blstats.get('experience_level'),
                'depth': self.blstats.get('depth'),
                'branch': self.blstats.get('dungeon_number'),
                'branch_level': self.blstats.get('level_number'),
                'time': self.blstats.get('time'),
                'hp': self.blstats.get('hitpoints'),
                'max_hp': self.blstats.get('max_hitpoints'),
                'hunger': self.blstats.get('hunger_state'),
                'message_log': "||".join(self.message_log[-10:]),
                'action_log': "||".join([nethack.ACTIONS[num].name for num in self.action_log[-10:]]),
                'score': self.reward,
            })

    def reset(self):
        self.reading_base_attributes = False
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
        
        self.time_hung = 0
        self.time_stuck = 0
        self.rng = self.make_seeded_rng()
        self.glyph_under_player = None
        self.live_interactive_menu = None
        self.time_did_advance = True

        self.neighborhood = None
        self.latest_monster_death = None

        self.menu_plan_log = []

        # for mapping purposes
        self.dmap = type('DMap', (), {"dungeon_number":0, "level_number":0,})()
        self.glyphs = None

    def make_seeded_rng(self):
        import random
        seed = base64.b64encode(os.urandom(4))
        #seed = b'g4kEfA=='
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


        character = CharacterData(
            base_sex=base_sex,
            base_race = self.base_race_mapping[attribute_match_1[2]],
            base_class = base_class,
            base_alignment = attribute_match_2[1],
        )
        self.character = Character(character)

        self.gods_by_alignment[character.base_alignment] = attribute_match_2[2]
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
        if self.time_hung > 2_000:
            if environment.env.debug: pdb.set_trace()
            pass
        self.time = new_time
        self.glyphs = observation['glyphs'].copy() # does this need to be a copy?
        self.blstats = blstats


    def set_menu_plan(self, menu_plan):
        self.active_menu_plan = menu_plan

    def run_menu_plan(self, message):
        retval = self.active_menu_plan.interact(message, self.live_interactive_menu)

        if retval is None and self.active_menu_plan.fallback:
            retval = self.active_menu_plan.fallback
            self.active_menu_plan = BackgroundMenuPlan
            return retval

        if self.active_menu_plan != BackgroundMenuPlan:
            if retval is None:
                self.active_menu_plan = BackgroundMenuPlan
                retval = self.active_menu_plan.interact(message, self.live_interactive_menu)

        return retval

    def update_neighborhood(self, neighborhood):
        if self.neighborhood is not None:
            old_loc = self.neighborhood.player_location
        else:
            old_loc = None
        
        self.neighborhood = neighborhood

        if self.neighborhood is not None and old_loc == self.neighborhood.player_location:
            self.time_stuck += 1
        else:
            self.time_stuck = 0

        if self.time_stuck > 200:
            pass
            #if environment.env.debug: import pdb; pdb.set_trace()

    def log_message(self, message):
        self.message_log.append(message.message)

        if message.feedback.nevermind or message.feedback.nothing_to_eat:
            eat_corpse_flag = False
            if self.advice_log[-1] is None:
                if isinstance(self.menu_plan_log[-1].advisor, advs.EatCorpseAdvisor): # why is this an instance and not a class?
                    eat_corpse_flag = True
            elif self.advice_log[-1].advisor == advs.EatCorpseAdvisor: # have to do this weird thing because we usually handle classes and not instances
                eat_corpse_flag = True

            if eat_corpse_flag:
                print("Deleting record")
                self.latest_monster_death = None

        #if message.feedback.failed_move:
        #    self.failed_move_advisors.append(self.advice_log[-1].action)

    def log_action(self, action, menu_plan=None, advice=None):
        self.menu_plan_log.append(menu_plan)
        self.action_log.append(action)
        self.advice_log.append(advice)

        if menu_plan == None:
            self.last_non_menu_action = action
            self.last_non_menu_action_timestamp = self.time

    def check_gamestate_advancement(self, neighborhood):
        game_did_advance = True
        if self.time is not None and self.last_non_menu_action_timestamp is not None:
            if self.time - self.last_non_menu_action_timestamp == 0: # we keep this timestamp because we won't call this function every step: menu plans bypass it
                neighborhood_diverged = self.neighborhood.player_location != neighborhood.player_location or (self.neighborhood.glyphs != neighborhood.glyphs).any()
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
        run_state.update_reward(reward)

        blstats = BLStats(observation['blstats'])

        # Our previous run finished, we are now at the start of a new run
        if done:
            print_stats(done, run_state, blstats)
            run_state.log()
            run_state.reset()
            level_changed = True
        else:
            level_changed = blstats.get("level_number") != run_state.dmap.level_number or blstats.get("dungeon_number") != run_state.dmap.dungeon_number

        if run_state.reading_base_attributes:
            raw_screen_content = bytes(observation['tty_chars']).decode('ascii')
            run_state.update_base_attributes(raw_screen_content)
            #import pdb; pdb.set_trace()

        _inventory = inv.Inventory(observation)
        #import pdb; pdb.set_trace()

        inventory = observation # for now this is sufficient, we always access inv like inventory['inv...']
        player_location = (blstats.get('hero_row'), blstats.get('hero_col'))

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

        # mapping
        if level_changed:
            run_state.dmap = DMap(blstats.get("dungeon_number"), blstats.get("level_number"), observation['glyphs'], player_location)
        else:
            run_state.dmap.update(player_location)

        message = Message(observation['message'], observation['tty_chars'], observation['misc'])
        run_state.log_message(message)


        killed_monster_name = RecordedMonsterDeath.killed_monster(message.message)
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
                        blstats.get('time'),
                        killed_monster_name
                    )
                    if recorded_death.can_corpse:
                        run_state.latest_monster_death = recorded_death
                except Exception as e:
                    print("WARNING: {} for killed monster. Are we hallucinating?".format(str(e)))

        if "corpse tastes" in message.message:
            print(message.message)

        if "It's a wall" in message.message and environment.env.debug:
            if environment.env.debug: pdb.set_trace() # we bumped into a wall but this shouldn't have been possible

        if message.interactive_menu_class is not None:
            if not run_state.live_interactive_menu:
                run_state.live_interactive_menu = message.interactive_menu_class()
        else:
            run_state.live_interactive_menu = None

        #run_state.advice_log[-1].advisor.give_feedback(message.feedback, run_state) # maybe we want something more like this?

        ###################################################
        # We are done observing and ready to start acting #
        ###################################################

        if message.has_more and message.interactive_menu_class is None:
            retval = utilities.ACTION_LOOKUP[nethack.actions.TextCharacters.SPACE]
            dummy_menu_plan = type('MenuPlan', (), {"name":"hit space if more", "advisor":background_advisor})()
            run_state.log_action(retval, menu_plan=dummy_menu_plan)
            return retval

        if not run_state.character:
            retval = utilities.ACTION_LOOKUP[nethack.actions.Command.ATTRIBUTES]
            run_state.reading_base_attributes = True
            dummy_menu_plan = type('MenuPlan', (), {"name":"look up attributes at game start", "advisor":background_advisor})()
            run_state.log_action(retval, menu_plan="dummy_menu_plan")
            return retval

        if message:
            retval = run_state.run_menu_plan(message)
            if retval is not None:
                run_state.log_action(retval, menu_plan=run_state.active_menu_plan)
                return retval

        neighborhood = Neighborhood(
            player_location, observation, run_state.dmap, run_state.character, previous_glyph_on_player, run_state.latest_monster_death, message.feedback)
        game_did_advance = run_state.check_gamestate_advancement(neighborhood)
        run_state.update_neighborhood(neighborhood)

        flags = advs.Flags(blstats, inventory, neighborhood, message, run_state.character)

        #if environment.env.debug: pdb.set_trace()
        for advisor_level in advisor_sets.small_advisors:
            if advisor_level.check_flags(flags):
                #print(advisor_level, advisor_level.advisors)
                advisors = advisor_level.advisors.keys()
                all_advice = [advisor().advice(run_state.rng, run_state.character, blstats, inventory, neighborhood, message, flags) for advisor in advisors]
                #print(all_advice)
                try:
                    all_advice = [advice for advice in all_advice if advice and (game_did_advance is True or utilities.ACTION_LOOKUP[advice.action] not in run_state.actions_without_consequence)]
                except TypeError:
                    if environment.env.debug: pdb.set_trace()
                if all_advice:
                    chosen_advice = run_state.rng.choices(
                        all_advice,
                        weights=map(lambda x: advisor_level.advisors[x.advisor], all_advice)
                    )[0]
                    action = chosen_advice.action

                    #if action == nethack.actions.Command.QUAFF: print("quaffing!")
                    if action == nethack.actions.Command.FIRE: print("firing!")
                    if action == nethack.actions.Command.WEAR: print("wearing!")
                    #if action == nethack.actions.Command.EAT: print("eating!", chosen_advice.advisor)

                    menu_plan = chosen_advice.menu_plan
                    break

        try:
            retval = utilities.ACTION_LOOKUP[action]
        except UnboundLocalError:
            print("WARNING: somehow fell all the way out of advisors. Could mean fallbacks failed to advance game time due to intrinsic speed.")

            chosen_advice = advs.Advice(None, utilities.ACTION_LOOKUP[nethack.actions.Command.SEARCH], None)
            retval = chosen_advice.action
            menu_plan = chosen_advice.menu_plan
            #if environment.env.debug: pdb.set_trace()

        run_state.log_action(retval, advice=chosen_advice)

        if menu_plan is not None:
            run_state.set_menu_plan(menu_plan)

        if retval == nethack.actions.MiscDirection.WAIT:
            if environment.env.debug: pdb.set_trace()

        return retval

    def batched_step(self, observations, rewards, dones, infos):
        """
        Perform a batched step on lists of environment outputs.

        Each argument is a list of the respective gym output.
        Returns an iterable of actions.
        """
        actions = [self.step(self.run_states[i], observations[i], rewards[i], dones[i], infos[i]) for i in range(self.num_envs)]
        return actions
