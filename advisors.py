import random
import glyphs as gd
import nle.nethack as nethack
import menuplan
import utilities
import abc
import environment
import pdb
import numpy as np

# Advisors
# act on the cleaned up state (message obj, neighborhood obj, blstats)
# -> check if condition is satisfied (eg on the downstairs, near locked door)
# -> return a candidate action

# Control
# query all advisors and get a list of advice tagged to advisors
# choose among advisors (can make a ranked list of advisors by priority and deterministically or weighted-randomly choose between them;
# can eventually plug the weighting into NN)

class Flags():
    def __init__(self, blstats, inventory, neighborhood, message):
        self.am_weak = blstats.get('hunger_state') > 2

        # downstairs
        previous_glyph = neighborhood.previous_glyph_on_player
        if previous_glyph is not None: # on the first frame there was no previous glyph
            previous_is_downstairs = getattr(previous_glyph, 'is_downstairs', False)
        else:
            previous_is_downstairs = False

        self.on_downstairs = "staircase down here" in message.message or previous_is_downstairs

        self.bumped_into_locked_door = "This door is locked" in message.message
        self.have_walkable_squares = neighborhood.action_grid[neighborhood.walkable].any() # at least one square is walkable
        self.can_move = True # someday, Held, Handspan etc.

        self.adjacent_univisited_square = (neighborhood.visits[neighborhood.walkable] == 0).any()

        # --- Spooky messages ---
        diagonal_out_of_doorway_message = "You can't move diagonally out of an intact doorway." in message.message
        diagonal_into_doorway_message = "You can't move diagonally into an intact doorway." in message.message
        boulder_in_vain_message = "boulder, but in vain." in message.message
        boulder_blocked_message = "Perhaps that's why you cannot move it." in message.message
        carrying_too_much_message = "You are carrying too much to get through." in message.message
        no_hands_door_message = "You can't open anything -- you have no hands!" in message.message

        self.cant_move_that_way_message = diagonal_out_of_doorway_message or diagonal_into_doorway_message or boulder_in_vain_message or boulder_blocked_message or carrying_too_much_message or no_hands_door_message
        # ---

        is_monster = np.vectorize(lambda g: isinstance(g, gd.MonsterGlyph))(neighborhood.glyphs)
        is_giant_ant_lol = neighborhood.raw_glyphs == 0 # Unfortunate edge casing due to bug
        self.near_monster = (is_monster & ~is_giant_ant_lol & ~neighborhood.players_square_mask).any()

class Advisor(abc.ABC):
    def __init__(self):
        pass

    @abc.abstractmethod
    def check_conditions(self, flags): # returns T/F
        pass

    @abc.abstractmethod
    def advice(self, blstats, inventory, neighborhood, message): # returns action, MenuPlan
        pass

    def give_advice(self, flags, blstats, inventory, neighborhood, message):
        if self.check_conditions(flags):
            return self.advice(blstats, inventory, neighborhood, message)
        else:
            return None, None

### ------------ Approach 1 ------------
class MoveAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.have_walkable_squares

class RandomMoveAdvisor(MoveAdvisor): 
    def advice(self, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[neighborhood.walkable]
        if not possible_actions.any():
            return None, None
        return random.choice(possible_actions), None

class MostNovelMoveAdvisor(MoveAdvisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.have_walkable_squares and not flags.cant_move_that_way_message

    def advice(self, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[neighborhood.walkable]
        visits = neighborhood.visits[neighborhood.walkable]
        most_novel = possible_actions[visits == visits.min()]

        return random.choice(most_novel), None

class VisitUnvisitedSquareAdvisor(MoveAdvisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.adjacent_univisited_square and not flags.cant_move_that_way_message
    def advice(self, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[(neighborhood.visits == 0) & neighborhood.walkable]

        return random.choice(possible_actions), None


class MoveDownstairsAdvisor(MoveAdvisor):
    def check_conditions(self, flags):
        return flags.can_move and flags.on_downstairs

    def advice(self, _1, _2, _3, _4):
        return nethack.actions.MiscDirection.DOWN, None

class KickLockedDoorAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.bumped_into_locked_door

    def advice(self, _, __, neighborhood, ___):
        kick = nethack.actions.Command.KICK
        door_directions = neighborhood.action_grid[np.vectorize(lambda g: getattr(g, 'is_closed_door', False))(neighborhood.glyphs)]
        if len(door_directions) > 0:
            a = random.choice(door_directions)
        else: # we got the locked door message but didn't find a door
            a = None
            if environment.env.debug: pdb.set_trace()
            pass
        menu_plan = menuplan.MenuPlan("kick locked door", {
            "In what direction?": nethack.ACTIONS.index(a),
        })
        #if environment.env.debug: pdb.set_trace()
        return kick, menu_plan

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

    def advice(self, _, inventory, __, ___):
        eat = nethack.actions.Command.EAT
        try:
            FOOD_CLASS = 7
            food_index = inventory['inv_oclasses'].tolist().index(FOOD_CLASS)
        except ValueError:
            food_index = None
        if food_index:
            letter = inventory['inv_letters'][food_index]
            menu_plan = self.make_menu_plan(letter)
            return eat, menu_plan
        else:
            return None, None

class EatWhenWeakAdvisor(EatTopInventoryAdvisor):
    def check_conditions(self, flags):
        return flags.am_weak

class PrayWhenWeakAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.am_weak

    def advice(self, _, __, ___, ____):
        pray = nethack.actions.Command.PRAY
        menu_plan = menuplan.MenuPlan("yes pray", {
            "Are you sure you want to pray?": utilities.keypress_action(ord('y')),
        })

        return pray, menu_plan

class SearchAdvisor(Advisor):
    def check_conditions(self, flags):
        return True # this action is always possible and a good waiting action

    def advice(self, _, __, ___, ____):
        return nethack.ACTIONS.index(nethack.actions.Command.SEARCH), None

class AttackAdvisor(Advisor):
    def check_conditions(self, flags):
        return flags.near_monster

    def advice(self, blstats, inventory, neighborhood, message):
        is_monster = np.vectorize(lambda g: isinstance(g, gd.MonsterGlyph))(neighborhood.glyphs)
        
        is_giant_ant_lol = neighborhood.raw_glyphs == 0 # Unfortunate edge casing due to bug
        monster_directions = neighborhood.action_grid[is_monster & ~neighborhood.players_square_mask & ~is_giant_ant_lol]

        return random.choice(monster_directions), None



advisors = [
    EatWhenWeakAdvisor(),
    PrayWhenWeakAdvisor(),
    MoveDownstairsAdvisor(),
    AttackAdvisor(),
    KickLockedDoorAdvisor(),
    MostNovelMoveAdvisor(),
    #VisitUnvisitedSquareAdvisor(),
    RandomMoveAdvisor(),
    SearchAdvisor(),
]