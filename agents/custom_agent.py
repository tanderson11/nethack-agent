import random

import numpy as np
import itertools

from nle import nethack
from agents.base import BatchedAgent

import glyphs as gd
import environment

if environment.env.debug:
    import pdb

# Config variable that are screwing with me
# pile_limit

def keypress_action(ascii_ord):
    action = nethack.ACTIONS.index(ascii_ord)
    if action is None:
        raise Exception("Bad keypress")
    return action

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
                if ARS.rs.active_menu_plan.handles_bad_messages: # if our active menu plan handles bad messages, assume that this unparsed message is going to be handled by the plan
                    pass
                else:
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

class Square():
    def __init__(self, glyph, visits):
        self.glyph = glyph
        self.visits = visits

class Neighborhood():
    cardinal_action_index_to_offsets = {
        0: (-1,0),
        1: (0,1),
        2: (1,0),
        3: (0,-1),
        4: (-1,1),
        5: (1,1),
        6: (1,-1),
        7: (-1,-1),
    }

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

    def __init__(self, player_location, observation, novelty_map):
        self.player_location = player_location
        self.player_row, self.player_col = self.player_location

        col_lim = observation['glyphs'].shape[1]
        row_lim = observation['glyphs'].shape[0]

        row_slice = slice(max(self.player_row-1, 0),min(self.player_row+2, row_lim+1)) # +2 because non inclusive on upper end
        col_slice = slice(max(self.player_col-1, 0),min(self.player_col+2, col_lim+1))
        self.glyphs = observation['glyphs'][row_slice, col_slice]
        self.visits = novelty_map.map[row_slice, col_slice]

        directions = list(nethack.actions.CompassDirection)
        self.directions_to_glyphs = {a:self.cardinal_access(a, self.glyphs) for a in directions} # mapping of CompassDirection actions to the glyphs on those spaces
        self.directions_to_visits = {a:self.cardinal_access(a, self.visits) for a in directions}


    def cardinal_access(self, a, target):
        action_index = nethack.ACTIONS.index(a)
        assert action_index in range(0, 16), "action should be a CompassDirection or CompassDirectionLonger. It is {}, {}".format(a.name, a.value) # compass direction and compasss direction longer
        if action_index > 7:
            action_index = action_index % 8 # CompassDirectionLonger -> CompassDirection

        offset = self.__class__.cardinal_action_index_to_offsets[action_index]
        try:
            row_offset, col_offset = offset
            directional_target = target[1+row_offset, 1+col_offset]
            
        except IndexError: #sometimes we are on the edge of the map
            return None

        return directional_target

    def glyph_set_to_directions(self, glyph_set):
        matches = np.isin(self.glyphs, glyph_set)
        directions = self.__class__.action_grid[matches]

        if directions.any():
            return directions

        return None


    def walkable_directions(self):
        #if environment.env.debug: pdb.set_trace()
        return [a for a,g in self.directions_to_glyphs.items() if g and gd.is_walkable_glyph(g)]

class MenuPlan():
    def __init__(self, name, match_to_keypress, queue_final=None, handles_bad_messages=None):
        self.name = name
        self.match_to_keypress = match_to_keypress
        self.keypress_count = 0

        self.handles_bad_messages = handles_bad_messages
        self.queue_final = queue_final

        self.end_flag = False

    def interact(self, message_obj):
        for k, v in self.match_to_keypress.items():
            if k in message_obj.message:
                self.keypress_count += 1
                return v


        if self.keypress_count == 0:
            pass

        if self.queue_final and not self.end_flag:
            #if environment.env.debug: pdb.set_trace()
            self.end_flag = True
            return self.queue_final
        else:
            return None

    def __repr__(self):
        return self.name

