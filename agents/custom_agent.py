import base64
import csv
from dataclasses import astuple
import os
import re

import numpy as np
import pandas as pd

from nle import nethack
from agents.base import BatchedAgent

import advisors as advs
from advisors import Advice, ActionAdvice, MenuAdvice, ReplayAdvice
import advisor_sets

import menuplan
from neighborhood import Neighborhood, CurrentSquare
import utilities
import physics
import inventory as inv
import constants
import monster_messages

from utilities import ARS
from character import Character
import constants
import glyphs as gd
import map
from map import DMap, DCoord
import environment
from wizmode_prep import WizmodePrep

from collections import Counter

if environment.env.debug:
    import pdb

# Config variable that are screwing with me
# pile_limit

class BLStats():
    """// From botl.h.
    mn.attr("BL_MASK_STONE") = py::int_(static_cast<int>(BL_MASK_STONE));
    mn.attr("BL_MASK_SLIME") = py::int_(static_cast<int>(BL_MASK_SLIME));
    mn.attr("BL_MASK_STRNGL") = py::int_(static_cast<int>(BL_MASK_STRNGL));
    mn.attr("BL_MASK_FOODPOIS") =
        py::int_(static_cast<int>(BL_MASK_FOODPOIS));
    mn.attr("BL_MASK_TERMILL") = py::int_(static_cast<int>(BL_MASK_TERMILL));
    mn.attr("BL_MASK_BLIND") = py::int_(static_cast<int>(BL_MASK_BLIND));
    mn.attr("BL_MASK_DEAF") = py::int_(static_cast<int>(BL_MASK_DEAF));
    mn.attr("BL_MASK_STUN") = py::int_(static_cast<int>(BL_MASK_STUN));
    mn.attr("BL_MASK_CONF") = py::int_(static_cast<int>(BL_MASK_CONF));
    mn.attr("BL_MASK_HALLU") = py::int_(static_cast<int>(BL_MASK_HALLU));
    mn.attr("BL_MASK_LEV") = py::int_(static_cast<int>(BL_MASK_LEV));
    mn.attr("BL_MASK_FLY") = py::int_(static_cast<int>(BL_MASK_FLY));
    mn.attr("BL_MASK_RIDE") = py::int_(static_cast<int>(BL_MASK_RIDE));
    mn.attr("BL_MASK_BITS") = py::int_(static_cast<int>(BL_MASK_BITS));"""

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

        if strength_25 not in range(3,26):
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

