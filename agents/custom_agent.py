import random

import numpy as np
import itertools

from nle import nethack
from agents.base import BatchedAgent

import advisors as advs
import menuplan
import utilities
import glyphs as gd
import environment

if environment.env.debug:
    import pdb

# Config variable that are screwing with me
# pile_limit

class ActiveRunState():
    def __init__(self):
        rs = None

    def set_active(self, run_state):
        self.rs = run_state

ARS = ActiveRunState()

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
        # Implement There is an altar to Chih Sung-tzu (neutral) here.
        ])
    def __init__(self, message, tty_chars):
        self.raw_message = message
        self.message = ''
        self.has_more = False

        if np.count_nonzero(message) > 0:
            self.message = bytes(message).decode('ascii').rstrip('\x00')

        ascii_top_line = bytes(tty_chars[0]).decode('ascii')
        potential_message = ascii_top_line.strip(' ')
        if not self.message and potential_message:
            if not (potential_message.startswith("You read: ") or potential_message in self.__class__.known_lost_messages):
                if environment.env.debug: pdb.set_trace()
            self.message = potential_message

        ascii_top_lines = ascii_top_line + bytes(tty_chars[1:3]).decode('ascii')
        # Bad conflict with "They say that shopkeepers often remember things that you might forget."
        if "--More--" in ascii_top_lines or "hings that" in ascii_top_lines:
            # NLE doesn't pass through the --More-- in its observation
            # ascii_message = bytes(observation['message']).decode('ascii')
            # So let's go look for it
            # With pile_limit > 1, we can get a --More-- without a message
            # # np.count_nonzero(observation['message']) > 0
            self.has_more = True

        truly_has_more = "--More--" in bytes(tty_chars).decode('ascii')

        if truly_has_more != self.has_more:
            if environment.env.debug: pdb.set_trace()
            self.has_more = truly_has_more

    def __bool__(self):
        return bool(self.message)

class NoveltyMap():
    def __init__(self, dlevel, glyphs, initial_player_location):

        self.dlevel = dlevel
        self.map = np.zeros_like(glyphs)

        self.map[initial_player_location] += 1

    def update(self, player_location):
        self.map[player_location] += 1

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

    def __init__(self, player_location, observation, novelty_map, previous_glyph_on_player):
        self.player_location = player_location
        self.player_row, self.player_col = self.player_location

        col_lim = observation['glyphs'].shape[1]
        row_lim = observation['glyphs'].shape[0]

        row_slice = slice(max(self.player_row-1, 0),min(self.player_row+2, row_lim)) # +2 because non inclusive on upper end
        col_slice = slice(max(self.player_col-1, 0),min(self.player_col+2, col_lim)) # don't actually need to min the upper end because slices automatically stop at an upper boundary, but it's useful in restricting the action grid

        self.action_grid = self.__class__.action_grid[1+(row_slice.start-self.player_row):1+(row_slice.stop-self.player_row), 1+(col_slice.start-self.player_col):1+(col_slice.stop-self.player_col)] # this highly deranged syntax selects a window in the action_grid equivalent to the window into the glyphs (ie: if we're at the edge of the map, we select the relevant part of the action grid)

        vectorized_lookup = np.vectorize(lambda g: gd.GLYPH_LOOKUP.get(g))
        self.raw_glyphs = observation['glyphs'][row_slice, col_slice]
        self.glyphs = vectorized_lookup(self.raw_glyphs)

        self.visits = novelty_map.map[row_slice, col_slice]
        self.players_square_mask = self.action_grid == self.__class__.action_grid[1,1] # if the direction is the direction towards our square, we're not interested

        #self.walkable = ~np.isin(self.glyphs, gd.WALL_GLYPHS)

        walkable_tile = np.vectorize(lambda g: getattr(g, 'walkable', False))(self.glyphs)
        diagonal_tile = np.vectorize(lambda g: nethack.ACTIONS.index(g) > 3 and nethack.ACTIONS.index(g) < 8)(self.action_grid)
        open_door = np.vectorize(lambda g: getattr(g, 'is_open_door', False))(self.glyphs)
        if previous_glyph_on_player is not None:
            on_doorway = getattr(previous_glyph_on_player, 'is_open_door', False)
        else:
            on_doorway = False

        try:
            self.walkable = walkable_tile & ~(diagonal_tile & open_door) & ~(diagonal_tile & on_doorway) # don't move diagonally into open doors
        except TypeError:
            if environment.env.debug: pdb.set_trace()

        self.previous_glyph_on_player = previous_glyph_on_player

    def glyph_set_to_directions(self, glyph_set):
        matches = np.isin(self.raw_glyphs, glyph_set)
        directions = self.action_grid[matches]

        return directions