BackgroundMenuPlan = MenuPlan("background",{
    '"Hello stranger, who are you?" - ': keypress_action(ord('\r')),
    "Call a ": keypress_action(ord('\r')),
    "Call an ": keypress_action(ord('\r')),
    "Really attack": nethack.ACTIONS.index(nethack.actions.Command.ESC),
    "Shall I remove": nethack.ACTIONS.index(nethack.actions.Command.ESC),
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
            if self.active_menu_plan.end_flag or retval is None:
                #if environment.env.debug and self.active_menu_plan.end_flag: pdb.set_trace()
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
        self.run_states = [RunState()] * num_envs
        if self.debug_envs:
            for i, env in enumerate(self.debug_envs):
                self.run_states[i].debug_env = env

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)

        blstats = BLStats(observation['blstats'])

        player_location = (blstats.get('hero_row'), blstats.get('hero_col'))
        try:
            previous_glyph_on_player = run_state.glyphs[player_location]
            #if environment.env.debug: pdb.set_trace()
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

        neighborhood = Neighborhood(player_location, observation, run_state.novelty_map)

        if "staircase down here" in message.message or previous_glyph_on_player == gd.DOWNSTAIRS_GLYPH: # the staircase down here message only appears if there's also an object on the square, so this isn't really what I want
            if previous_glyph_on_player == gd.DOWNSTAIRS_GLYPH:
                #if environment.env.debug: pdb.set_trace()
                pass
            retval = nethack.ACTIONS.index(nethack.actions.MiscDirection.DOWN)
            run_state.log_action(retval)
            return retval

        possible_actions = neighborhood.walkable_directions()

        total_visits = np.sum(neighborhood.visits) - neighborhood.visits[1,1] # visits to squares other than center

        if total_visits > 0:
            weighted_visits = (1 - (0.99*neighborhood.visits / total_visits)) # such that if you've only visited one adjacent, it's given a 99% discount
            action_weights = np.array([neighborhood.cardinal_access(a, weighted_visits) for a in possible_actions])
            if action_weights is None and environment.debug: pdb.set_trace()
            action_weights = action_weights / sum(action_weights)
        else:
            action_weights = [1/len(possible_actions) for a in possible_actions]

        
        if "This door is locked" in message.message:
            possible_actions = [nethack.actions.Command.KICK]
            action_weights = [1.]
            door_directions = neighborhood.glyph_set_to_directions(gd.DOOR_GLYPHS)
            if len(door_directions) > 0:
                a = random.choice(door_directions)
            else: # we got the locked door message but didn't find a door
                a = None
                if environment.env.debug: pdb.set_trace()
                pass
            menu_plan = MenuPlan("kick", {
                "In what direction?": nethack.ACTIONS.index(a),
            })
            run_state.set_menu_plan(menu_plan)

        if blstats.get('hunger_state') > 2:
            try:
                FOOD_CLASS = 7
                food_index = observation['inv_oclasses'].tolist().index(FOOD_CLASS)
            except ValueError:
                food_index = None
            if food_index:
                letter = observation['inv_letters'][food_index]
                possible_actions = [nethack.actions.Command.EAT]
                action_weights = [1.]
                menu_plan = MenuPlan("eat", {
                    "here; eat": keypress_action(ord('n')),
                    "want to eat?": keypress_action(letter),
                    "You succeed in opening the tin.": keypress_action(ord(' ')),
                    "smells like": keypress_action(ord('y')),
                    "Rotten food!": keypress_action(ord(' ')),
                    "Eat it?": keypress_action(ord('y')),
                })
                run_state.set_menu_plan(menu_plan)
            else:
                #if environment.env.debug: pdb.set_trace()
                possible_actions = [nethack.actions.Command.PRAY]
                action_weights = [1.]
                menu_plan = MenuPlan("pray", {
                    "Are you sure you want to pray?": keypress_action(ord('y')),
                })
                run_state.set_menu_plan(menu_plan)

        action = np.random.choice(possible_actions, p=action_weights)

        retval = nethack.ACTIONS.index(action)
        run_state.log_action(retval)
        return retval

    def batched_step(self, observations, rewards, dones, infos):
        """
        Perform a batched step on lists of environment outputs.

        Each argument is a list of the respective gym output.
        Returns an iterable of actions.
        """
        actions = [self.step(self.run_states[i], observations[i], rewards[i], dones[i], infos[i]) for i in range(self.num_envs)]
        return actions