class Message():
    known_lost_messages = set([
        "Things that are here:",
        "Things that you feel here:",
        "Other things that are here:",
        "Other things that you feel here:",
        "Hello Agent, welcome to NetHack!  You are a neutral female gnomish", # see issue_report_1
        "Pick up what?",
        "paperback book named",
        "staircase down",
        ])

    # TODO. It's grunt work, but should learn all the trap messages in
    # # https://github.com/facebookresearch/nle/blob/ceee6396797c5fe00eac66aa909af48e5ee8b04d/src/trap.c
    # Will check for k in message
    match_to_feature = {
        "There is a doorway here.": gd.get_by_name(gd.CMapGlyph, 'ndoor'),
        "There is a broken door here.": gd.get_by_name(gd.CMapGlyph, 'ndoor'),
        "There is an open door here.": gd.get_by_name(gd.CMapGlyph, 'vodoor'),
        "You can't move diagonally out of an intact doorway.": gd.get_by_name(gd.CMapGlyph, 'vodoor'),
        "There is a staircase up here.": gd.get_by_name(gd.CMapGlyph, 'upstair'),
        "There is a staircase down here.": gd.get_by_name(gd.CMapGlyph, 'dnstair'),
        "There is a fountain here.": gd.get_by_name(gd.CMapGlyph, 'fountain'),
        "There is a grave here.": gd.get_by_name(gd.CMapGlyph, 'grave'),
        "There is a sink here.": gd.get_by_name(gd.CMapGlyph, 'sink'),
        "There is an altar to ": gd.get_by_name(gd.CMapGlyph, 'altar'),
        "An arrow shoots out at you!": gd.get_by_name(gd.CMapGlyph, 'arrow_trap'),
        "A little dart shoots out at you!": gd.get_by_name(gd.CMapGlyph, 'dart_trap'),
        "A tower of flame erupts from the floor!": gd.get_by_name(gd.CMapGlyph, 'fire_trap'),
        "A trapdoor in the ceiling opens and a rock falls on your head!": gd.get_by_name(gd.CMapGlyph, 'falling_rock_trap'),
        "Click! You trigger a rolling boulder trap!": gd.get_by_name(gd.CMapGlyph, 'rolling_boulder_trap'),
        "A gush of water hits you": gd.get_by_name(gd.CMapGlyph, 'rust_trap'),
        "A pit opens up under you": gd.get_by_name(gd.CMapGlyph, 'pit'),
        "A pit full of spikes opens up under you": gd.get_by_name(gd.CMapGlyph, 'spiked_pit'),
        "You step onto a polymorph trap!": gd.get_by_name(gd.CMapGlyph, 'polymorph_trap'),
        "A cloud of gas puts you to sleep!": gd.get_by_name(gd.CMapGlyph, 'sleeping_gas_trap'),
        "bear trap closes": gd.get_by_name(gd.CMapGlyph, 'bear_trap'),
        "The fountain dries up!": gd.get_by_name(gd.CMapGlyph, 'room'),
    }

    class Feedback():
        def __init__(self, message):
            self.diagonal_out_of_doorway_message = "You can't move diagonally out of an intact doorway." in message.message
            self.diagonal_into_doorway_message = "You can't move diagonally into an intact doorway." in message.message
            self.collapse_message = "You collapse under your load" in message.message
            self.boulder_in_vain_message = "boulder, but in vain." in message.message
            self.boulder_blocked_message = "Perhaps that's why you cannot move it." in message.message
            self.carrying_too_much_message = "You are carrying too much to get through." in message.message
            self.solid_stone = "It's solid stone" in message.message
            #no_hands_door_message = "You can't open anything -- you have no hands!" in message.message
            
            #"Can't find dungeon feature"
            #self.failed_move =  self.diagonal_into_doorway_message or self.collapse_message or self.boulder_in_vain_message
            self.nothing_to_eat = "You don't have anything to eat." in message.message
            self.nevermind = "Never mind." in message.message
            self.trouble_lifting = "trouble lifting" in message.message
            self.nothing_to_pickup = "There is nothing here to pick up." in message.message


    def get_dungeon_feature_here(self, raw_message):
        for k, v in self.match_to_feature.items():
            if k in raw_message:
                return v

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

        nle_missed_message = False
        potential_message = ascii_top_line.strip(' ')
        if not self.message and potential_message:
            nle_missed_message = True
            self.message = potential_message

        self.dungeon_feature_here = self.get_dungeon_feature_here(self.message)

        if nle_missed_message and not (self.dungeon_feature_here or self.has_more or self.message.startswith("You read: ") or self.message in self.known_lost_messages):
            # print(f"NLE missed this message: {potential_message}")
            pass

        self.feedback = self.__class__.Feedback(self)

    def __bool__(self):
        return bool(self.message)

normal_background_menu_plan_options = [
    menuplan.PhraseMenuResponse('"Hello stranger, who are you?" - ', "Agent"),
    menuplan.PhraseMenuResponse("You are required to supply your name", "Agent"), # Vault message when deaf
    menuplan.EscapeMenuResponse("Call a "),
    menuplan.EscapeMenuResponse("Call an "),
    menuplan.YesMenuResponse("Really attack"),
    menuplan.NoMenuResponse("Shall I remove"),
    menuplan.NoMenuResponse("Would you wear it for me?"),
    menuplan.EscapeMenuResponse("zorkmids worth of damage!"),
    menuplan.EscapeMenuResponse("trouble lifting"),
    menuplan.PhraseMenuResponse("For what do you wish?", "blessed +2 silver dragon scale mail"),
]

wizard_background_menu_plan_options = [
    menuplan.YesMenuResponse("Die?"),
    menuplan.NoMenuResponse("Force the gods to be pleased?"),
    menuplan.NoMenuResponse("Advance skills without practice?"),
    menuplan.EscapeMenuResponse("Where do you want to be teleported?"),
    menuplan.EscapeMenuResponse("Create what kind of monster?"),
    menuplan.EscapeMenuResponse("To what level do you want to teleport?"),
]

background_advisor = advs.BackgroundActionsAdvisor()
BackgroundMenuPlan = menuplan.MenuPlan(
    "background",
    background_advisor,
    normal_background_menu_plan_options + wizard_background_menu_plan_options if environment.env.wizard else normal_background_menu_plan_options
)

