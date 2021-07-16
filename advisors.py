import abc
from collections import OrderedDict
import pdb

import glyphs as gd
import nle.nethack as nethack
import numpy as np

import environment
import menuplan
import utilities
from utilities import ARS

# Advisors
# act on the cleaned up state (message obj, neighborhood obj, blstats)
# -> check if condition is satisfied (eg on the downstairs, near locked door)
# -> return a candidate action

# Control
# query all advisors and get a list of advice tagged to advisors
# choose among advisors (can make a ranked list of advisors by priority and deterministically or weighted-randomly choose between them;
# can eventually plug the weighting into NN)

class Advice():
    def __init__(self, advisor, action, menu_plan):
        self.advisor = advisor
        self.action = action
        self.menu_plan = menu_plan

    def __repr__(self):
        return "Advice: (action={}; advisor={}; menu_plan={})".format(self.action, self.advisor, self.menu_plan)

class Flags():
    def __init__(self, blstats, inventory, neighborhood, message):
        self.blstats = blstats
        self.inventory = inventory
        self.neighborhood = neighborhood
        self.message = message

        self.am_weak = blstats.get('hunger_state') > 2
        self.am_satiated = blstats.get('hunger_state') == 0

        exp_lvl_to_prayer_hp_thresholds = {
            1: 1/5,
            6: 1/6,
            14: 1/7,
            22: 1/8,
            30: 1/9
        }
        fraction_index = [k for k in list(exp_lvl_to_prayer_hp_thresholds.keys()) if k <= blstats.get('experience_level')][-1]
        self.am_critically_injured = blstats.get('hitpoints') < blstats.get('max_hitpoints') and (blstats.get('hitpoints') < exp_lvl_to_prayer_hp_thresholds[fraction_index] or blstats.get('hitpoints') < 6)
        self.low_hp = self.am_critically_injured or blstats.get('hitpoints') <= blstats.get('max_hitpoints') * 6/10
        # downstairs
        previous_glyph = neighborhood.previous_glyph_on_player
        if previous_glyph is not None: # on the first frame there was no previous glyph
            previous_is_downstairs = getattr(previous_glyph, 'is_downstairs', False)
        else:
            previous_is_downstairs = False

        self.on_downstairs = "staircase down here" in message.message or previous_is_downstairs

        self.have_walkable_squares = neighborhood.action_grid[neighborhood.walkable].any() # at least one square is walkable
        self.have_unthreatened_walkable_squares = neighborhood.action_grid[neighborhood.walkable & ~neighborhood.threatened].any()

        #self.can_move = True # someday Held, Handspan etc.
        self.can_move = not message.feedback.collapse_message

        if previous_glyph is not None and "for sale" not in message.message: # hopefully this will help us not pick up food in shops
            self.desirable_object_on_space = (isinstance(previous_glyph, gd.ObjectGlyph) or isinstance(previous_glyph, gd.CorpseGlyph)) and previous_glyph.desirable_object()
        else:
            self.desirable_object_on_space = False

        is_monster = neighborhood.is_monster()

        self.near_monster = (is_monster & ~neighborhood.players_square_mask).any()
        self.feverish = "You feel feverish." in message.message

        self.can_enhance = "You feel more confident" in message.message or "could be more dangerous" in message.message
        if self.can_enhance:
            print(message.message)

        self.fresh_corpse_on_square = (neighborhood.fresh_corpse_on_square_glyph is not None)

class AdvisorLevel():
    def __init__(self, advisors):
        self.advisors = advisors

    def check_flags(self, flags):
        return True

class ThreatenedMoreThanOnceAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.neighborhood.n_threat[flags.neighborhood.players_square_mask] > 1

class AmUnthreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.neighborhood.n_threat[flags.neighborhood.players_square_mask] == 0

class MajorTroubleAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.feverish

class UnthreatenedMovesAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.have_unthreatened_walkable_squares

class FreeImprovementAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.can_enhance

class AllMovesThreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return not flags.have_unthreatened_walkable_squares

class CriticallyInjuredAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_critically_injured

class CriticallyInjuredAndUnthreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_critically_injured and flags.neighborhood.n_threat[flags.neighborhood.players_square_mask] == 0

class DungeonsOfDoomAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.blstats.get('dungeon_number') == 0

#class NoMovesAdvisor(AdvisorLevel):
#    def check_flags(self, flags):
#        return True

class WeakWithHungerAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_weak

class AdjacentToMonsterAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.near_monster   

class LowHPAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.low_hp   

class AdjacentToMonsterAndLowHpAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.near_monster and flags.low_hp

class Advisor(abc.ABC):
    def __init__(self):
        pass

    @abc.abstractmethod
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags): # returns action, MenuPlan
        pass

class BackgroundActionsAdvisor(Advisor): # dummy advisor to hold background menu plans
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        pass

class MoveAdvisor(Advisor): # this should be some kind of ABC as well, just don't know quite how to chain them # should be ABC over find_agreeable_moves
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if flags.can_move and flags.have_walkable_squares:
            agreeable_move_mask = self.find_agreeable_moves(rng, blstats, inventory, neighborhood, message)
            return self.get_move(rng, blstats, inventory, neighborhood, message, agreeable_move_mask)
        else:
            return None

class RandomMoveAdvisor(MoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable

    def get_move(self, rng, blstats, inventory, neighborhood, message, agreeable_move_mask):
        possible_actions = neighborhood.action_grid[agreeable_move_mask]

        #print(possible_actions)
        if possible_actions.any():
            return Advice(self.__class__, rng.choice(possible_actions), None)
        else:
            return None

class MostNovelMoveAdvisor(MoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable

    def get_move(self, rng, blstats, inventory, neighborhood, message, agreeable_move_mask):
        possible_actions = neighborhood.action_grid[agreeable_move_mask]
        visits = neighborhood.visits[agreeable_move_mask]

        if visits.any():
            most_novel = possible_actions[visits == visits.min()]
            return Advice(self.__class__, rng.choice(most_novel), None)
        else:
            return None

class LeastNovelMoveAdvisor(MoveAdvisor):
    def get_move(self, rng, blstats, inventory, neighborhood, message, agreeable_move_mask):
        possible_actions = neighborhood.action_grid[agreeable_move_mask]
        visits = neighborhood.visits[agreeable_move_mask]

        if visits.any():
            least_novel = possible_actions[visits == visits.max()]
            return Advice(self.__class__, rng.choice(least_novel), None)
        else:
            return None

class LeastNovelUnthreatenedMoveAdvisor(LeastNovelMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable & ~neighborhood.threatened

class LeastNovelNonObjectGlyphMoveAdvisor(LeastNovelMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable & ~neighborhood.threatened & utilities.vectorized_map(lambda g: not isinstance(g, gd.ObjectGlyph), neighborhood.glyphs)

class MostNovelUnthreatenedMoveAdvisor(MostNovelMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable & ~neighborhood.threatened

class FreshCorpseMoveAdvisor(RandomMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable & neighborhood.has_fresh_corpse

class DesirableObjectMoveAdvisor(RandomMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable & utilities.vectorized_map(lambda g: getattr(g, 'desirable_object', lambda: False)(), neighborhood.glyphs)

class RandomLeastThreatenedMoveAdvisor(RandomMoveAdvisor): 
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable & (neighborhood.n_threat == neighborhood.n_threat.min())

class RandomUnthreatenedMoveAdvisor(RandomMoveAdvisor): 
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message):
        return neighborhood.walkable & ~neighborhood.threatened

class PrayerAdvisor(Advisor):
    def advice(self, rng, character, _1, _2, _3, _4, _5):
        pray = nethack.actions.Command.PRAY
        menu_plan = menuplan.MenuPlan("yes pray", self, {
            "Are you sure you want to pray?": utilities.keypress_action(ord('y')),
        })
        return Advice(self.__class__, pray, menu_plan)

class DownstairsAdvisor(Advisor):
    exp_lvl_to_max_mazes_lvl = {
        1: 1,
        2: 1,
        3: 2,
        4: 2,
        5: 3,
        6: 5,
        7: 6,
        8: 8,
        9: 10,
        10: 12,
        11: 16,
        12: 20,
        13: 20,
        14: 60,
    }

    # getting slightly less aggressive now that we eat corpses
    exp_lvl_to_max_mazes_lvl_no_food = {
        1:1,
        2:2,
        3:3,
        4:4,
        5:5,
        6:6,
        7:6,
        8:8,
        9:10,
        10:12,
        11:16,
        12:20,
        13:20,
        14:60,
    }

    @classmethod
    def check_willingness_to_descend(cls, blstats, inventory):
        willing_to_descend = blstats.get('hitpoints') == blstats.get('max_hitpoints')
        if utilities.have_item_oclasses(['FOOD_CLASS'], inventory):
            willing_to_descend = willing_to_descend and cls.exp_lvl_to_max_mazes_lvl.get(blstats.get('experience_level'), 60) > blstats.get('depth')
        else:
            willing_to_descend = willing_to_descend and cls.exp_lvl_to_max_mazes_lvl_no_food.get(blstats.get('experience_level'), 60) > blstats.get('depth')
        
        #willing_to_descend = willing_to_descend and cls.exp_lvl_to_max_mazes_lvl.get(blstats.get('experience_level'), 60) > blstats.get('depth')
        return willing_to_descend

    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        pass

class TakeDownstairsAdvisor(DownstairsAdvisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if flags.can_move and flags.on_downstairs:
            willing_to_descend = self.__class__.check_willingness_to_descend(blstats, inventory)
            if willing_to_descend:
                return Advice(self.__class__, nethack.actions.MiscDirection.DOWN, None)
            return None
        return None

class KickLockedDoorAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flag):
        if "This door is locked" in message.message:
            kick = nethack.actions.Command.KICK
            door_directions = neighborhood.action_grid[utilities.vectorized_map(lambda g: getattr(g, 'is_closed_door', False), neighborhood.glyphs)]
            if len(door_directions) > 0:
                a = rng.choice(door_directions)
            else: # we got the locked door message but didn't find a door
                a = None
                if environment.env.debug: pdb.set_trace()
                pass
            menu_plan = menuplan.MenuPlan("kick locked door", self, {
                "In what direction?": utilities.ACTION_LOOKUP[a],
            })
            return Advice(self.__class__, kick, menu_plan)
        return None

class ItemUseAdvisor(Advisor): # should be abc over self.use_item and self.__class__.oclassess_used
    oclasses_used = None

    def have_item_oclass(self, inventory):
        return utilities.have_item_oclasses(self.__class__.oclasses_used, inventory)

    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if self.have_item_oclass(inventory):
            return self.use_item(rng, blstats, inventory, neighborhood, message, flags)
        return None

class EatTopInventoryAdvisor(ItemUseAdvisor):
    oclasses_used = ['FOOD_CLASS']

    def make_menu_plan(self, letter):
        menu_plan = menuplan.MenuPlan("eat from inventory", self, {
        "here; eat": utilities.keypress_action(ord('n')),
        "want to eat?": utilities.keypress_action(letter),
        "You succeed in opening the tin.": utilities.keypress_action(ord(' ')),
        "smells like": utilities.keypress_action(ord('y')),
        "Rotten food!": utilities.keypress_action(ord(' ')),
        "Eat it?": utilities.keypress_action(ord('y')),
        })
        return menu_plan

    def use_item(self, rng, _1, inventory, _3, _4, flags):
        eat = nethack.actions.Command.EAT
        FOOD_CLASS = gd.ObjectGlyph.OBJECT_CLASSES.index('FOOD_CLASS')
        food_index = inventory['inv_oclasses'].tolist().index(FOOD_CLASS)

        letter = inventory['inv_letters'][food_index]
        menu_plan = self.make_menu_plan(letter)
        return Advice(self.__class__, eat, menu_plan)

class ReadTeleportAdvisor(ItemUseAdvisor):
    oclasses_used = ['SCROLL_CLASS']

    def use_item(self, rng, _1, inventory, _3, _4, flags):
        read = nethack.actions.Command.READ
        menu_plan = menuplan.MenuPlan("read teleportation scroll", self, {
            "What do you want to read?": utilities.keypress_action(ord('*'))
            }, interactive_menu_header_rows=0,
            menu_item_selector=lambda x: (x.category == "Scrolls") & ("teleporation" in x.item_appearance),
            expects_strange_messages=True
        )
        
        return Advice(self.__class__, read, menu_plan)

class ZapTeleportOnSelfAdvisor(ItemUseAdvisor):
    oclasses_used = ['WAND_CLASS']

    def use_item(self, rng, _1, inventory, _3, _4, flags):
        zap = nethack.actions.Command.ZAP

        menu_plan = menuplan.MenuPlan("zap teleportation wand", self, {"What do you want to zap?": utilities.keypress_action(ord('*'))}, interactive_menu_header_rows=0, menu_item_selector=lambda x: (x.category == "Wands") & ("teleporation" in x.item_appearance), expects_strange_messages=True)
        return Advice(self.__class__, zap, menu_plan)

class DrinkHealingPotionAdvisor(ItemUseAdvisor):
    oclasses_used = ['POTION_CLASS']
    def use_item(self, rng, _1, inventory, _3, _4, flags):
        quaff = nethack.actions.Command.QUAFF
        menu_plan = menuplan.MenuPlan("drink healing potion", self, {
            "What do you want to drink?": utilities.keypress_action(ord('*')),
            "Drink from the fountain?": nethack.ACTIONS.index(nethack.actions.Command.ESC)
            }, interactive_menu_header_rows=0,
            menu_item_selector=lambda x: (x.category == "Potions") & ("healing" in x.item_appearance),
            expects_strange_messages=True)
        #pdb.set_trace()
        return Advice(self.__class__, quaff, menu_plan)

class FallbackSearchAdvisor(Advisor):
    def advice(self, rng, character, _1, _2, _3, _4, _5):
        return Advice(self.__class__, nethack.actions.Command.SEARCH, None)

class NoUnexploredSearchAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if not (neighborhood.visits[neighborhood.walkable] == 0).any() and (utilities.vectorized_map(lambda g: getattr(g, 'possible_secret_door', False), neighborhood.glyphs)).any():
            return Advice(self.__class__, nethack.actions.Command.SEARCH, None)
        return None

class RandomAttackAdvisor(Advisor):
    def get_target_monsters(self, neighborhood):
        always_peaceful = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.always_peaceful, neighborhood.glyphs)
        targeted_monster_mask = neighborhood.is_monster() & ~neighborhood.players_square_mask & ~always_peaceful
        return targeted_monster_mask

    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        targeted_monster_mask = self.get_target_monsters(neighborhood)
        monster_directions = neighborhood.action_grid[targeted_monster_mask]
        if monster_directions.any():
            attack_direction = rng.choice(monster_directions)
            return Advice(self.__class__, attack_direction, None)
        return None

class RandomSafeMeleeAttack(RandomAttackAdvisor):
    def get_target_monsters(self, neighborhood):
        always_peaceful = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.always_peaceful, neighborhood.glyphs)
        has_passive_mask = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.has_passive, neighborhood.glyphs)
        targeted_monster_mask = neighborhood.is_monster() & ~neighborhood.players_square_mask & ~has_passive_mask & ~always_peaceful
        return targeted_monster_mask

class RandomRangedAttackAdvisor(RandomAttackAdvisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        targeted_monster_mask = self.get_target_monsters(neighborhood)

        monster_directions = neighborhood.action_grid[targeted_monster_mask]

        if monster_directions.any():
            fire = nethack.actions.Command.FIRE
            attack_direction = rng.choice(monster_directions)

            WEAPON_CLASS = gd.ObjectGlyph.OBJECT_CLASSES.index('WEAPON_CLASS')
            is_weapon = [c == WEAPON_CLASS for c in inventory['inv_oclasses'].tolist()]
            extra_weapon = sum(is_weapon) > 1

            if extra_weapon:
                menu_plan = menuplan.MenuPlan("ranged attack", self, {
                    "In what direction?": nethack.ACTIONS.index(attack_direction),
                    "What do you want to throw?": utilities.keypress_action(ord('*')), # note throw: means we didn't have anything quivered
                    }, interactive_menu_header_rows=0,
                    expects_strange_messages=True,
                    menu_item_selector=lambda x: (x.category == "Weapons") & ("weapon in hand" not in x.item_equipped_status)
                    )
                return Advice(self.__class__, fire, menu_plan)

            return None
        return None

class PickupAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if flags.desirable_object_on_space:
            menu_plan = menuplan.MenuPlan("pick up comestibles and safe corpses", self, {}, interactive_menu_header_rows=2, menu_item_selector=lambda x: x.category == "Comestibles")
            print("Pickup")
            return Advice(self.__class__, nethack.actions.Command.PICKUP, menu_plan)
        return None

class EatCorpseAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if not flags.fresh_corpse_on_square:
            return None

        if flags.am_satiated:
            return None
        corpse_spoiler = neighborhood.fresh_corpse_on_square_glyph.corpse_spoiler
        if not corpse_spoiler:
            return None
        if corpse_spoiler.slime or corpse_spoiler.petrify or corpse_spoiler.instadeath:
            return None

        # For these remaining checks, maybe skip them if I'm hungry enough
        if character.can_cannibalize() and (corpse_spoiler.race_for_cannibalism == character.base_race):
            return None
        if character.can_cannibalize() and corpse_spoiler.aggravate:
            return None
        if any([
            corpse_spoiler.acidic,
            corpse_spoiler.poisonous,
            corpse_spoiler.stun,
            corpse_spoiler.polymorph,
            corpse_spoiler.hallucination,
            corpse_spoiler.lycanthropy,
            corpse_spoiler.teleportitis,
            corpse_spoiler.invisibility,
            corpse_spoiler.speed_toggle
        ]):
            return None
        menu_plan = menuplan.MenuPlan(
            "eat corpse on square", self,
            OrderedDict([
                (f"{neighborhood.fresh_corpse_on_square_glyph.name} corpse here; eat", utilities.keypress_action(ord('y'))),
                ("here; eat", utilities.keypress_action(ord('n'))),
                ("want to eat?", utilities.ACTION_LOOKUP[nethack.actions.Command.ESC]),
            ]))
        return Advice(self.__class__, nethack.actions.Command.EAT, menu_plan)

class TravelToDownstairsAdvisor(DownstairsAdvisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        willing_to_descend = self.__class__.check_willingness_to_descend(blstats, inventory)
        
        if willing_to_descend:
            travel = nethack.actions.Command.TRAVEL

            menu_plan = menuplan.MenuPlan("travel down", self, {
                "Where do you want to travel to?": utilities.keypress_action(ord('>')),
                "Can't find dungeon feature": nethack.ACTIONS.index(nethack.actions.Command.ESC)
                },
                expects_strange_messages=True,
                fallback=utilities.keypress_action(ord('.')))
     
            return Advice(self.__class__, travel, menu_plan)
        return None

class EnhanceSkillsAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        enhance = nethack.actions.Command.ENHANCE
        menu_plan = menuplan.MenuPlan("enhance skills", self, {}, interactive_menu_header_rows=2, menu_item_selector=lambda x: True, expects_strange_messages=True)

        return Advice(self.__class__, enhance, menu_plan)

# Thinking outloud ...
# Free/scheduled (eg enhance), Repair major, escape, attack, repair minor, improve/identify, descend, explore
