from pdb import run
import base64
import os
import re

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

class RecordedMonsterDeath():
    def __init__(self, square, time, monster_name):
        self.square = square
        self.time = time
        self.monster_name = monster_name
        self.monster_glyph = gd.get_by_name(gd.MonsterGlyph, self.monster_name)

    death_log_line = re.compile("^You kill the (.*)!$")

    @classmethod
    def generate_from_message(cls, square, time, message):
        # "You kill the lichen!" is an example message
        match = re.match(cls.death_log_line, message)
        if match is None:
            return None
        monster_name = match[1]
        return cls(square, time, monster_name)

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
        self.has_more = False
        self.interactive_menu_class = None

        if np.count_nonzero(message) > 0:
            try:
                self.message = bytes(message).decode('ascii').rstrip('\x00')
            except UnicodeDecodeError:
                if environment.env.debug: pdb.set_trace()

        ascii_top_line = bytes(tty_chars[0]).decode('ascii')
        potential_message = ascii_top_line.strip(' ')
        if not self.message and potential_message:
            if not (potential_message.startswith("You read: ") or potential_message in self.__class__.known_lost_messages):
                if not ARS.rs.active_menu_plan.expects_strange_messages:
                    if environment.env.debug: pdb.set_trace()
            self.message = potential_message

        self.interactive_menu_class = None
        if "Pick up what?" in self.message or (self.message in gd.ObjectGlyph.OBJECT_CLASS_LABEL_IN_INVENTORY):
            self.interactive_menu_class = menuplan.InteractiveInventoryMenu
        elif "Pick a skill to advance:" in self.message:
            self.interactive_menu_class = menuplan.InteractiveEnhanceSkillsMenu

        ascii_top_lines = ascii_top_line + bytes(tty_chars[1:3]).decode('ascii')
        # Bad conflict with "They say that shopkeepers often remember things that you might forget."
        if "--More--" in ascii_top_lines or "hings that" in ascii_top_lines:
            # NLE doesn't pass through the --More-- in its observation
            # ascii_message = bytes(observation['message']).decode('ascii')
            # So let's go look for it
            # With pile_limit > 1, we can get a --More-- without a message
            # # np.count_nonzero(observation['message']) > 0
            self.has_more = True

        truly_has_more = (misc_observation[2] == 1)

        if truly_has_more != self.has_more and self.interactive_menu_class is None:
            if environment.env.debug: pdb.set_trace()
            self.has_more = truly_has_more

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
    def move_slice_center(old_center, new_center, slices): # we have a slice (4,7) with a center of (5) that implies we want the slice
        old_center_row, old_center_col = old_center
        new_center_row, new_center_col = new_center

        row_translate = old_center_row - new_center_row
        col_translate = old_center_col - new_center_col

        row_slice, col_slice = slices

        relative_row_slice = slice(row_slice.start-row_translate,row_slice.stop-row_translate)
        relative_col_slice = slice(col_slice.start-col_translate,col_slice.stop-col_translate)

        #pdb.set_trace()
        return relative_row_slice, relative_col_slice

    def calculate_threat(self, glyph_grid, player_location_in_glyph_grid):
        threat_map = np.zeros_like(glyph_grid)

        it = np.nditer(glyph_grid, flags=['multi_index'])
        for g in it:
            glyph = gd.GLYPH_NUMERAL_LOOKUP[int(g)]
            if it.multi_index != player_location_in_glyph_grid and (isinstance(glyph, gd.MonsterGlyph) and glyph.has_melee) or isinstance(glyph, gd.InvisibleGlyph or isinstance(glyph,gd.SwallowGlyph)):
                row_slice, col_slice = Neighborhood.centered_slices_bounded_on_array(it.multi_index, (1, 1), glyph_grid) # radius one box around the location of g
                threat_map[row_slice, col_slice] += 1 # monsters threaten their own squares in this implementation OK? TK 

        return threat_map

    def __init__(self, player_location, observation, dmap, previous_glyph_on_player):
        self.player_location = player_location
        self.player_row, self.player_col = self.player_location

        col_lim = observation['glyphs'].shape[1]
        row_lim = observation['glyphs'].shape[0]

        window_size = 1

        row_slice, col_slice = Neighborhood.centered_slices_bounded_on_array(player_location, (window_size, window_size), observation['glyphs'])

        # a window into the action grid of the size size and shape as our window into the glyph grid (ie: don't include actions out of bounds on the map)
        action_grid_row_slice, action_grid_column_slice = Neighborhood.move_slice_center(player_location, (1,1), (row_slice,col_slice)) # move center to (1,1) (action grid center)

        self.action_grid = self.__class__.action_grid[action_grid_row_slice, action_grid_column_slice]
        diagonal_moves = self.__class__.diagonal_moves[action_grid_row_slice, action_grid_column_slice]

        vectorized_lookup = np.vectorize(lambda g: gd.GLYPH_NUMERAL_LOOKUP.get(g))
        self.raw_glyphs = observation['glyphs'][row_slice, col_slice]
        self.glyphs = vectorized_lookup(self.raw_glyphs)

        self.visits = dmap.visits_map[row_slice, col_slice]
        self.players_square_mask = self.action_grid == self.__class__.action_grid[1,1] # if the direction is the direction towards our square, we're not interested

        walkable_tile = np.vectorize(lambda g: g.walkable)(self.glyphs)
        open_door = np.vectorize(lambda g: isinstance(g, gd.CMapGlyph) and g.is_open_door)(self.glyphs)
        on_doorway = isinstance(previous_glyph_on_player, gd.CMapGlyph) and previous_glyph_on_player.is_open_door

        try:
            self.walkable = walkable_tile & ~(diagonal_moves & open_door) & ~(diagonal_moves & on_doorway) # don't move diagonally into open doors
        except TypeError:
            if environment.env.debug: pdb.set_trace()

        self.previous_glyph_on_player = previous_glyph_on_player

        large_row_window, large_col_window = Neighborhood.centered_slices_bounded_on_array(player_location, (window_size+1, window_size+1), observation['glyphs'])
        player_location_in_glyph_grid = (self.player_row-large_row_window.start, self.player_col-large_col_window.start)
        threat_row_slice, threat_col_slice = Neighborhood.move_slice_center(self.player_location, player_location_in_glyph_grid, (row_slice, col_slice))
        self.threat = self.calculate_threat(observation['glyphs'][large_row_window,large_col_window], player_location_in_glyph_grid)[threat_row_slice,threat_col_slice]
        self.threatened = self.threat > 0
        if self.threatened.any(): pass#pdb.set_trace()
        
        #pdb.set_trace()

    def glyph_set_to_directions(self, glyph_set):
        matches = np.isin(self.raw_glyphs, glyph_set)
        directions = self.action_grid[matches]

        return directions

    def is_monster(self):
        return np.vectorize(lambda g: (isinstance(g, gd.MonsterGlyph) or isinstance(g, gd.SwallowGlyph) or isinstance(g, gd.InvisibleGlyph)))(self.glyphs)

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
        print(f"Seeding Agent's RNG {seed}")
        return random.Random(seed)

    def update(self, done, reward, observation):
        self.done = done
        self.step_count += 1
        self.reward += reward

        # we want to track when we are taking game actions that are progressing the game
        # time isn't a totally reliable metric for this, as game time doesn't advance after every action for fast players
        # our metric for time advanced: true if game time advanced or if neighborhood changed
        # neighborhood equality assessed by glyphs and player location

        # Potentially useful for checking stalls
        new_time = BLStats(observation['blstats']).get('time')
        if self.time == new_time:
            self.time_hung += 1
        else:
            self.time_hung = 0
        if self.time_hung > 2_000:
            if environment.env.debug: pdb.set_trace()
            pass
        self.time = new_time
        self.tty = observation['tty_chars']

        self.glyphs = observation['glyphs'].copy() # does this need to be a copy?

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