class RunState():
    def __init__(self, debug_env=None):
        self.debug_env = debug_env
        self.reset()
        self.log_path = None
        self.target_roles = environment.env.target_roles
        if environment.env.log_runs:
            self.log_root = debug_env.savedir
            self.log_path = os.path.join(self.log_root, "log.csv")
            with open(self.log_path, 'w') as log_file:
                writer = csv.DictWriter(log_file, fieldnames=self.LOG_HEADER)
                writer.writeheader()

    def print_action_log(self, total):
        return "||".join([nethack.ACTIONS[utilities.ACTION_LOOKUP[num]].name for num in self.action_log[(-1 * total):]])

    LOG_HEADER = ['race', 'class', 'level', 'exp points', 'depth', 'branch', 'branch_level', 'time', 'hp', 'max_hp', 'AC', 'encumberance', 'hunger', 'message_log', 'action_log', 'score', 'last_pray_time', 'last_pray_reason', 'scummed', 'ascended', 'step_count', 'l1_advised_step_count', 'l1_need_downstairs_step_count', 'search_efficiency', 'total damage', 'adjacent monster turns', 'died in shop']

    REPLAY_HEADER = ['action', 'run_number', 'dcoord', 'menu_action']

    def log_final_state(self, final_reward, ascended):
        # self.blstats is intentionally one turn stale, i.e. wasn't updated after done=True was observed
        self.update_reward(final_reward)
        print_stats(True, self, self.blstats)
        if self.scumming:
            if not environment.env.debug:
                pass
                #raise Exception("Should not scum except to debug")
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
                'exp points': self.blstats.get('experience_points'),
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
                'step_count': self.step_count,
                'l1_advised_step_count': self.l1_advised_step_count,
                'l1_need_downstairs_step_count': self.l1_need_downstairs_step_count,
                'search_efficiency': len([x for x in self.search_log if x[1]]) / len(self.search_log) if self.search_log else None,
                'total damage': self.total_damage,
                'adjacent monster turns': self.adjacent_monster_turns,
                'died in shop': self.neighborhood.in_shop if self.neighborhood else False,
            })

        with open(os.path.join(self.log_root, 'search_log.csv'), 'a') as search_log_file:
            writer = csv.writer(search_log_file)
            for line in self.search_log:
                writer.writerow(list(line[0]) + [line[1]])

        self.update_counter_json("message_counter.json", Counter(self.message_log))
        #import pdb; pdb.set_trace()
        message_score_df = pd.DataFrame(self.message_log, columns=['message'], index=pd.Series(self.score_against_message_log, name='score'))
        self.dump_dataframe("message_by_score.csv", message_score_df)
        self.update_counter_json("advisor_counter.json", Counter([advice.from_advisor.__class__.__name__ for advice in self.advice_log if isinstance(advice, ActionAdvice)]))

    def dump_dataframe(self, filename, dataframe):
        import json
        try:
            with open(os.path.join(self.log_root, "message_counter.json"), 'r') as counter_file:
                state = json.load(counter_file)
                new_key = max([int(key) for key in state.keys()])
        except FileNotFoundError:
            #state = pd.DataFrame()
            new_key = 0

        dataframe['replay'] = new_key

        with open(os.path.join(self.log_root,  filename), 'a') as f:
            dataframe.to_csv(f, mode='a', header=False)

    def update_counter_json(self, filename, counter):
        import json
        try:
            with open(os.path.join(self.log_root, filename), 'r') as counter_file:
                state = json.load(counter_file)
                #import pdb; pdb.set_trace()
                new_key = max([int(key) for key in state.keys()]) + 1
                #import pdb; pdb.set_trace()
        except FileNotFoundError:
            state = {}
            new_key = 0

        state[new_key] = counter

        with open(os.path.join(self.log_root,  filename), 'w') as counter_file:
            json.dump(state, counter_file)

    def reset(self):
        self.scumming = False
        self.character = None
        self.auto_pickup = True # defaults on
        self.gods_by_alignment = {}

        self.step_count = 0
        self.l1_advised_step_count = 0
        self.l1_need_downstairs_step_count = 0
        self.reward = 0
        self.time = None

        self.active_menu_plan = BackgroundMenuPlan
        self.message_log = []
        self.score_against_message_log = []
        self.action_log = []
        self.advice_log = []
        self.search_log = []
        self.hp_log = []
        self.tty_cursor_log = []
        self.actions_without_consequence = set()

        self.last_non_menu_action = None
        self.last_non_menu_action_timestamp = None
        self.last_non_menu_action_failed_advancement = None
        self.last_non_menu_advisor = None

        self.total_damage = 0
        self.adjacent_monster_turns = 0
        self.last_damage_timestamp = None

        self.queued_name_action = None
        self.last_dropped_item = None
        
        self.time_hung = 0
        self.time_stuck = 0
        self.rng = self.make_seeded_rng()
        self.time_did_advance = True

        self.neighborhood = None
        self.current_square = None
        self.global_identity_map = gd.GlobalIdentityMap()

        self.latest_monster_flight = None

        self.wizmode_prep = WizmodePrep() if environment.env.wizard else None
        self.stall_detection_on = True

        # for mapping purposes
        self.dmap = DMap()
        self.glyphs = None

        self.debugger_on = False
        self.debug_tripwire = False

        self.replay_log_path = None
        self.replay_log = []
        self.replay_index = 0
        if self.debug_env:
            core_seed, disp_seed, _ = self.debug_env.get_seeds()
            replay_log_path = os.path.join(os.path.dirname(__file__), "..", "seeded_runs", f"{core_seed}-{disp_seed}.csv")
            if os.path.exists(replay_log_path):
                self.replay_log_path = replay_log_path
                with open(self.replay_log_path, newline='') as csvfile:
                    reader = csv.DictReader(csvfile)
                    self.replay_log = [row for row in reader]
                    if self.replay_log:
                        self.replay_run_number = int(self.replay_log[-1]['run_number']) + 1
                    else:
                        self.replay_run_number = 0

    def make_seeded_rng(self):
        import random
        seed = base64.b64encode(os.urandom(4))
        #seed = b'C3GzzQ=='
        print(f"Seeding Agent's RNG {seed}")
        return random.Random(seed)

    def replay_advice(self):
        if self.replay_index >= len(self.replay_log):
            return None
        action = int(self.replay_log[self.replay_index]['action'])
        menu_action = self.replay_log[self.replay_index]['menu_action'] == 'True'
        self.replay_index += 1
        return ReplayAdvice(action=action, is_menu_action=menu_action)

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
        self.character.set_class_skills()

        self.gods_by_alignment[self.character.base_alignment] = attribute_match_2[2]
        self.gods_by_alignment[attribute_match_3[2]] = attribute_match_3[1]
        self.gods_by_alignment[attribute_match_3[4]] = attribute_match_3[3]

        if self.character.base_class == constants.BaseRole.Priest:
            self.global_identity_map.is_priest = True

    def update_reward(self, reward):
        self.step_count += 1
        self.reward += reward

    def log_adjacent_monsters(self, n_adjacent):
        self.adjacent_monster_turns += n_adjacent

    def log_damage(self, damage, time):
        self.last_damage_timestamp = time
        self.total_damage += damage

    def update_observation(self, observation):
        # we want to track when we are taking game actions that are progressing the game
        # time isn't a totally reliable metric for this, as game time doesn't advance after every action for fast players
        # our metric for time advanced: true if game time advanced or if neighborhood changed
        # neighborhood equality assessed by glyphs and player location

        blstats = BLStats(observation['blstats'].copy())
        new_time = blstats.get('time')

        self.hp_log.append(blstats.get('hitpoints'))
        if len(self.hp_log) > 1 and self.hp_log[-1] < self.hp_log[-2]:
            damage = self.hp_log[-2] - self.hp_log[-1]
            self.log_damage(damage, new_time)

        # Potentially useful for checking stalls
        if self.time == new_time:
            if self.stall_detection_on:
                self.time_hung += 1
        else:
            self.time_hung = 0
        if self.time_hung > 100:
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
        self.neighborhood = neighborhood
        if self.current_square.location != neighborhood.absolute_player_location:
            raise Exception("Somehow got out of sync")

    def handle_message(self, message):
        self.message_log.append(message.message)
        self.score_against_message_log.append(self.reward)

        if self.character is not None:
            self.character.listen_for_intrinsics(message.message)

        item_on_square = inv.ItemParser.listen_for_item_on_square(self.global_identity_map, self.character, message.message, glyph=self.current_square.glyph_under_player)
        if item_on_square is not None:
            self.current_square.item_on_square = item_on_square

        if item_on_square is not None:
            if self.neighborhood is not None and self.neighborhood.level_map is not None:
                self.neighborhood.level_map.lootable_squares_map[self.current_square.location] = True

        if self.active_menu_plan is not None and self.active_menu_plan.listening_item:
            name_action = self.active_menu_plan.listening_item.process_message(message, self.last_non_menu_action)
            if name_action is not None:
                self.queued_name_action = name_action

        dropped = inv.ItemParser.listen_for_dropped_item(self.global_identity_map, self.character, message.message)
        if dropped is not None:
            self.last_dropped_item = dropped
        inv.ItemParser.listen_for_price_offer(self.global_identity_map, self.character, message.message, last_dropped=self.last_dropped_item)

        if message.feedback.boulder_in_vain_message or message.feedback.diagonal_into_doorway_message or message.feedback.boulder_blocked_message or message.feedback.carrying_too_much_message or message.feedback.solid_stone:
            if message.feedback.carrying_too_much_message:
                self.character.carrying_too_much_for_diagonal = True
            if self.last_non_menu_action in physics.direction_actions:
                self.current_square.failed_moves_on_square.append(self.last_non_menu_action)

                if message.feedback.solid_stone:
                    if environment.env.debug:
                        import pdb; pdb.set_trace()
                    #target_location = physics.Square(*physics.action_to_delta[self.last_non_menu_action]) + self.neighborhood.absolute_player_location
                    # can't add stone: we'll assume it's fog and trample it.
                    # hacky solution: add a wall
                    # no, this also gets trampled
                    #self.neighborhood.level_map.add_feature(target_location, gd.GLYPH_NAME_LOOKUP['vwall'])
            else:
                if self.last_non_menu_action != nethack.actions.Command.TRAVEL:
                    if environment.env.debug: import pdb; pdb.set_trace()

        if message.feedback.trouble_lifting or message.feedback.nothing_to_pickup:
            if message.feedback.trouble_lifting:
                self.character.near_burdened = True
            if self.last_non_menu_action in physics.direction_actions:
                # Autopickup
                pass
            elif not self.last_non_menu_action == nethack.actions.Command.PICKUP:
                if environment.env.debug: import pdb; pdb.set_trace()
            else:
                # Pickup, don't try that again
                self.last_non_menu_action_failed_advancement = True
                self.actions_without_consequence.add(self.last_non_menu_action)

    def log_action(self, advice):
        self.advice_log.append(advice)

        if self.replay_log_path and not isinstance(advice, ReplayAdvice):
            with open(self.replay_log_path, 'a') as log_file:
                writer = csv.DictWriter(log_file, fieldnames=self.REPLAY_HEADER)
                writer.writerow({
                    'action': int(advice.keypress) if isinstance(advice, MenuAdvice) else int(advice.action),
                    'run_number': self.replay_run_number,
                    'dcoord': str(astuple(self.current_square.dcoord)),
                    'menu_action': isinstance(advice, MenuAdvice),
                })

        # TODO lots of compatiblility cruft here

        if isinstance(advice, MenuAdvice):
            return

        if isinstance(advice, ReplayAdvice) and advice.is_menu_action:
            return

        self.action_log.append(advice.action)

        self.last_non_menu_action = advice.action
        self.last_non_menu_action_timestamp = self.time
        self.last_non_menu_action_failed_advancement = False

        if isinstance(advice, ActionAdvice):
            self.last_non_menu_advisor = advice.from_advisor

    def check_gamestate_advancement(self, neighborhood):
        if self.last_non_menu_action in self.actions_without_consequence:
            # Why are we confused about this.
            if environment.env.debug: import pdb; pdb.set_trace()
        game_did_advance = True
        if self.time is not None and self.last_non_menu_action_timestamp is not None and self.time_hung > 4: # time_hung > 4 is a bandaid for fast characters
            if self.time - self.last_non_menu_action_timestamp == 0: # we keep this timestamp because we won't call this function every step: menu plans bypass it
                neighborhood_diverged = self.neighborhood.absolute_player_location != neighborhood.absolute_player_location or (self.neighborhood.glyphs != neighborhood.glyphs).any()
                if not neighborhood_diverged:
                    game_did_advance = False

        if game_did_advance: # we advanced the game state, forget the list of attempted actions
            self.actions_without_consequence = set()
        else:
            self.last_non_menu_action_failed_advancement = True
            self.actions_without_consequence.add(self.last_non_menu_action)

    def log_tty_cursor(self, tty_cursor):
        self.tty_cursor = tty_cursor
        self.tty_cursor_log.append(tuple(tty_cursor))

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
    
    @classmethod
    def generate_action(cls, run_state, observation):
        blstats = BLStats(observation['blstats'])

        time = blstats.get('time')

        player_location = (blstats.get('hero_row'), blstats.get('hero_col'))

        if run_state.character:
            run_state.character.update_inventory_from_observation(
                run_state.global_identity_map, blstats.am_hallu(), observation)

        dungeon_number = blstats.get("dungeon_number")
        level_number = blstats.get("level_number")
        dcoord = DCoord(dungeon_number, level_number)

        try:
            level_map = run_state.dmap.dlevels[dcoord]
            level_map.update(player_location, observation['glyphs'])
        except KeyError:
            level_map = run_state.dmap.make_level_map(dcoord, observation['glyphs'], player_location)

        if run_state.character:
            run_state.dmap.update_target_dcoords(run_state.character)

        if not run_state.character and run_state.step_count > 2:
            # The first action should always be to look at attributes
            raw_screen_content = bytes(observation['tty_chars']).decode('ascii')
            run_state.update_base_attributes(raw_screen_content)

            #if environment.env.debug and run_state.target_roles and run_state.character.base_class not in run_state.target_roles:
            if run_state.target_roles and run_state.character.base_class not in run_state.target_roles:
                run_state.scumming = True

        changed_square = False
        previous_square = False
        if run_state.current_square is None or run_state.current_square.dcoord != dcoord or run_state.current_square.location != player_location:
            changed_square = True
            previous_square = run_state.current_square

            if run_state.character and run_state.character.held_by is not None:
                run_state.character.held_by = None

            new_square = CurrentSquare(
                arrival_time=time,
                dcoord=dcoord,
                location=player_location,
            )
            # If still on the same level, know what's under us
            if run_state.last_non_menu_action != nethack.actions.Command.TRAVEL and run_state.neighborhood and run_state.neighborhood.dcoord == dcoord:
                # we're intentionally using the pre-update run_state here to get a little memory of previous glyphs
                raw_previous_glyph_on_player = gd.GLYPH_NUMERAL_LOOKUP[run_state.glyphs[player_location]]
                if isinstance(raw_previous_glyph_on_player, gd.PetGlyph):
                    pass
                elif not (isinstance(raw_previous_glyph_on_player, gd.CMapGlyph) or gd.stackable_glyph(raw_previous_glyph_on_player) or isinstance(raw_previous_glyph_on_player, gd.WarningGlyph)):
                    # Re: warning glyphs, current situations where we walk onto them include piercers
                    # While hallu, we might step onto a statue we hallucinated as a monster
                    if raw_previous_glyph_on_player.name == 'leprechaun':
                        # Wild, I know, but a leprechaun can dodge us like this
                        # "miss wildly and stumble forward"
                        pass
                    elif environment.env.debug: import pdb; pdb.set_trace()
                else:
                    new_square.glyph_under_player = raw_previous_glyph_on_player
            run_state.current_square = new_square

        run_state.update_observation(observation) # moved after previous glyph futzing

        if run_state.step_count % 1000 == 0:
            print_stats(False, run_state, blstats)

        message = Message(observation['message'], observation['tty_chars'], observation['misc'])
        run_state.handle_message(message)

        if run_state.character:
            if run_state.last_non_menu_action == nethack.actions.Command.DROP or run_state.last_non_menu_action == nethack.actions.Command.DROPTYPE:
                run_state.character.clear_weight_knowledge()

        if message.dungeon_feature_here:
            level_map.add_feature(player_location, message.dungeon_feature_here)

        if run_state.character: # None until we C-X at the start of game
            run_state.character.update_from_observation(blstats)

        if isinstance(run_state.last_non_menu_advisor, advs.EatCorpseAdvisor):
            if changed_square and environment.env.debug:
                import pdb; pdb.set_trace()
            if message.feedback.nevermind or message.feedback.nothing_to_eat or "You finish eating the" in message.message:
                level_map.record_eat_succeeded_or_failed(player_location)
        elif isinstance(run_state.last_non_menu_advisor, advs.PickupDesirableItems):
            if changed_square and environment.env.debug:
                import pdb; pdb.set_trace()
            level_map.lootable_squares_map[player_location] = False

        if "Things that are here:" in message.message or "There are several objects here." in message.message:
            run_state.current_square.stack_on_square = True

        if "lands on the altar" in message.message:
            #import pdb; pdb.set_trace()
            run_state.current_square.stack_on_square = True
            level_map.lootable_squares_map[player_location] = True

        if isinstance(run_state.last_non_menu_advisor, advs.DropToPriceIDAdvisor):
            run_state.current_square.stack_on_square = True
            level_map.lootable_squares_map[player_location] = True

        killed_monster_name = monster_messages.RecordedMonsterDeath.involved_monster(message.message)
        if killed_monster_name:
            # TODO need to get better at knowing the square where the monster dies
            # currently bad at ranged attacks, confusion, and more
            if run_state.last_non_menu_action not in [nethack.actions.Command.FIRE, nethack.actions.Command.READ, nethack.actions.Command.TRAVEL]:
                if run_state.character.held_by is not None:
                    run_state.character.held_by = None

                delta = physics.action_to_delta[run_state.last_non_menu_action]

                try:
                    recorded_death = monster_messages.RecordedMonsterDeath(
                        (player_location[0] + delta[0], player_location[1] + delta[1]),
                        time,
                        killed_monster_name
                    )
                except Exception as e:
                    print("WARNING: {} for killed monster. Are we hallucinating?".format(str(e)))
                else:
                    level_map.lootable_squares_map[recorded_death.square] = True
                    if recorded_death.monster_glyph.safe_to_eat(run_state.character):
                        level_map.record_edible_corpse(recorded_death.square, time, recorded_death.monster_glyph)

        fleeing_monster_name = monster_messages.RecordedMonsterFlight.involved_monster(message.message)
        if fleeing_monster_name:
            try:
                recorded_flight = monster_messages.RecordedMonsterFlight(time, fleeing_monster_name)
                run_state.latest_monster_flight = recorded_flight
            except Exception as e:
                print("WARNING: {} for fleeing monster. Are we hallucinating?".format(str(e)))

        #create staircases. as of NLE 0.7.3, we receive the descend/ascend message while still in the old region
        if previous_square and previous_square.dcoord != dcoord:
            if len(run_state.message_log) > 1 and ("You descend the" in run_state.message_log[-2] or "You fall down the stairs" in run_state.message_log[-2] or "You climb" in run_state.message_log[-2]):
                print(run_state.message_log[-2])
                # create the staircases (idempotent)
                if "You descend the" in run_state.message_log[-2] or "You fall down the stairs" in run_state.message_log[-2]:
                    direction = (map.DirectionThroughDungeon.down, map.DirectionThroughDungeon.up)
                elif "You climb" in run_state.message_log[-2]:
                    direction = (map.DirectionThroughDungeon.up, map.DirectionThroughDungeon.down)

                if dcoord.branch != previous_square.dcoord.branch:
                    run_state.dmap.add_branch_traversal(start_dcoord=dcoord, end_dcoord=previous_square.dcoord)

                # staircase we just took
                previous_level_map = run_state.dmap.dlevels[previous_square.dcoord]
                previous_level_map.add_traversed_staircase(
                    previous_square.location, to_dcoord=dcoord, to_location=player_location, direction=direction[0])
                # staircase it's implied we've arrived on (probably breaks in the Valley)
                level_map.add_traversed_staircase(player_location, to_dcoord=previous_square.dcoord, to_location=previous_square.location, direction=direction[1])
                print("OLD DCOORD: {} NEW DCOORD: {}".format(previous_square.dcoord, dcoord))
            elif environment.env.debug:
                import pdb; pdb.set_trace()


        if "Something is written here in the dust" in message.message:
            if level_map.visits_count_map[player_location] == 1:
                level_map.add_warning_engraving(player_location)

        if run_state.character:
            run_state.character.update_from_message(message.message, time)

        if " tastes " in message.message or "finish eating" in message.message:
            print(message.message)

        if "You finish your dressing maneuver" in message.message or "You finish taking off" in message.message:
            print(message.message)

        if "It's a wall" in message.message and environment.env.debug:
            if environment.env.debug:
                pass
                #import pdb; pdb.set_trace() # we bumped into a wall but this shouldn't have been possible
                # examples of moments when this can happen: are blind and try to step into shop through broken wall that has been repaired by shopkeeper but we've been unable to see

        if "enough tries" in message.message and environment.env.debug:
            #import pdb; pdb.set_trace()
            pass

        if "You bite that, you pay for it!" in message.message:
            if environment.env.debug:
                import pdb; pdb.set_trace()

        if "You bought" in message.message:
            print(message.message)

        if "cannibal" in message.message:
            if environment.env.debug:
                import pdb; pdb.set_trace()

        if "Yak" in message.message:
            if environment.env.debug:
                import pdb; pdb.set_trace()

        if run_state.debugger_on:
            import pdb; pdb.set_trace()

        if "unknown comand" in message.message:
            raise Exception(f"Unknown command: {message.message}")

        if "while wearing a shield" in message.message:
            print(message.message)

        if " stole " in message.message:
            print(message.message)

        ###################################################
        # We are done observing and ready to start acting #
        ###################################################

        replay_advice = run_state.replay_advice()
        if replay_advice:
            return replay_advice

        menu_plan_retval = None
        if message:
            menu_plan_retval = run_state.run_menu_plan(message)
            ### GET MENU_PLAN RETVAL ###

        if menu_plan_retval is None and message.has_more and not run_state.active_menu_plan.in_interactive_menu:
            advice = MenuAdvice(
                keypress=nethack.actions.TextCharacters.SPACE,
                from_menu_plan=run_state.active_menu_plan, # TODO Not necessarily right vs background
            )
            return advice

        if menu_plan_retval is not None: # wait to return menu_plan retval, in case our click through more is supposed to override behavior in non-interactive menu plan
            advice = MenuAdvice(
                keypress=menu_plan_retval,
                from_menu_plan=run_state.active_menu_plan, # TODO Not necessarily right vs background
            )
            return advice

        if message.has_more:
            if environment.env.debug: pdb.set_trace() # should have been handled by our menu plan or by our blind mashing of space

        if run_state.auto_pickup:
            advice = ActionAdvice(
                from_advisor=None,
                action=nethack.actions.Command.AUTOPICKUP,
            )
            run_state.auto_pickup = False
            return advice

        if not run_state.character:
            advice = ActionAdvice(
                from_advisor=None,
                action=nethack.actions.Command.ATTRIBUTES,
            )
            return advice

        if run_state.scumming or (environment.env.max_score and run_state.reward > environment.env.max_score):
            scumming_menu_plan = menuplan.MenuPlan("scumming", None, [
                menuplan.YesMenuResponse("Really quit?"),
                menuplan.NoMenuResponse("Dump core?")
            ])
            advice = ActionAdvice(
                from_advisor=None,
                action=nethack.actions.Command.QUIT,
                new_menu_plan=scumming_menu_plan,
            )
            return advice

        if run_state.wizmode_prep:
            if not run_state.wizmode_prep.prepped:
                run_state.stall_detection_on = False
                action, menu_plan = run_state.wizmode_prep.next_action()
                advice = ActionAdvice(
                    from_advisor=None,
                    action=action,
                    new_menu_plan=menu_plan,
                )
                return advice
            else:
                run_state.stall_detection_on = True

        level_map.garbage_collect_corpses(time)

        neighborhood = Neighborhood(
            time,
            run_state.current_square,
            observation['glyphs'],
            level_map,
            run_state.character,
            run_state.latest_monster_flight,
        )
        if not (run_state.last_non_menu_action_failed_advancement or run_state.last_non_menu_action == nethack.actions.Command.SEARCH):
            run_state.check_gamestate_advancement(neighborhood)

        if run_state.last_non_menu_action == nethack.actions.Command.SEARCH:
            search_succeeded = False
            old_count = np.count_nonzero(run_state.neighborhood.extended_possible_secret_mask[run_state.neighborhood.neighborhood_view])
            new_count = np.count_nonzero(neighborhood.extended_possible_secret_mask[neighborhood.neighborhood_view])
            if new_count < old_count:
                search_succeeded = True
            run_state.search_log.append((np.ravel(run_state.neighborhood.raw_glyphs), search_succeeded))

        if not run_state.current_square.stack_on_square and not neighborhood.desirable_object_on_space(run_state.global_identity_map, run_state.character):
            #import pdb; pdb.set_trace()
            level_map.lootable_squares_map[player_location] = False

        ############################
        ### NEIGHBORHOOD UPDATED ###
        ############################
        run_state.update_neighborhood(neighborhood)

        run_state.log_adjacent_monsters(neighborhood.n_adjacent_monsters)
        ############################

        if blstats.get('depth') == 1:
            run_state.l1_advised_step_count += 1
            if level_map.need_egress():
                run_state.l1_need_downstairs_step_count += 1

        oracle = advs.Oracle(run_state, run_state.character, neighborhood, message, blstats)

        for advisor in advisor_sets.new_advisors:
            advice = advisor.advice_on_conditions(run_state.rng, run_state, run_state.character, oracle)
            if advice is not None:
                #print(advice)
                if advice.action == nethack.actions.Command.PRAY:
                    run_state.character.last_pray_time = time
                    run_state.character.last_pray_reason = advice.from_advisor # advice.from_advisor because we want to be more specific inside composite advisors
                elif advice.action == nethack.actions.Command.SEARCH:
                    level_map.log_search(player_location)

                if advice.action not in run_state.actions_without_consequence:
                    break

        if isinstance(advice.from_advisor, advs.FallbackSearchAdvisor):
            #if environment.env.debug: import pdb; pdb.set_trace()
            print("WARNING: Fell through advisors to fallback search")

        return advice

    def step(self, run_state, observation, reward, done, info):
        ARS.set_active(run_state)
        if observation['glyphs'].shape != constants.GLYPHS_SHAPE:
            raise Exception("Bad glyphs shape")

        if done and run_state.step_count != 0:
            raise Exception("The runner framework should have reset the run state")

        run_state.update_reward(reward)
        run_state.log_tty_cursor(observation['tty_cursor'])

        advice = self.generate_action(run_state, observation)

        if not isinstance(advice, Advice):
            raise Exception("Bad advice")

        if advice.new_menu_plan:
            run_state.set_menu_plan(advice.new_menu_plan)

        run_state.log_action(advice)

        if isinstance(advice, ActionAdvice):
            if advice.from_advisor:
                advice.from_advisor.advice_selected()
            return utilities.ACTION_LOOKUP[advice.action]
        elif isinstance(advice, ReplayAdvice):
            return utilities.ACTION_LOOKUP[advice.action]
        else:
            return utilities.ACTION_LOOKUP[advice.keypress]

    def batched_step(self, observations, rewards, dones, infos):
        """
        Perform a batched step on lists of environment outputs.

        Each argument is a list of the respective gym output.
        Returns an iterable of actions.
        """
        actions = [self.step(self.run_states[i], observations[i], rewards[i], dones[i], infos[i]) for i in range(self.num_envs)]
        return actions
