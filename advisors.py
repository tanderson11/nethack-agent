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

        self.willing_to_descend = exp_lvl_to_max_mazes_lvl.get(blstats.get('experience_level'), 60) > blstats.get('level_number')


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

        if previous_glyph is not None:
            self.desirable_object = isinstance(previous_glyph, gd.ObjectGlyph) and previous_glyph.object_class_name == "FOOD_CLASS"
        else:
            self.desirable_object = False

        is_monster = neighborhood.is_monster()

        self.adjacent_secret_door_possibility = (np.vectorize(lambda g: getattr(g, 'possible_secret_door', False))(neighborhood.glyphs))
        self.near_monster = (is_monster & ~neighborhood.players_square_mask).any()

        self.have_potion = gd.ObjectGlyph.OBJECT_CLASSES.index('POTION_CLASS') in inventory['inv_oclasses']

        self.feverish = "You feel feverish." in message.message

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

class DrinkHealingPotionWhenCriticallyInjuredAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.am_critically_injured and flags.have_potion

    def advice(self, _0, _1, inventory, _3, _4):
        quaff = nethack.actions.Command.QUAFF
        menu_plan = menuplan.MenuPlan("drink healing potion", {"What do you want to drink?": utilities.keypress_action(ord('*'))}, interactive_menu_header_rows=0, menu_item_selector=lambda x: (x.category == "Potions") & ("healing" in x.item_appearance), expects_strange_messages=True)
        return Advice(self.__class__, quaff, menu_plan)

class UseHealingItemWhenCriticallyInjuredAdvisor(Advisor): # right now we only quaff
    def make_menu_plan(self, letter):
        menu_plan = menuplan.MenuPlan("quaff from inventory", {
        "Drink from the fountain?": utilities.keypress_action(ord('n')),
        "want to drink?": utilities.keypress_action(letter),
        })
        return menu_plan

    def check_conditions(self, flags):
        return flags.am_critically_injured

    def advice(self, _0, _1, inventory, _3, _4):
        is_healing = np.vectorize(lambda g: getattr(gd.GLYPH_LOOKUP[g], 'is_identified_healing_object', lambda: False)())(inventory['inv_glyphs'])
        quaff = nethack.actions.Command.QUAFF

        try:
            POTION_CLASS = gd.ObjectGlyph.OBJECT_CLASSES.index('POTION_CLASS')
            is_potion = inventory['inv_oclasses'] == POTION_CLASS
            #if environment.env.debug: pdb.set_trace()
            potion_index = (is_potion & is_healing).tolist().index(True) #stops at first True but borked if all False (quaffs 0th potion even though it's not healing)
        except ValueError:
            potion_index = None

        if potion_index is not None:
            #if environment.env.debug: pdb.set_trace()
            print(np.vectorize(lambda g: getattr(gd.GLYPH_LOOKUP[g], 'name', False))(inventory['inv_glyphs'])[potion_index])
            letter = inventory['inv_letters'][potion_index]
            menu_plan = self.make_menu_plan(letter)
            return Advice(self.__class__, quaff, menu_plan)


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

    def advice(self, rng, blstats, inventory, neighborhood, message):
        is_monster = neighborhood.is_monster()

        never_melee_mask = np.vectorize(lambda g: isinstance(g, gd.MonsterGlyph) and g.never_melee)(neighborhood.glyphs)
        
        monster_directions = neighborhood.action_grid[is_monster & ~neighborhood.players_square_mask & ~never_melee_mask]

        if monster_directions.any():
            return Advice(self.__class__, rng.choice(monster_directions), None)

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


# Thinking outloud ...
# Repair major, escape, attack, repair minor, descend, explore

advisors = [
    {
        #UseHealingItemWhenCriticallyInjuredAdvisor: 1,
        DrinkHealingPotionWhenCriticallyInjuredAdvisor: 1,
        EatWhenWeakAdvisor: 1,
    },
    {
        PrayWhenCriticallyInjuredAdvisor: 1,
        PrayWhenWeakAdvisor: 1,
        PrayWhenMajorTroubleAdvisor: 1,
    },
    {
        AttackAdvisor: 1,
    },
    {
        PickupAdvisor: 1,
    },
    {
        KickLockedDoorAdvisor: 1,
        MoveDownstairsAdvisor: 1
    },
    {
        MostNovelMoveAdvisor: 20,
        NoUnexploredSearchAdvisor: 20,
        TravelToDownstairsAdvisor: 1,
        RandomMoveAdvisor: 1,
    },
    {
        FallbackSearchAdvisor: 1
    }
]