BackgroundMenuPlan = menuplan.MenuPlan("background",{
    '"Hello stranger, who are you?" - ': utilities.keypress_action(ord('\r')),
    "Call a ": utilities.keypress_action(ord('\r')),
    "Call an ": utilities.keypress_action(ord('\r')),
    "Really attack": utilities.keypress_action(ord('y')),#nethack.ACTIONS.index(nethack.actions.Command.ESC), # Attacking because don't know about peaceful monsters yet
    "Shall I remove": nethack.ACTIONS.index(nethack.actions.Command.ESC),
    "Would you wear it for me?": nethack.ACTIONS.index(nethack.actions.Command.ESC),
})

class RunState():
    def __init__(self):
        self.reset()
        self.debug_env = None

    def reset(self):
        self.step_count = 0
        self.reward = 0
        self.done = False
        self.time = None
        self.tty = None
        self.active_menu_plan = BackgroundMenuPlan
        self.message_log = []
        self.action_log = []
        self.time_hung = 0

        # for mapping purposes
        self.novelty_map = type('NoveltyMap', (), {"dlevel":0})()
        self.glyphs = None

    def update(self, done, reward, observation):
        self.done = done
        self.step_count += 1
        self.reward += reward
        # Potentially useful for checking stalls
        new_time = BLStats(observation['blstats']).get('time')
        if self.time == new_time:
            self.time_hung += 1
        else:
            self.time_hung = 0
        if self.time_hung > 1_000:
            if environment.env.debug: pdb.set_trace()
            pass
        self.time = new_time
        self.tty = observation['tty_chars']

        self.glyphs = observation['glyphs'].copy() # does this need to be a copy?

    def set_menu_plan(self, menu_plan):
        self.active_menu_plan = menu_plan

    def run_menu_plan(self, message):
        retval = self.active_menu_plan.interact(message)

        if self.active_menu_plan != BackgroundMenuPlan:
            if  retval is None:
                self.active_menu_plan = BackgroundMenuPlan
                retval = self.active_menu_plan.interact(message)

        return retval

    def log_message(self, message):
        self.message_log.append(message)

    def log_action(self, action):
        self.action_log.append(action)

def print_stats(run_state, blstats):
    print(
        ("[Done] " if run_state.done else "") +
        f"After step {run_state.step_count}: " + \
        f"reward {run_state.reward}, " + \
        f"dlevel {blstats.get('level_number')}, " + \
        f"elevel {blstats.get('experience_level')}, " + \
        f"time {blstats.get('time')}"
    )

class CustomAgent(BatchedAgent):
    """A example agent... that simple acts randomly. Adapt to your needs!"""

    def __init__(self, num_envs, num_actions, debug_envs=None):
        """Set up and load you model here"""
        super().__init__(num_envs, num_actions, debug_envs)
        self.run_states = [RunState() for i in range(0, num_actions)]
        if self.debug_envs:
            for i, env in enumerate(self.debug_envs):
                self.run_states[i].debug_env = env

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)

        blstats = BLStats(observation['blstats'])
        inventory = observation # for now this is sufficient, we always access inv like inventory['inv...']
        player_location = (blstats.get('hero_row'), blstats.get('hero_col'))

        try:
            previous_glyph_on_player = gd.GLYPH_LOOKUP[run_state.glyphs[player_location]] # we're intentionally using the un-updated run_state here to get a little memory of previous glyphs
        except TypeError:
            previous_glyph_on_player = None

        # run_state stuff: Currently only for logging
        run_state.update(done, reward, observation)
        if done:
            print_stats(run_state, blstats)
            run_state.reset()

        if run_state.step_count % 1000 == 0:
            print_stats(run_state, blstats)

        message = Message(observation['message'], observation['tty_chars'])
        run_state.log_message(message.message)


        if message.has_more:
            retval = nethack.ACTIONS.index(nethack.actions.TextCharacters.SPACE)
            run_state.log_action(retval)
            return retval

        if message:
            retval = run_state.run_menu_plan(message)
            if retval is not None:
                run_state.log_action(retval)
                return retval

        # mapping
        dlevel = blstats.get('level_number')
        if run_state.novelty_map.dlevel != dlevel:
            run_state.novelty_map = NoveltyMap(dlevel, observation['glyphs'], player_location)
        else:
            run_state.novelty_map.update(player_location)

        if "solid stone" in message.message:
            if environment.env.debug: pdb.set_trace() # we bumped into a wall but this shouldn't have been possible

        neighborhood = Neighborhood(player_location, observation, run_state.novelty_map, previous_glyph_on_player)
        flags = advs.Flags(blstats, inventory, neighborhood, message)

        #if environment.env.debug: pdb.set_trace()
        possible_actions, menu_plans = zip(*[advisor.give_advice(flags, blstats, inventory, neighborhood, message) for advisor in advs.advisors])
        possible_actions = np.array(possible_actions)
        menu_plans = np.array(menu_plans)

        # somehow choose the action cleverly
        # for now we'll just choose first non none action by priority
        for i,a in enumerate(possible_actions):
            if a is not None:
                action = a
                menu_plan = menu_plans[i]
                break


        retval = nethack.ACTIONS.index(action)
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
