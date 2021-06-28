import glyphs as gd
import nle.nethack as nethack
import menuplan
import utilities
import abc
import environment
import pdb
import numpy as np

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

class Flags():
    def __init__(self, blstats, inventory, neighborhood, message):
        self.blstats = blstats
        self.inventory = inventory
        self.neighborhood = neighborhood
        self.message = message

        self.am_weak = blstats.get('hunger_state') > 2

        exp_lvl_to_prayer_hp_thresholds = {
            1: 1/5,
            6: 1/6,
            14: 1/7,
            22: 1/8,
            30: 1/9
        }
        fraction_index = [k for k in list(exp_lvl_to_prayer_hp_thresholds.keys()) if k <= blstats.get('experience_level')][-1]
        self.am_critically_injured = blstats.get('hitpoints') < blstats.get('max_hitpoints') and (blstats.get('hitpoints') < exp_lvl_to_prayer_hp_thresholds[fraction_index] or blstats.get('hitpoints') < 6)

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

        exp_lvl_to_max_mazes_lvl_no_food = {
            1:1,
            2:2,
            3:3,
            4:4,
            5:5,
            6:6,
            7:9,
            8:9,
            9:10,
            10: 12,
            11: 16,
            12: 20,
            13: 20,
            14: 60,
        }

        self.willing_to_descend = blstats.get('hitpoints') == blstats.get('max_hitpoints')
        if have_item_oclass(inventory, "FOOD_CLASS"):
            self.willing_to_descend = self.willing_to_descend and exp_lvl_to_max_mazes_lvl.get(blstats.get('experience_level'), 60) > blstats.get('level_number')
        else:
            self.willing_to_descend = self.willing_to_descend and exp_lvl_to_max_mazes_lvl_no_food.get(blstats.get('experience_level'), 60) > blstats.get('level_number')

        # downstairs
        previous_glyph = neighborhood.previous_glyph_on_player
        if previous_glyph is not None: # on the first frame there was no previous glyph
            previous_is_downstairs = getattr(previous_glyph, 'is_downstairs', False)
        else:
            previous_is_downstairs = False

        self.on_downstairs = "staircase down here" in message.message or previous_is_downstairs

        self.bumped_into_locked_door = "This door is locked" in message.message
        self.have_walkable_squares = neighborhood.action_grid[neighborhood.walkable].any() # at least one square is walkable
        self.can_move = True # someday Held, Handspan etc.

        self.adjacent_univisited_square = (neighborhood.visits[neighborhood.walkable] == 0).any()

        if previous_glyph is not None and "for sale" not in message.message: # hopefully this will help us not pick up food in shops
            self.desirable_object = isinstance(previous_glyph, gd.ObjectGlyph) and previous_glyph.object_class_name == "FOOD_CLASS"
        else:
            self.desirable_object = False

        is_monster = neighborhood.is_monster()

        self.adjacent_secret_door_possibility = (np.vectorize(lambda g: getattr(g, 'possible_secret_door', False))(neighborhood.glyphs))
        self.near_monster = (is_monster & ~neighborhood.players_square_mask).any()
        self.feverish = "You feel feverish." in message.message

        self.can_enhance = "You feel more confident" in message.message or "could be more dangerous" in message.message
        if self.can_enhance:
            print(message.message)

class Advisor(abc.ABC):
    def __init__(self):
        pass

    @abc.abstractmethod
    def check_conditions(self, flags): # returns T/F
        pass

    @abc.abstractmethod
    def advice(self, rng, blstats, inventory, neighborhood, message): # returns action, MenuPlan
        pass

    def give_advice(self, rng, flags, blstats, inventory, neighborhood, message):
        if self.check_conditions(flags):
            return self.advice(rng, blstats, inventory, neighborhood, message)

class MoveAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.have_walkable_squares

