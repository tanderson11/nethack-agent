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
import menuplan
import utilities
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
        self.square = square
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

class Neighborhood():
    action_grid = np.array([
        nethack.actions.CompassDirection.NW,
        nethack.actions.CompassDirection.N,
        nethack.actions.CompassDirection.NE,
        nethack.actions.CompassDirection.W,
        nethack.actions.MiscDirection.WAIT, # maybe this should be None so we can catch unexpected behavior?
        nethack.actions.CompassDirection.E,
        nethack.actions.CompassDirection.SW,
        nethack.actions.CompassDirection.S,
        nethack.actions.CompassDirection.SE,
    ]).reshape(3,3)

    action_to_delta = {
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.NW]: (-1, -1),
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.N]: (-1, 0),
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.NE]: (-1, 1),
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.W]: (0, -1),
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.E]: (0, 1),
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.SW]: (1, -1),
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.S]: (1, 0),
        utilities.ACTION_LOOKUP[nethack.actions.CompassDirection.SE]: (1, 1),
    }

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

    diagonal_moves = np.vectorize(lambda dir: utilities.ACTION_LOOKUP[dir] > 3 and utilities.ACTION_LOOKUP[dir] < 8)(action_grid)

    @staticmethod
    def centered_slices_bounded_on_array(start, radii, target_array):
        row_slice_radius, col_slice_radius = radii
        col_lim = target_array.shape[1]
        row_lim = target_array.shape[0]

        row_start, col_start = start

        row_slice = slice(max(row_start-row_slice_radius, 0), min(row_start+row_slice_radius+1, row_lim)) # +1 because non-inclusive on upper end
        col_slice = slice(max(col_start-col_slice_radius, 0), min(col_start+col_slice_radius+1, col_lim))

        return row_slice, col_slice

    @staticmethod
    def move_slice_center(old_center, new_center, slices):
        old_center_row, old_center_col = old_center
        new_center_row, new_center_col = new_center

        row_translate = old_center_row - new_center_row
        col_translate = old_center_col - new_center_col

        row_slice, col_slice = slices

        relative_row_slice = slice(row_slice.start-row_translate,row_slice.stop-row_translate)
        relative_col_slice = slice(col_slice.start-col_translate,col_slice.stop-col_translate)

        return relative_row_slice, relative_col_slice

    @classmethod
    def raytrace_threat(cls, glyph_grid, source):
        row_lim = glyph_grid.shape[0]
        col_lim = glyph_grid.shape[1]

        ray_offsets = cls.action_to_delta.values()

        masks = []
        for offset in ray_offsets:
            ray_mask = np.full_like(glyph_grid, False, dtype='bool')

            current = source
            current = (current[0]+2*offset[0], current[1]+2*offset[1]) # initial bump so that ranged attacks don't threaten adjacent squares
            while 0 <= current[0] < row_lim and 0 <= current[1] < col_lim:
                glyph = gd.GLYPH_NUMERAL_LOOKUP[glyph_grid[current]]
                if isinstance(glyph, gd.CMapGlyph) and glyph.is_wall: # is this the full extent of what blocks projectiles/rays?
                    break # should we do anything with bouncing rays

                ray_mask[current] = True

                current = (current[0]+offset[0], current[1]+offset[1])


            masks.append(ray_mask)

        can_hit_mask = np.logical_or.reduce(masks)
        return can_hit_mask

    def calculate_threat(self, glyph_grid, player_location_in_glyph_grid):
        INVISIBLE_DAMAGE_THREAT = 6 # gotta do something lol

        n_threat_map = np.zeros_like(glyph_grid)
        damage_threat_map = np.zeros_like(glyph_grid)

        it = np.nditer(glyph_grid, flags=['multi_index'])
        for g in it:
            glyph = gd.GLYPH_NUMERAL_LOOKUP[int(g)]
            if it.multi_index != player_location_in_glyph_grid:
                if (isinstance(glyph, gd.MonsterGlyph) and glyph.has_melee) or isinstance(glyph, gd.InvisibleGlyph or isinstance(glyph, gd.SwallowGlyph)):
                    row_slice, col_slice = Neighborhood.centered_slices_bounded_on_array(it.multi_index, (1, 1), glyph_grid) # radius one box around the location of g
                    n_threat_map[row_slice, col_slice] += 1 # monsters threaten their own squares in this implementation OK? TK 

                    if isinstance(glyph, gd.MonsterGlyph) and glyph.has_melee:
                        damage_threat_map[row_slice, col_slice] += glyph.monster_spoiler.melee_attack_bundle.max_damage

                    if isinstance(glyph, gd.InvisibleGlyph):
                        damage_threat_map[row_slice, col_slice] += INVISIBLE_DAMAGE_THREAT # how should we imagine the threat of invisible monsters?

                    if isinstance(glyph,gd.SwallowGlyph):
                        damage_threat_map[row_slice, col_slice] += gd.GLYPH_NUMERAL_LOOKUP[glyph.swallowing_monster_offset].monster_spoiler.engulf_attack_bundle.max_damage/8 # stomachs do approx 1/8 of the monster damage 

                if (isinstance(glyph, gd.MonsterGlyph) and glyph.has_ranged):
                    can_hit_mask = self.__class__.raytrace_threat(glyph_grid, it.multi_index)
                    n_threat_map[can_hit_mask] += 1
                    damage_threat_map[can_hit_mask] += glyph.monster_spoiler.ranged_attack_bundle.max_damage


        return (n_threat_map, damage_threat_map)

    def __init__(self, player_location, observation, dmap, previous_glyph_on_player, latest_monster_death):
        blstats = BLStats(observation['blstats'])
        self.player_location = player_location
        self.player_row, self.player_col = self.player_location

        window_size = 1

        row_slice, col_slice = Neighborhood.centered_slices_bounded_on_array(player_location, (window_size, window_size), observation['glyphs'])

        # a window into the action grid of the size size and shape as our window into the glyph grid (ie: don't include actions out of bounds on the map)
        action_grid_row_slice, action_grid_col_slice = Neighborhood.move_slice_center(player_location, (1,1), (row_slice,col_slice)) # move center to (1,1) (action grid center)

        self.action_grid = self.__class__.action_grid[action_grid_row_slice, action_grid_col_slice]
        diagonal_moves = self.__class__.diagonal_moves[action_grid_row_slice, action_grid_col_slice]

        self.raw_glyphs = observation['glyphs'][row_slice, col_slice]
        self.glyphs = utilities.vectorized_map(lambda g: gd.GLYPH_NUMERAL_LOOKUP.get(g), self.raw_glyphs)

        self.visits = dmap.visits_map[row_slice, col_slice]
        self.players_square_mask = self.action_grid == self.__class__.action_grid[1,1] # if the direction is the direction towards our square, we're not interested

        #self.player_location_in_neighborhood = 


        walkable_tile = utilities.vectorized_map(lambda g: g.walkable, self.glyphs)
        open_door = utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_open_door, self.glyphs)
        on_doorway = isinstance(previous_glyph_on_player, gd.CMapGlyph) and previous_glyph_on_player.is_open_door

        self.walkable = walkable_tile & ~(diagonal_moves & open_door) & ~(diagonal_moves & on_doorway) # don't move diagonally into open doors

        self.previous_glyph_on_player = previous_glyph_on_player

        large_row_window, large_col_window = Neighborhood.centered_slices_bounded_on_array(player_location, (window_size+1, window_size+1), observation['glyphs'])
        player_location_in_glyph_grid = (self.player_row-large_row_window.start, self.player_col-large_col_window.start)
        threat_row_slice, threat_col_slice = Neighborhood.move_slice_center(self.player_location, player_location_in_glyph_grid, (row_slice, col_slice))

        raw_n_threat, raw_damage_threat = self.calculate_threat(observation['glyphs'][large_row_window,large_col_window], player_location_in_glyph_grid)
        self.n_threat = raw_n_threat[threat_row_slice,threat_col_slice]
        self.damage_threat = raw_damage_threat[threat_row_slice,threat_col_slice]
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
        directions = self.action_grid[matches]

        return directions

    def is_monster(self):
        mons = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) or isinstance(g, gd.SwallowGlyph) or isinstance(g, gd.InvisibleGlyph), self.glyphs)
        return mons

