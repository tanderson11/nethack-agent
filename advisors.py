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
    def __init__(self):
        self.flags = np.array()

class Advisor(abc.ABC):
    def __init__(self, predicate_flags):
        pass

    def check_flags(self, state_flags):
        return state_flags[predicate_flags].all()

    @abstractmethod
    def give_advice(self, blstats, inventory, neighborhood, message):
        pass




class Advisor():
    def __init__(self, predicate, advice_function):
        self.predicate = predicate
        self.advice_function = advice_function

    def give_advice(self, blstats, inventory, neighborhood, message):
        if self.predicate(blstats, inventory, neighborhood, message):
            return self.advice_function(blstats, inventory, neighborhood, message)
        else:
            return None, None # action, MenuPlan

# Predicates
# takes: blstats, inventory, neighborhood, message
# returns T/F

def can_move_p(blstats, inventory, neighborhood, message):
    # logic about paralysis, handspan loads, etc.
    return True

def locked_door_near_p(_1, _2, _3, message):
    return "This door is locked" in message.message

def weak_p(blstats, _1, _2, _3):
    return blstats.get('hunger_state') > 2

def on_downstairs_p(_1, _2, neighborhood, message):
    return "staircase down here" in message.message or neighborhood.previous_glyph_on_player == gd.DOWNSTAIRS_GLYPH

# Advice functions
# takes: blstats, inventory, neighborhood, message
# returns (action, MenuPlan)

def random_move(_1, _2, neighborhood, _3):
    possible_actions = neighborhood.action_grid[neighborhood.walkable]
    return random.choice(possible_actions), None

def most_novel_move(_1, _2, neighborhood, _3):
    possible_actions = neighborhood.action_grid[neighborhood.walkable]
    visits = neighborhood.visits[neighborhood.walkable]
    most_novel = possible_actions[visits == visits.min()]

    return random.choice(most_novel), None

def adjacent_locked_door_kick(_1, _2, neighborhood, _3):
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

def top_inventory_eat(_1, inventory, _2, _3):
    eat = nethack.actions.Command.EAT
    try:
        FOOD_CLASS = 7
        food_index = inventory['inv_oclasses'].tolist().index(FOOD_CLASS)
    except ValueError:
        food_index = None
    if food_index:
        letter = inventory['inv_letters'][food_index]
        menu_plan = menuplan.MenuPlan("eat from inventory", {
            "here; eat": utilities.keypress_action(ord('n')),
            "want to eat?": utilities.keypress_action(letter),
            "You succeed in opening the tin.": utilities.keypress_action(ord(' ')),
            "smells like": utilities.keypress_action(ord('y')),
            "Rotten food!": utilities.keypress_action(ord(' ')),
            "Eat it?": utilities.keypress_action(ord('y')),
        })
        return eat, menu_plan
    else:
        return None, None

def prayer(_1, _2, _3, _4):
    pray = nethack.actions.Command.PRAY
    menu_plan = menuplan.MenuPlan("yes pray", {
        "Are you sure you want to pray?": utilities.keypress_action(ord('y')),
    })

    return pray, menu_plan

def downstairs_move(_1, _2, _3, _4):
    return nethack.actions.MiscDirection.DOWN, None

move_randomly = Advisor(can_move_p, random_move)
move_to_most_novel_square = Advisor(can_move_p, most_novel_move)
kick_locked_doors = Advisor(locked_door_near_p, adjacent_locked_door_kick)
eat_from_inv_when_weak = Advisor(weak_p, top_inventory_eat)
pray_when_weak = Advisor(weak_p, prayer)
go_downstairs = Advisor(on_downstairs_p, downstairs_move)