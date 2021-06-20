import random

import numpy as np

from nle import nethack
from agents.base import BatchedAgent

# Config variable that are screwing with me
# pile_limit

def keypress_action(ascii_ord):
    action = nethack.ACTIONS.index(ascii_ord)
    if action is None:
        # import pdb; pdb.set_trace()
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

class MenuPlan():
    def __init__(self, match_to_keypress):
        self.match_to_keypress = match_to_keypress
        self.keypress_count = 0

    def interact(self, ascii_message):
        # import pdb; pdb.set_trace()
        for k, v in self.match_to_keypress.items():
            if k in ascii_message:
                self.keypress_count += 1
                return v
        if self.keypress_count == 0:
            # Can misfire if interrupting message
            # import pdb; pdb.set_trace()
            pass
        return None

class RunState():
    def __init__(self):
        self.reset()

    def reset(self):
        self.step_count = 0
        self.reward = 0
        self.done = False
        self.time = None
        self.tty = None
        self.active_menu_plan = None
        self.message_log = []
        self.action_log = []

    def update(self, done, reward, observation):
        self.done = done
        self.step_count += 1
        self.reward += reward
        # Potentially useful for checking stalls
        self.time = BLStats(observation['blstats']).get('time')
        self.tty = observation['tty_chars']

    def set_menu_plan(self, menu_plan):
        self.active_menu_plan = menu_plan

    def run_menu_plan(self, message):
        if not self.active_menu_plan:
            return None
        retval = self.active_menu_plan.interact(message)
        if retval is None:
            self.active_menu_plan = None
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

def check_stall(run_state, observation):
    if np.array_equal(run_state.tty, observation['tty_chars']) and \
        run_state.time == BLStats(observation['blstats']).get('time') and \
            not "It's " in bytes(observation['tty_chars'][0]).decode('ascii'):
            import pdb; pdb.set_trace()

class CustomAgent(BatchedAgent):
    """A example agent... that simple acts randomly. Adapt to your needs!"""

    def __init__(self, num_envs, num_actions):
        """Set up and load you model here"""
        super().__init__(num_envs, num_actions)
        self.run_states = [RunState()] * num_envs

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)
        # run_state stuff: Currently only for logging
        run_state.update(done, reward, observation)
        if done:
            print_stats(run_state, BLStats(observation['blstats']))
            run_state.reset()

        if run_state.step_count % 1000 == 0:
            print_stats(run_state, BLStats(observation['blstats']))

        if np.count_nonzero(observation['message']) > 0:
            message = bytes(observation['message']).decode('ascii')
            run_state.log_message(message)
        else:
            message = ''

        if message:
            retval = run_state.run_menu_plan(message)
            if retval is not None:
                run_state.log_action(retval)
                return retval

        possible_actions = list(nethack.actions.CompassDirection)

        # Look at the message to figure out whether we need to press space..

        ascii_top_lines = bytes(observation['tty_chars'][0:3]).decode('ascii')
        # Can see here or feel here. Things can be lowercase (I forget why)
        if "--More--" in ascii_top_lines or "hings that" in ascii_top_lines:
            # NLE doesn't pass through the --More-- in its observation
            # ascii_message = bytes(observation['message']).decode('ascii')
            # So let's go look for it
            # With pile_limit > 1, we can get a --More-- without a message
            # # np.count_nonzero(observation['message']) > 0
            retval = nethack.ACTIONS.index(nethack.actions.TextCharacters.SPACE)
            run_state.log_action(retval)
            return retval
        elif "--More--" in bytes(observation['tty_chars']).decode('ascii'):
            # import pdb; pdb.set_trace()
            retval = nethack.ACTIONS.index(nethack.actions.TextCharacters.SPACE)
            run_state.log_action(retval)
            return retval

        if BLStats(observation['blstats']).get('hunger_state') > 2:
            try:
                food_index = observation['inv_oclasses'].tolist().index(7)
            except ValueError:
                food_index = None
            if food_index:
                # If this runs while we're standing on food, we'll get wedged
                # print("EATING")
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