BackgroundMenuPlan = menuplan.MenuPlan("background",{
    '"Hello stranger, who are you?" - ': utilities.keypress_action(ord('\r')),
    "Call a ": utilities.keypress_action(ord('\r')),
    "Call an ": utilities.keypress_action(ord('\r')),
    "Really attack": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC], # Attacking because don't know about peaceful monsters yet
    "Shall I remove": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "Would you wear it for me?": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "zorkmids worth of damage!": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "little trouble lifting": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
})

class Character(NamedTuple):
    base_race: str
    base_class: str
    base_sex: str
    base_alignment: str

    def can_cannibalize(self):
        if self.base_race == 'orc':
            return False
        if self.base_class == 'Caveman' or self.base_class == 'Cavewoman':
            return False
        return True

class RunState():
    def __init__(self, debug_env):
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
                'race': self.character.base_race,
                'class': self.character.base_class,
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
        self.actions_without_consequence = []

        self.last_non_menu_action = None
        self.last_non_menu_action_timestamp = None
        
        self.time_hung = 0
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
        #seed = b'lry4tg=='
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
        character = Character(
            base_sex=base_sex,
            base_race = self.base_race_mapping[attribute_match_1[2]],
            base_class = attribute_match_1[3],
            base_alignment = attribute_match_2[1],
        )
        self.character = character
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
        self.neighborhood = neighborhood

    def log_message(self, message):
        self.message_log.append(message)

    def log_action(self, action, menu_plan=None):
        self.menu_plan_log.append(menu_plan)
        self.action_log.append(action)

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
        run_state.log_message(message.message)


        killed_monster_name = RecordedMonsterDeath.killed_monster(message.message)
        if killed_monster_name:
            # TODO need to get better at knowing the square where the monster dies
            # currently bad at ranged attacks, confusion, and more
            if not run_state.last_non_menu_action == utilities.ACTION_LOOKUP[nethack.actions.Command.FIRE]:
                delta = Neighborhood.action_to_delta[run_state.last_non_menu_action]
                recorded_death = RecordedMonsterDeath(
                    (player_location[0] + delta[0], player_location[1] + delta[1]),
                    blstats.get('time'),
                    killed_monster_name
                )
                if recorded_death.can_corpse:
                    run_state.latest_monster_death = recorded_death

        if "corpse tastes" in message.message:
            print(message.message)

        if "It's a wall" in message.message and environment.env.debug:
            pdb.set_trace() # we bumped into a wall but this shouldn't have been possible

        if message.interactive_menu_class is not None:
            if not run_state.live_interactive_menu:
                run_state.live_interactive_menu = message.interactive_menu_class()
        else:
            run_state.live_interactive_menu = None

        ###################################################
        # We are done observing and ready to start acting #
        ###################################################

        if message.has_more and message.interactive_menu_class is None:
            retval = utilities.ACTION_LOOKUP[nethack.actions.TextCharacters.SPACE]
            run_state.log_action(retval, menu_plan=True)
            return retval

        if not run_state.character:
            retval = utilities.ACTION_LOOKUP[nethack.actions.Command.ATTRIBUTES]
            run_state.reading_base_attributes = True
            run_state.log_action(retval, menu_plan=True)
            return retval

        if message:
            retval = run_state.run_menu_plan(message)
            if retval is not None:
                run_state.log_action(retval, menu_plan=run_state.active_menu_plan)
                return retval

        neighborhood = Neighborhood(
            player_location, observation, run_state.dmap, previous_glyph_on_player, run_state.latest_monster_death)
        game_did_advance = run_state.check_gamestate_advancement(neighborhood)
        run_state.update_neighborhood(neighborhood)

        flags = advs.Flags(blstats, inventory, neighborhood, message)

        #if environment.env.debug: pdb.set_trace()
        for advisor_level in advs.advisors:
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
                    #if action == nethack.actions.Command.EAT: print("eating!", chosen_advice.advisor)

                    menu_plan = chosen_advice.menu_plan
                    break

        try:
            retval = utilities.ACTION_LOOKUP[action]
        except UnboundLocalError:
            print("WARNING: somehow fell all the way out of advisors. Usually means search failed to advance game time due to intrinsic speed.")
            retval = utilities.ACTION_LOOKUP[nethack.actions.Command.SEARCH]
            menu_plan = None
            #if environment.env.debug: pdb.set_trace()
        run_state.log_action(retval)

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
