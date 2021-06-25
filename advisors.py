import random
import glyphs as gd
import nle.nethack as nethack
import menuplan
import utilities
import abc

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
        if  "staircase down here" in message.message:
            self.on_downstairs = True
        else:
            previous_glyph = neighborhood.previous_glyph_on_player
            if previous_glyph is not None:
                try:
                    self.on_downstairs = gd.GLYPH_LOOKUP[previous_glyph].is_downstairs()
                except AttributeError:
                    self.on_downstairs = False
            else:
                self.on_downstairs = False


        self.bumped_into_locked_door = "This door is locked" in message.message
        self.can_move = True

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
        return flags.can_move

class RandomMoveAdvisor(MoveAdvisor): 
    def advice(self, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[neighborhood.walkable]
        return random.choice(possible_actions), None

class NovelMoveAdvisor(MoveAdvisor):
    def advice(self, blstats, inventory, neighborhood, message):
        possible_actions = neighborhood.action_grid[neighborhood.walkable]
        visits = neighborhood.visits[neighborhood.walkable]
        most_novel = possible_actions[visits == visits.min()]

        return random.choice(most_novel), None

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
        door_directions = neighborhood.glyph_set_to_directions(gd.DOOR_GLYPHS)
        if len(door_directions) > 0:
            a = random.choice(door_directions)
        else: # we got the locked door message but didn't find a door
            a = None
            if environment.env.debug: pdb.set_trace()
            pass
        menu_plan = menuplan.MenuPlan("kick locked door", {
            "In what direction?": nethack.ACTIONS.index(a),
        })
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

advisors = [
    EatWhenWeakAdvisor(),
    PrayWhenWeakAdvisor(),
    MoveDownstairsAdvisor(),
    KickLockedDoorAdvisor(),
    #NovelMoveAdvisor(),
    RandomMoveAdvisor()
]