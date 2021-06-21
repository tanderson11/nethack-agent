import random

import numpy as np
import pdb

from nle import nethack
from agents.base import BatchedAgent

import environment

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
        'hero col', 'hero_row', 'strength_pct', 'strength', 'dexterity', 'constitution', 
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
                pass
            self.message = potential_message

        ascii_top_lines = ascii_top_line + bytes(tty_chars[1:3]).decode('ascii')
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

class MenuPlan():
    def __init__(self, match_to_keypress):
        self.match_to_keypress = match_to_keypress
        self.keypress_count = 0

    def interact(self, message_obj):
        for k, v in self.match_to_keypress.items():
            if k in message_obj.message:
                self.keypress_count += 1
                return v
        if self.keypress_count == 0:
            pass
        return None

BackgroundMenuPlan = MenuPlan({
    '"Hello stranger, who are you?" - ': keypress_action(ord('\r')),
    "Call a ": keypress_action(ord('\r')),
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

    def set_menu_plan(self, menu_plan):
        self.active_menu_plan = menu_plan

    def run_menu_plan(self, message):
        if not self.active_menu_plan:
            return None
        retval = self.active_menu_plan.interact(message)
        if retval is None:
            self.active_menu_plan = BackgroundMenuPlan
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

    def __init__(self, num_envs, num_actions, debug_envs):
        """Set up and load you model here"""
        super().__init__(num_envs, num_actions, debug_envs)
        self.run_states = [RunState()] * num_envs
        if self.debug_envs:
            for i, env in enumerate(self.debug_envs):
                self.run_states[i].debug_env = env

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)

        # run_state stuff: Currently only for logging
        run_state.update(done, reward, observation)
        if done:
            print_stats(run_state, BLStats(observation['blstats']))
            run_state.reset()

        if run_state.step_count % 1000 == 0:
            print_stats(run_state, BLStats(observation['blstats']))

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

        possible_actions = list(nethack.actions.CompassDirection)

        if BLStats(observation['blstats']).get('hunger_state') > 2:
            try:
                food_index = observation['inv_oclasses'].tolist().index(7)
            except ValueError:
                food_index = None
            if food_index:
                letter = observation['inv_letters'][food_index]
                possible_actions = [nethack.actions.Command.EAT]
                menu_plan = MenuPlan({
                    "here; eat": keypress_action(ord('n')),
                    "want to eat?": keypress_action(letter),
                    "You succeed in opening the tin.": keypress_action(ord(' ')),
                    "smells like": keypress_action(ord('y')),
                    "Rotten food!": keypress_action(ord(' ')),
                    "Eat it?": keypress_action(ord('y')),
                })
                run_state.set_menu_plan(menu_plan)

        action = random.choice(possible_actions)
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
