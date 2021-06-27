from pdb import run
import base64
import os

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
                if not ARS.rs.active_menu_plan.expects_strange_messages:
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

    diagonal_moves = np.vectorize(lambda dir: utilities.ACTION_LOOKUP[dir] > 3 and utilities.ACTION_LOOKUP[dir] < 8)(action_grid)

    def __init__(self, player_location, observation, novelty_map, previous_glyph_on_player):
        self.player_location = player_location
        self.player_row, self.player_col = self.player_location

        col_lim = observation['glyphs'].shape[1]
        row_lim = observation['glyphs'].shape[0]

        # +2 because non inclusive on upper end
        row_slice = slice(max(self.player_row-1, 0),min(self.player_row+2, row_lim))
        # don't actually need to min the upper end because slices automatically stop
        # at an upper boundary, but it's useful in restricting the action grid 
        col_slice = slice(max(self.player_col-1, 0),min(self.player_col+2, col_lim))

        # this highly deranged syntax selects a window in the action_grid equivalent
        # to the window into the glyphs (ie: if we're at the edge of the map,
        # we select the relevant part of the action grid)
        action_grid_row_slice = slice(1+(row_slice.start-self.player_row), 1+(row_slice.stop-self.player_row))
        action_grid_column_slice = slice(1+(col_slice.start-self.player_col), 1+(col_slice.stop-self.player_col))

        self.action_grid = self.__class__.action_grid[action_grid_row_slice, action_grid_column_slice]
        diagonal_moves = self.__class__.diagonal_moves[action_grid_row_slice, action_grid_column_slice]

        vectorized_lookup = np.vectorize(lambda g: gd.GLYPH_LOOKUP.get(g))
        self.raw_glyphs = observation['glyphs'][row_slice, col_slice]
        self.glyphs = vectorized_lookup(self.raw_glyphs)

        self.visits = novelty_map.map[row_slice, col_slice]
        self.players_square_mask = self.action_grid == self.__class__.action_grid[1,1] # if the direction is the direction towards our square, we're not interested

        walkable_tile = np.vectorize(lambda g: g.walkable)(self.glyphs)
        open_door = np.vectorize(lambda g: isinstance(g, gd.CMapGlyph) and g.is_open_door)(self.glyphs)
        on_doorway = isinstance(previous_glyph_on_player, gd.CMapGlyph) and previous_glyph_on_player.is_open_door

        try:
            self.walkable = walkable_tile & ~(diagonal_moves & open_door) & ~(diagonal_moves & on_doorway) # don't move diagonally into open doors
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
    "Really attack": utilities.keypress_action(ord('y')), # Attacking because don't know about peaceful monsters yet
    "Shall I remove": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
    "Would you wear it for me?": utilities.ACTION_LOOKUP[nethack.actions.Command.ESC],
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
        self.rng = self.make_seeded_rng()

        # for mapping purposes
        self.novelty_map = type('NoveltyMap', (), {"dlevel":0})()
        self.glyphs = None

    def make_seeded_rng(self):
        import random
        seed = base64.b64encode(os.urandom(4))
        print(f"Seeding Agent's RNG {seed}")
        return random.Random(seed)

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

        if retval is None and self.active_menu_plan.fallback:
            retval = self.active_menu_plan.fallback
            self.active_menu_plan = BackgroundMenuPlan
            return retval

        if self.active_menu_plan != BackgroundMenuPlan:
            if retval is None:
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
        self.run_states = [RunState() for i in range(0, num_envs)]
        if self.debug_envs:
            for i, env in enumerate(self.debug_envs):
                self.run_states[i].debug_env = env

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)

        blstats = BLStats(observation['blstats'])
        inventory = observation # for now this is sufficient, we always access inv like inventory['inv...']
        player_location = (blstats.get('hero_row'), blstats.get('hero_col'))

        # we're intentionally using the pre-update run_state here to get a little memory of previous glyphs
        if run_state.glyphs is not None:
            previous_glyph_on_player = gd.GLYPH_LOOKUP[run_state.glyphs[player_location]]
            # Don't forget dungeon features just because we're now standing on them
            if not (isinstance(run_state.glyph_under_player, gd.CMapGlyph) and isinstance(previous_glyph_on_player, gd.MonsterGlyph)):
                run_state.glyph_under_player = previous_glyph_on_player
        previous_glyph_on_player = run_state.glyph_under_player

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
            retval = utilities.ACTION_LOOKUP[nethack.actions.TextCharacters.SPACE]
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

        if "solid stone" in message.message or "It's a wall" in message.message:
            if environment.env.debug: pdb.set_trace() # we bumped into a wall but this shouldn't have been possible

        neighborhood = Neighborhood(player_location, observation, run_state.novelty_map, previous_glyph_on_player)
        flags = advs.Flags(blstats, inventory, neighborhood, message)

        #if environment.env.debug: pdb.set_trace()
        for advisor_level in advs.advisors:
            advisors = advisor_level.keys()
            all_advice = [advisor().give_advice(run_state.rng, flags, blstats, inventory, neighborhood, message) for advisor in advisors]
            all_advice = [advice for advice in all_advice if advice]
            if all_advice:
                chosen_advice = run_state.rng.choices(
                    all_advice,
                    weights=map(lambda x: advisor_level[x.advisor], all_advice)
                )[0]
                action = chosen_advice.action
                menu_plan = chosen_advice.menu_plan
                break

        retval = utilities.ACTION_LOOKUP[action]
        run_state.log_action(retval)

        if menu_plan is not None:
            run_state.set_menu_plan(menu_plan)

        #print(retval)
        return retval

    def batched_step(self, observations, rewards, dones, infos):
        """
        Perform a batched step on lists of environment outputs.

        Each argument is a list of the respective gym output.
        Returns an iterable of actions.
        """
        actions = [self.step(self.run_states[i], observations[i], rewards[i], dones[i], infos[i]) for i in range(self.num_envs)]
        return actions
