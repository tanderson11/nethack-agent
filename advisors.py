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

class Advice():
    def __init__(self, advisor, action, menu_plan):
        self.advisor = advisor
        self.action = action
        self.menu_plan = menu_plan

    def __repr__(self):
        return "Advice: (action={}; advisor={}; menu_plan={})".format(self.action, self.advisor, self.menu_plan)


class Flags():
    exp_lvl_to_prayer_hp_thresholds = {
        1: 1/5,
        6: 1/6,
        14: 1/7,
        22: 1/8,
        30: 1/9
    }

    def __init__(self, blstats, inventory, neighborhood, message, character):
        self.blstats = blstats
        self.inventory = inventory
        self.neighborhood = neighborhood
        self.message = message
        self.character = character

        self.computed_values = {}

    def am_weak(self):
        try:
            return self.computed_values['am_weak']
        except KeyError:
            am_weak = self.blstats.get('hunger_state') > 2
            self.computed_values['am_weak'] = am_weak
            return am_weak

    def am_satiated(self):
        try:
            return self.computed_values['am_satiated']
        except KeyError:
            am_satiated = self.blstats.get('hunger_state') > 2
            self.computed_values['am_satiated'] = am_satiated
            return am_satiated

    def am_critically_injured(self):
        try:
            return self.computed_values['am_critically_injured']
        except KeyError:
            fraction_index = [k for k in list(self.__class__.exp_lvl_to_prayer_hp_thresholds.keys()) if k <= self.blstats.get('experience_level')][-1]
            hp = self.blstats.get('hitpoints')
            am_critically_injured = hp < self.blstats.get('max_hitpoints') and (hp < self.__class__.exp_lvl_to_prayer_hp_thresholds[fraction_index] or hp < 6)
            self.computed_values['am_critically_injured'] = am_critically_injured
            return am_critically_injured

    def am_low_hp(self):
        try:
            return self.computed_values['am_low_hp']
        except KeyError:
            am_low_hp = self.am_critically_injured() or self.blstats.get('hitpoints') <= self.blstats.get('max_hitpoints') * 6/10
            self.computed_values['am_low_hp'] = am_low_hp
            return am_low_hp

    def on_downstairs(self):
        try:
            return self.computed_values['on_downstairs']
        except KeyError:
            previous_is_downstairs = isinstance(self.neighborhood.previous_glyph_on_player, gd.CMapGlyph) and self.neighborhood.previous_glyph_on_player.is_downstairs
            on_downstairs = "staircase down here" in self.message.message or previous_is_downstairs
            self.computed_values['on_downstairs'] = on_downstairs
            return on_downstairs

    def can_move(self):
        try:
            return self.computed_values['can_move']
        except KeyError:
            # someday Held, Handspan, Overburdened etc.
            can_move = not self.message.feedback.collapse_message
            self.computed_values['can_move'] = can_move
            return can_move

    def have_moves(self):
        try:
            return self.computed_values['have_moves']
        except KeyError:
            # someday Held, Handspan, Overburdened etc.
            have_moves = self.neighborhood.walkable.any() # at least one square is walkable
            self.computed_values['have_moves'] = have_moves
            return have_moves

    def have_unthreatened_moves(self):
        try:
            return self.computed_values['have_unthreatened_moves']
        except KeyError:
            # someday Held, Handspan, Overburdened etc.
            have_unthreatened_moves = (self.neighborhood.walkable & self.neighborhood.n_threat == 0).any() # at least one square is walkable
            self.computed_values['have_unthreatened_moves'] = have_unthreatened_moves
            return have_unthreatened_moves

    def desirable_object_on_space(self):
        try:
            return self.computed_values['desirable_object_on_space']
        except KeyError:
            prev_glyph = self.neighborhood.previous_glyph_on_player
            desirable_object_on_space = (isinstance(prev_glyph, gd.ObjectGlyph) or isinstance(prev_glyph, gd.CorpseGlyph)) and prev_glyph.desirable_object(self.character)

            self.computed_values['desirable_object_on_space'] = desirable_object_on_space
            return desirable_object_on_space

    def near_monster(self):
        try:
            return self.computed_values['near_monster']
        except KeyError:
            # someday Held, Handspan, Overburdened etc.
            near_monster = (self.neighborhood.is_monster() & ~self.neighborhood.players_square_mask).any()
            self.computed_values['near_monster'] = near_monster
            return near_monster

    def major_trouble(self):
        try:
            return self.computed_values['major_trouble']
        except KeyError:
            # someday Held, Handspan, Overburdened etc.
            major_trouble = "You feel feverish." in self.message.message
            self.computed_values['major_trouble'] = major_trouble
            return major_trouble

    def can_enhance(self):    
        try:
            return self.computed_values['can_enhance']
        except KeyError:
            # someday Held, Handspan, Overburdened etc.
            can_enhance = "You feel more confident" in self.message.message or "could be more dangerous" in self.message.message
            self.computed_values['can_enhance'] = can_enhance
            return can_enhance

    def fresh_corpse_on_square(self):    
        try:
            return self.computed_values['fresh_corpse_on_square']
        except KeyError:
            # someday Held, Handspan, Overburdened etc.
            fresh_corpse_on_square = (self.neighborhood.fresh_corpse_on_square_glyph is not None)
            self.computed_values['fresh_corpse_on_square'] = fresh_corpse_on_square
            return fresh_corpse_on_square

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
        return flags.major_trouble()

class UnthreatenedMovesAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.have_unthreatened_moves()

class FreeImprovementAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.can_enhance()

class AllMovesThreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return not flags.have_unthreatened_moves()

class CriticallyInjuredAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_critically_injured()

class CriticallyInjuredAndUnthreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_critically_injured() and flags.neighborhood.n_threat[flags.neighborhood.players_square_mask] == 0

class DungeonsOfDoomAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.blstats.get('dungeon_number') == 0

class NoMovesAdvisor(AdvisorLevel):
    def check_flags(self, flags):
        return not flags.have_moves()

class WeakWithHungerAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_weak()

class AdjacentToMonsterAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.near_monster()  

class LowHPAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_low_hp()

class AdjacentToMonsterAndLowHpAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.near_monster() and flags.am_low_hp()

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
        if flags.can_move() and flags.have_moves():
            agreeable_move_mask = self.find_agreeable_moves(rng, blstats, inventory, neighborhood, message, character)
            return self.get_move(rng, blstats, inventory, neighborhood, message, agreeable_move_mask)
        else:
            return None

class RandomMoveAdvisor(MoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable

    def get_move(self, rng, blstats, inventory, neighborhood, message, agreeable_move_mask):
        possible_actions = neighborhood.action_grid[agreeable_move_mask]

        #print(possible_actions)
        if possible_actions.any():
            return Advice(self.__class__, rng.choice(possible_actions), None)
        else:
            return None

class MostNovelMoveAdvisor(MoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
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
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened

class LeastNovelNonObjectGlyphMoveAdvisor(LeastNovelMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened & utilities.vectorized_map(lambda g: not isinstance(g, gd.ObjectGlyph), neighborhood.glyphs)

class MostNovelUnthreatenedMoveAdvisor(MostNovelMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened

class FreshCorpseMoveAdvisor(RandomMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & neighborhood.has_fresh_corpse

class DesirableObjectMoveAdvisor(RandomMoveAdvisor):
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & utilities.vectorized_map(lambda g: isinstance(g, gd.ObjectGlyph) and g.desirable_object(character), neighborhood.glyphs)

class RandomLeastThreatenedMoveAdvisor(RandomMoveAdvisor): 
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & (neighborhood.n_threat == neighborhood.n_threat.min())

class RandomUnthreatenedMoveAdvisor(RandomMoveAdvisor): 
    def find_agreeable_moves(self, rng, blstats, inventory, neighborhood, message, character):
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
        if flags.can_move() and flags.on_downstairs():
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

class PickupFoodAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if flags.desirable_object_on_space():
            menu_plan = menuplan.MenuPlan("pick up comestibles and safe corpses", self, {}, interactive_menu_header_rows=2, menu_item_selector=lambda x: x.category == "Comestibles")
            print("Food pickup")
            return Advice(self.__class__, nethack.actions.Command.PICKUP, menu_plan)
        return None

class PickupArmorAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if flags.desirable_object_on_space():
            menu_plan = menuplan.MenuPlan("pick up armor", self, {}, interactive_menu_header_rows=2, menu_item_selector=lambda x: x.category == "Armor")
            print("Armor pickup")
            return Advice(self.__class__, nethack.actions.Command.PICKUP, menu_plan)
        return None

class EatCorpseAdvisor(Advisor):
    def advice(self, rng, character, blstats, inventory, neighborhood, message, flags):
        if not flags.fresh_corpse_on_square():
            return None

        if flags.am_satiated():
            return None

        if not neighborhood.fresh_corpse_on_square_glyph.safe_to_eat(character):
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