def print_stats(run_state, blstats):
    print(
        ("[Done] " if run_state.done else "") +
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
        self.run_states = [RunState() for i in range(0, num_envs)]
        if self.debug_envs:
            for i, env in enumerate(self.debug_envs):
                self.run_states[i].debug_env = env

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)

        blstats = BLStats(observation['blstats'])
        level_changed = blstats.get("level_number") != run_state.dmap.level_number or blstats.get("dungeon_number") != run_state.dmap.dungeon_number or done

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

        # run_state stuff: Currently only for logging
        run_state.update(done, reward, observation)
        if done:
            print_stats(run_state, blstats)
            run_state.reset()

        if run_state.step_count % 1000 == 0:
            print_stats(run_state, blstats)

        # mapping
        if level_changed:
            run_state.dmap = DMap(blstats.get("dungeon_number"), blstats.get("level_number"), observation['glyphs'], player_location)
        else:
            run_state.dmap.update(player_location)

        message = Message(observation['message'], observation['tty_chars'], observation['misc'])

        # --- Spooky messages ---
        #diagonal_out_of_doorway_message = "You can't move diagonally out of an intact doorway." in message.message
        #diagonal_into_doorway_message = "You can't move diagonally into an intact doorway." in message.message
        #boulder_in_vain_message = "boulder, but in vain." in message.message
        #boulder_blocked_message = "Perhaps that's why you cannot move it." in message.message
        #carrying_too_much_message = "You are carrying too much to get through." in message.message
        #no_hands_door_message = "You can't open anything -- you have no hands!" in message.message
        #solid_stone_message = "solid stone" in message.message # hopefully only happens when there's a tricky glyph; we drop into debugger later
        #nevermind = "Never mind." in message.message

        #cant_move_that_way_message = diagonal_out_of_doorway_message or diagonal_into_doorway_message or boulder_in_vain_message or boulder_blocked_message or carrying_too_much_message or no_hands_door_message or solid_stone_message
        #peaceful_monster_message = "Really attack" in message.message
        # ---

        #if cant_move_that_way_message or peaceful_monster_message: # if we failed to move, tell the neighborhood so it treats that square as unwalkable

        #last_nonmenu_action_failed = peaceful_monster_message or cant_move_that_way_message or nevermind

        run_state.log_message(message.message)

        if "corpse tastes" in message.message:
            print(message.message)

        if message.interactive_menu_class is not None:
            if not run_state.live_interactive_menu:
                run_state.live_interactive_menu = message.interactive_menu_class()
        else:
            run_state.live_interactive_menu = None

        if message.has_more:
            retval = utilities.ACTION_LOOKUP[nethack.actions.TextCharacters.SPACE]
            run_state.log_action(retval, menu_plan=True)
            return retval

        if message:
            retval = run_state.run_menu_plan(message)
            if retval is not None:
                run_state.log_action(retval, menu_plan=run_state.active_menu_plan)
                return retval

        if "It's a wall" in message.message:
            if environment.env.debug: pdb.set_trace() # we bumped into a wall but this shouldn't have been possible

        neighborhood = Neighborhood(player_location, observation, run_state.dmap, previous_glyph_on_player)
        game_did_advance = run_state.check_gamestate_advancement(neighborhood)
        run_state.update_neighborhood(neighborhood)

        flags = advs.Flags(blstats, inventory, neighborhood, message)

        #if environment.env.debug: pdb.set_trace()
        for advisor_level in advs.advisors:
            if advisor_level.check_flags(flags):
                #print(advisor_level, advisor_level.advisors)
                advisors = advisor_level.advisors.keys()
                all_advice = [advisor().advice(run_state.rng, blstats, inventory, neighborhood, message, flags) for advisor in advisors]
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
                    if action == nethack.actions.Command.FIRE: print("firing!");

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