class RandomMoveAdvisor(MoveAdvisor): 
    def advice(self, rng, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[neighborhood.walkable]
        if possible_actions.any():
            return Advice(self.__class__, rng.choice(possible_actions), None)

class MostNovelMoveAdvisor(MoveAdvisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.have_walkable_squares
    def advice(self, rng, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[neighborhood.walkable]
        visits = neighborhood.visits[neighborhood.walkable]
        most_novel = possible_actions[visits == visits.min()]
        return Advice(self.__class__, rng.choice(most_novel), None)

class VisitUnvisitedSquareAdvisor(MoveAdvisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.adjacent_univisited_square

    def advice(self, rng, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[(neighborhood.visits == 0) & neighborhood.walkable]
        return Advice(self.__class__, rng.choice(possible_actions), None)


class MoveDownstairsAdvisor(MoveAdvisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.on_downstairs and flags.willing_to_descend

    def advice(self, _0, _1, _2, _3, _4):
        return Advice(self.__class__, nethack.actions.MiscDirection.DOWN, None)

class KickLockedDoorAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.bumped_into_locked_door

    def advice(self, rng, _, __, neighborhood, ___):
        kick = nethack.actions.Command.KICK
        door_directions = neighborhood.action_grid[np.vectorize(lambda g: getattr(g, 'is_closed_door', False))(neighborhood.glyphs)]
        if len(door_directions) > 0:
            a = rng.choice(door_directions)
        else: # we got the locked door message but didn't find a door
            a = None
            if environment.env.debug: pdb.set_trace()
            pass
        menu_plan = menuplan.MenuPlan("kick locked door", {
            "In what direction?": utilities.ACTION_LOOKUP[a],
        })
        #if environment.env.debug: pdb.set_trace()
        return Advice(self.__class__, kick, menu_plan)

class EatTopInventoryAdvisor(Advisor):
    def make_menu_plan(self, letter):
        menu_plan = menuplan.MenuPlan("eat from inventory", {
        "here; eat": utilities.keypress_action(ord('n')),
        "want to eat?": utilities.keypress_action(letter),
        "You succeed in opening the tin.": utilities.keypress_action(ord(' ')),
        "smells like": utilities.keypress_action(ord('y')),
        "Rotten food!": utilities.keypress_action(ord(' ')),
        "Eat it?": utilities.keypress_action(ord('y')),
        })
        return menu_plan

    def advice(self, _0, _1, inventory, _3, _4):
        eat = nethack.actions.Command.EAT
        try:
            FOOD_CLASS = gd.ObjectGlyph.OBJECT_CLASSES.index('FOOD_CLASS')
            food_index = inventory['inv_oclasses'].tolist().index(FOOD_CLASS)
        except ValueError:
            food_index = None
        if food_index is not None:
            letter = inventory['inv_letters'][food_index]
            menu_plan = self.make_menu_plan(letter)
            return Advice(self.__class__, eat, menu_plan)

class EatWhenWeakAdvisor(EatTopInventoryAdvisor):
    def check_conditions(self, flags):
        return flags.am_weak and not flags.near_monster

class PrayerAdvisor(Advisor):
    def advice(self, _0, _1, _2, _3, _4):
        pray = nethack.actions.Command.PRAY
        menu_plan = menuplan.MenuPlan("yes pray", {
            "Are you sure you want to pray?": utilities.keypress_action(ord('y')),
        })
        return Advice(self.__class__, pray, menu_plan)

class PrayWhenMajorTroubleAdvisor(PrayerAdvisor):
    def check_conditions(self, flags):
        return flags.feverish

class PrayWhenWeakAdvisor(PrayerAdvisor):
    def check_conditions(self, flags):
        return flags.am_weak

class PrayWhenCriticallyInjuredAdvisor(PrayerAdvisor):
    def check_conditions(self, flags):
        return flags.am_critically_injured

class CriticallyInjuredAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.am_critically_injured

def have_item_oclass(inventory, oclass):
    return gd.ObjectGlyph.OBJECT_CLASSES.index(oclass) in inventory['inv_oclasses']

class ReadTeleportWhenCriticallyInjuredAdvisor(CriticallyInjuredAdvisor):
    def advice(self, _0, _1, inventory, _3, _4):
        read = nethack.actions.Command.READ
        have_scroll = have_item_oclass(inventory, 'SCROLL_CLASS')
        if have_scroll:
            menu_plan = menuplan.MenuPlan("read teleportation scroll", {"What do you want to read?": utilities.keypress_action(ord('*'))}, interactive_menu_header_rows=0, menu_item_selector=lambda x: (x.category == "Scrolls") & ("teleporation" in x.item_appearance), expects_strange_messages=True)
            return Advice(self.__class__, read, menu_plan)
        return None

class ZapTeleportWhenCriticallyInjuredAdvisor(CriticallyInjuredAdvisor):
    def advice(self, _0, _1, inventory, _3, _4):
        zap = nethack.actions.Command.ZAP
        have_wand = have_item_oclass(inventory, 'WAND_CLASS')
        if have_wand:
            menu_plan = menuplan.MenuPlan("zap teleportation wand", {"What do you want to zap?": utilities.keypress_action(ord('*'))}, interactive_menu_header_rows=0, menu_item_selector=lambda x: (x.category == "Wands") & ("teleporation" in x.item_appearance), expects_strange_messages=True)
            return Advice(self.__class__, zap, menu_plan)
        return None

class DrinkHealingPotionWhenCriticallyInjuredAdvisor(CriticallyInjuredAdvisor):
    def advice(self, _0, _1, inventory, _3, _4):
        have_potion = have_item_oclass(inventory, 'POTION_CLASS')
        quaff = nethack.actions.Command.QUAFF
        if have_potion:
            menu_plan = menuplan.MenuPlan("drink healing potion", {
                "What do you want to drink?": utilities.keypress_action(ord('*')),
                "Drink from the fountain?": nethack.ACTIONS.index(nethack.actions.Command.ESC)
                }, interactive_menu_header_rows=0,
                menu_item_selector=lambda x: (x.category == "Potions") & ("healing" in x.item_appearance),
                expects_strange_messages=True)
            return Advice(self.__class__, quaff, menu_plan)
        return None

class SearchAdvisor(Advisor):
    def advice(self, _0, _1, _2, _3, _4):
        return Advice(self.__class__, nethack.actions.Command.SEARCH, None)

class FallbackSearchAdvisor(SearchAdvisor):
    def check_conditions(self, flags):
        return True # this action is always possible and a good waiting action

class NoUnexploredSearchAdvisor(SearchAdvisor):
    def check_conditions(self, flags):
        return (not flags.adjacent_univisited_square) and flags.adjacent_secret_door_possibility.any()

class AttackAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.near_monster

class MeleeAttackAdvisor(AttackAdvisor):
    def advice(self, rng, blstats, inventory, neighborhood, message):
        is_monster = neighborhood.is_monster()

        never_melee_mask = np.vectorize(lambda g: isinstance(g, gd.MonsterGlyph) and g.never_melee)(neighborhood.glyphs)
        
        monster_directions = neighborhood.action_grid[is_monster & ~neighborhood.players_square_mask & ~never_melee_mask]

        if monster_directions.any():
            return Advice(self.__class__, rng.choice(monster_directions), None)

        return None

class MeleeEvenNastyAdvisor(AttackAdvisor):
    def advice(self, rng, blstats, inventory, neighborhood, message):
        is_monster = neighborhood.is_monster()
        
        monster_directions = neighborhood.action_grid[is_monster & ~neighborhood.players_square_mask]

        if monster_directions.any():
            return Advice(self.__class__, rng.choice(monster_directions), None)

        return None

class RangedAttackAdvisor(AttackAdvisor):
    def advice(self, rng, blstats, inventory, neighborhood, message):
        is_monster = neighborhood.is_monster()
        monster_directions = neighborhood.action_grid[is_monster & ~neighborhood.players_square_mask]

        if monster_directions.any():
            fire = nethack.actions.Command.FIRE
            attack_direction = rng.choice(monster_directions)

            WEAPON_CLASS = gd.ObjectGlyph.OBJECT_CLASSES.index('WEAPON_CLASS')
            is_weapon = [c == WEAPON_CLASS for c in inventory['inv_oclasses'].tolist()]
            extra_weapon = sum(is_weapon) > 1

            if extra_weapon:
                menu_plan = menuplan.MenuPlan("ranged attack", {
                    "In what direction?": nethack.ACTIONS.index(attack_direction),
                    "What do you want to throw?": utilities.keypress_action(ord('*')), # note throw: means we didn't have anything quivered
                    }, interactive_menu_header_rows=0,
                    expects_strange_messages=True,
                    menu_item_selector=lambda x: (x.category == "Weapons") & ("weapon in hand" not in x.item_equipped_status)
                    )
                return Advice(self.__class__, fire, menu_plan)

            return None

class PickupAdvisor(Advisor):
    def check_conditions(self, flags):
        return (not flags.near_monster) and flags.desirable_object

    def advice(self, rng, blstats, inventory, neighborhood, message):
        menu_plan = menuplan.MenuPlan("pick up comestibles", {}, interactive_menu_header_rows=2, menu_item_selector=lambda x: x.category == "Comestibles")
        print("Pickup")
        return Advice(self.__class__, nethack.actions.Command.PICKUP, menu_plan)

class TravelToDownstairsAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.willing_to_descend

    def advice(self, rng, blstats, inventory, neighborhood, message):
        travel = nethack.actions.Command.TRAVEL

        menu_plan = menuplan.MenuPlan("travel down", {
            "Where do you want to travel to?": utilities.keypress_action(ord('>')),
            "Can't find dungeon feature": nethack.ACTIONS.index(nethack.actions.Command.ESC)
            },
            expects_strange_messages=True,
            fallback=utilities.keypress_action(ord('.')))
 
        return Advice(self.__class__, travel, menu_plan)

class EnhanceSkillsAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.can_enhance

    def advice(self, rng, blstats, inventory, neighborhood, message):
        enhance = nethack.actions.Command.ENHANCE
        menu_plan = menuplan.MenuPlan("enhance skills", {}, interactive_menu_header_rows=2, menu_item_selector=lambda x: True, expects_strange_messages=True)

        return Advice(self.__class__, enhance, menu_plan)

class SearchWhenLowHpAdvisor(Advisor):
    def check_conditions(self,flags):
        return True # abuse

    def advice(self, rng, blstats, inventory, neighborhood, message):
        if blstats.get('hitpoints') <= blstats.get('max_hitpoints') * 2/5:
            return Advice(self.__class__, nethack.actions.Command.SEARCH, None)

        return None

# Thinking outloud ...
# Free/scheduled (eg enhance), Repair major, escape, attack, repair minor, improve/identify, descend, explore

advisors = [
    {
        EnhanceSkillsAdvisor: 1,
    },
    {
        #UseHealingItemWhenCriticallyInjuredAdvisor: 1,
        DrinkHealingPotionWhenCriticallyInjuredAdvisor: 3,
        EatWhenWeakAdvisor: 1,
    },
    {
        PrayWhenCriticallyInjuredAdvisor: 1,
        ZapTeleportWhenCriticallyInjuredAdvisor: 1,
        ReadTeleportWhenCriticallyInjuredAdvisor: 1,
        PrayWhenWeakAdvisor: 1,
        PrayWhenMajorTroubleAdvisor: 1,
    },
    {
        MeleeAttackAdvisor: 1,
    },
    {
        RangedAttackAdvisor: 1,
    },
    {
        PickupAdvisor: 1,
    },
    {
        SearchWhenLowHpAdvisor: 1,
    },
    {
        KickLockedDoorAdvisor: 1,
        MoveDownstairsAdvisor: 1
    },
    {
        MostNovelMoveAdvisor: 200,
        NoUnexploredSearchAdvisor: 200,
        TravelToDownstairsAdvisor: 1,
        MeleeEvenNastyAdvisor: 1,
        RandomMoveAdvisor: 10,
    },
    {
        FallbackSearchAdvisor: 1
    }
]