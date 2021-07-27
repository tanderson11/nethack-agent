import abc
from collections import OrderedDict
import functools
import pdb

import glyphs as gd
import nle.nethack as nethack
import numpy as np

import physics
import environment
import menuplan
import utilities
from utilities import ARS
import inventory as inv
import inspect

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

    def __init__(self, run_state, blstats, inventory, neighborhood, message, character):
        self.run_state = run_state
        self.blstats = blstats
        self.inventory = inventory
        self.neighborhood = neighborhood
        self.message = message
        self.character = character

        self.computed_values = {}

    @functools.cached_property
    def am_weak(self):
        am_weak = self.blstats.get('hunger_state') > 2
        return am_weak

    @functools.cached_property
    def am_satiated(self):
        am_satiated = self.blstats.get('hunger_state') > 2
        return am_satiated

    @functools.cached_property
    def am_critically_injured(self):
        fraction_index = [k for k in list(self.__class__.exp_lvl_to_prayer_hp_thresholds.keys()) if k <= self.blstats.get('experience_level')][-1]
        hp = self.blstats.get('hitpoints')
        am_critically_injured = hp < self.blstats.get('max_hitpoints') and (hp < self.__class__.exp_lvl_to_prayer_hp_thresholds[fraction_index] or hp < 6)
        return am_critically_injured

    @functools.cached_property
    def am_low_hp(self):
        am_low_hp = self.am_critically_injured or self.blstats.get('hitpoints') <= self.blstats.get('max_hitpoints') * 6/10
        return am_low_hp

    @functools.cached_property
    def on_downstairs(self):
        previous_is_downstairs = isinstance(self.neighborhood.previous_glyph_on_player, gd.CMapGlyph) and self.neighborhood.previous_glyph_on_player.is_downstairs
        try:
            staircase = self.neighborhood.level_map.staircases[self.neighborhood.absolute_player_location]
            direction = staircase.direction
        except KeyError:
            direction = None

        on_downstairs = "staircase down here" in self.message.message or direction == 'down' or previous_is_downstairs
        return on_downstairs

    @functools.cached_property
    def on_upstairs(self):
        previous_is_upstairs = isinstance(self.neighborhood.previous_glyph_on_player, gd.CMapGlyph) and self.neighborhood.previous_glyph_on_player.is_upstairs
        try:
            staircase = self.neighborhood.level_map.staircases[self.neighborhood.absolute_player_location]
            direction = staircase.direction
        except KeyError:
            direction = None

        on_upstairs = "staircase up here" in self.message.message or direction == 'up' or previous_is_upstairs
        return on_upstairs

    @functools.cached_property
    def on_warning_engraving(self):
        return self.neighborhood.level_map.warning_engravings.get(self.neighborhood.absolute_player_location, False)

    @functools.cached_property
    def can_move(self):
        # someday Held, Handspan, Overburdened etc.
        can_move = not self.message.feedback.collapse_message
        return can_move

    @functools.cached_property
    def have_moves(self):
        have_moves = self.neighborhood.walkable.any() # at least one square is walkable
        return have_moves

    @functools.cached_property
    def have_unthreatened_moves(self):
        have_unthreatened_moves = (self.neighborhood.walkable & ~self.neighborhood.threatened).any() # at least one square is walkable
        return have_unthreatened_moves

    @functools.cached_property
    def desirable_object_on_space(self):
        prev_glyph = self.neighborhood.previous_glyph_on_player
        desirable_object_on_space = (isinstance(prev_glyph, gd.ObjectGlyph) or isinstance(prev_glyph, gd.CorpseGlyph)) and prev_glyph.desirable_object(self.run_state.global_identity_map, self.character)

        return desirable_object_on_space

    @functools.cached_property
    def near_monster(self):
        near_monster = (self.neighborhood.is_monster & ~self.neighborhood.player_location_mask).any()
        return near_monster

    @functools.cached_property
    def major_trouble(self):
        major_trouble = "You feel feverish." in self.message.message or "You are slowing down" in self.message.message
        return major_trouble

    @functools.cached_property
    def can_enhance(self):    
        can_enhance = "You feel more confident" in self.message.message or "could be more dangerous" in self.message.message
        return can_enhance

    @functools.cached_property
    def fresh_corpse_on_square(self):    
        fresh_corpse_on_square = (self.neighborhood.fresh_corpse_on_square_glyph is not None)
        return fresh_corpse_on_square

    @functools.cached_property
    def in_gnomish_mines(self):
        in_gnomish_mines = self.blstats.get('dungeon_number') == 2
        return in_gnomish_mines

class AdvisorLevel():
    def __init__(self, advisors, skip_probability=0):
        self.advisors = advisors
        self.skip_probability = skip_probability

    def check_if_random_skip(self, rng):
        if self.skip_probability > 0 and rng.random() < self.skip_probability:
            return True
        return False

    def check_flags(self, flags):
        return True

    def check_level(self, flags, rng):
        if self.check_if_random_skip(rng): return False
        return self.check_flags(flags)

class ThreatenedMoreThanOnceAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.neighborhood.n_threat[flags.neighborhood.player_location_mask] > 1
        
class AmUnthreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.neighborhood.n_threat[flags.neighborhood.player_location_mask] == 0

class MajorTroubleAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.major_trouble

class SafeAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return ~flags.am_low_hp and ~flags.neighborhood.monster_present and ~flags.am_weak

class UnthreatenedMovesAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.have_unthreatened_moves

class FreeImprovementAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.can_enhance

class AllMovesThreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return not flags.have_unthreatened_moves

class CriticallyInjuredAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_critically_injured

class CriticallyInjuredAndUnthreatenedAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_critically_injured and flags.neighborhood.n_threat[flags.neighborhood.player_location_mask] == 0

class DungeonsOfDoomAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.blstats.get('dungeon_number') == 0

class GnomishMinesAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.in_gnomish_mines

class NoMovesAdvisor(AdvisorLevel):
    def check_flags(self, flags):
        return not flags.have_moves

class WeakWithHungerAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_weak

class AdjacentToMonsterAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.near_monster

class LowHPAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_low_hp

class UnthreatenedLowHPAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.am_low_hp & (flags.neighborhood.n_threat[flags.neighborhood.player_location_mask] == 0)

class AdjacentToMonsterAndLowHpAdvisorLevel(AdvisorLevel):
    def check_flags(self, flags):
        return flags.near_monster and flags.am_low_hp

class Advisor(abc.ABC):
    def __init__(self):
        pass

    @abc.abstractmethod
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags): # returns action, MenuPlan
        pass

class BackgroundActionsAdvisor(Advisor): # dummy advisor to hold background menu plans
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        pass

class MoveAdvisor(Advisor): # this should be some kind of ABC as well, just don't know quite how to chain them # should be ABC over find_agreeable_moves
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.can_move and flags.have_moves:
            agreeable_move_mask = self.find_agreeable_moves(run_state, rng, blstats, inventory, neighborhood, message, character)
            return self.get_move(rng, blstats, inventory, neighborhood, message, agreeable_move_mask)
        else:
            return None

class RandomMoveAdvisor(MoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable

    def get_move(self, rng, blstats, inventory, neighborhood, message, agreeable_move_mask):
        possible_actions = neighborhood.action_grid[agreeable_move_mask]

        if possible_actions.any():
            return Advice(self.__class__, rng.choice(possible_actions), None)
        else:
            return None

class VisitUnvisitedSquareAdvisor(RandomMoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened & (neighborhood.visits == 0)

class MostNovelMoveAdvisor(MoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable

    def get_move(self, rng, blstats, inventory, neighborhood, message, agreeable_move_mask):
        possible_actions = neighborhood.action_grid[agreeable_move_mask]
        visits = neighborhood.visits[agreeable_move_mask]

        if len(visits) > 0: # len in case all sqaures that are walkable have 0 visits
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

class ContinueMovementIfUnthreatenedAdvisor(MoveAdvisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.can_move and flags.have_moves and neighborhood.last_movement_action is not None:
            next_target = physics.offset_location_by_action(neighborhood.local_player_location, neighborhood.last_movement_action)

            try:
                is_threatened = neighborhood.threatened[next_target]
                is_walkabe = neighborhood.walkable[next_target]
            except IndexError:
                return None

            if is_walkabe and not is_threatened:
                return Advice(self.__class__, neighborhood.action_grid[x+dx, y+dy], None)
            else:
                return None
        else:
            return None

class LeastNovelUnthreatenedMoveAdvisor(LeastNovelMoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened

class LeastNovelNonObjectGlyphMoveAdvisor(LeastNovelMoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened & utilities.vectorized_map(lambda g: not isinstance(g, gd.ObjectGlyph), neighborhood.glyphs)

class MostNovelUnthreatenedMoveAdvisor(MostNovelMoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened

class FreshCorpseMoveAdvisor(RandomMoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & neighborhood.has_fresh_corpse & ~neighborhood.threatened

class DesirableObjectMoveAdvisor(RandomMoveAdvisor):
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & utilities.vectorized_map(lambda g: isinstance(g, gd.ObjectGlyph) and g.desirable_object(run_state.global_identity_map, character), neighborhood.glyphs) & ~neighborhood.threatened

class RandomLeastThreatenedMoveAdvisor(RandomMoveAdvisor): 
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & (neighborhood.n_threat == neighborhood.n_threat.min())

class RandomUnthreatenedMoveAdvisor(RandomMoveAdvisor): 
    def find_agreeable_moves(self, run_state, rng, blstats, inventory, neighborhood, message, character):
        return neighborhood.walkable & ~neighborhood.threatened

class PrayerAdvisor(Advisor):
    def advice(self, run_state, rng, character, blstats, _2, _3, _4, _5):
        if character.last_pray_time is None and blstats.get('time') <= 300:
            return None
        if character.last_pray_time is not None and (blstats.get('time') - character.last_pray_time) < 250:
            return None
        pray = nethack.actions.Command.PRAY
        menu_plan = menuplan.MenuPlan("yes pray", self, [
            menuplan.YesMenuResponse("Are you sure you want to pray?")
        ])
        return Advice(self.__class__, pray, menu_plan)

class PrayWhenWeakAdvisor(PrayerAdvisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.am_weak:
            return super().advice(run_state, rng, character, blstats, inventory, neighborhood, message, flags)
        else:
            return None

class PrayWhenCriticallyInjuredAdvisor(PrayerAdvisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.am_critically_injured:
            return super().advice(run_state, rng, character, blstats, inventory, neighborhood, message, flags)
        else:
            return None

class PrayWhenMajorTroubleAdvisor(PrayerAdvisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.major_trouble:
            return super().advice(run_state, rng, character, blstats, inventory, neighborhood, message, flags)
        else:
            return None

class UpstairsAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.can_move and flags.on_upstairs:
            willing_to_ascend = self.willing_to_ascend(rng, character, blstats, inventory, neighborhood, message, flags)
            if willing_to_ascend:
                menu_plan = menuplan.MenuPlan("go upstairs", self, [
                      menuplan.NoMenuResponse("Beware, there will be no return!  Still climb? [yn] (n)"),
                  ])
                return Advice(self.__class__, nethack.actions.MiscDirection.UP, None)
            return None
        return None

    def willing_to_ascend(self, rng, character, blstats, inventory, neighborhood, message, flags):
        return True 

class TraverseUnknownUpstairsAdvisor(UpstairsAdvisor):
    def willing_to_ascend(self, rng, character, blstats, inventory, neighborhood, message, flags):
        try:
            # if we know about this staircase, we're not interested
            staircase = neighborhood.level_map.staircases[neighborhood.absolute_player_location]
            return False
        except:
            return True

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
    def check_willingness_to_descend(cls, blstats, inventory, neighborhood):
        try:
            # see if we know about this staircase
            staircase = neighborhood.level_map.staircases[neighborhood.absolute_player_location]
            # don't descend if it leads to the mines
            if staircase.end_dcoord[0] == 2:
                return False
        except KeyError:
            pass

        willing_to_descend = blstats.get('hitpoints') == blstats.get('max_hitpoints')
        if inventory.have_item_oclass(inv.Food):
            willing_to_descend = willing_to_descend and cls.exp_lvl_to_max_mazes_lvl.get(blstats.get('experience_level'), 60) > blstats.get('depth')
        else:
            willing_to_descend = willing_to_descend and cls.exp_lvl_to_max_mazes_lvl_no_food.get(blstats.get('experience_level'), 60) > blstats.get('depth')
        
        #willing_to_descend = willing_to_descend and cls.exp_lvl_to_max_mazes_lvl.get(blstats.get('experience_level'), 60) > blstats.get('depth')
        return willing_to_descend

    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        pass

class TakeDownstairsAdvisor(DownstairsAdvisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.can_move and flags.on_downstairs:
            willing_to_descend = self.__class__.check_willingness_to_descend(blstats, inventory, neighborhood)
            if willing_to_descend:
                return Advice(self.__class__, nethack.actions.MiscDirection.DOWN, None)
            return None
        return None

class OpenClosedDoorAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        # coarse check
        if flags.on_warning_engraving:
            return None

        door_directions = neighborhood.action_grid[utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_closed_door, neighborhood.glyphs)]
        if len(door_directions > 0):
            a = rng.choice(door_directions)
            # better check: don't want to open doors if they are adjacent to an engraving
            for location in neighborhood.level_map.warning_engravings.keys():
                door_loc = physics.offset_location_by_action(neighborhood.absolute_player_location, utilities.ACTION_LOOKUP[a])
                if np.abs(door_loc[0] - location[0]) < 2 and np.abs(door_loc[1] - location[1]) < 2:
                    #if environment.env.debug: import pdb; pdb.set_trace()
                    return None
        else:
            return None

        return Advice(self.__class__, a, None)

class KickLockedDoorAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.on_warning_engraving:
            return None
        if not "This door is locked" in message.message:
            return None
        kick = nethack.actions.Command.KICK
        door_directions = neighborhood.action_grid[utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_closed_door, neighborhood.glyphs)]
        if len(door_directions) > 0:
            a = rng.choice(door_directions)
            for location in neighborhood.level_map.warning_engravings.keys():
                door_loc = physics.offset_location_by_action(neighborhood.absolute_player_location, utilities.ACTION_LOOKUP[a])
                if np.abs(door_loc[0] - location[0]) < 2 and np.abs(door_loc[1] - location[1]) < 2:
                    if environment.env.debug: import pdb; pdb.set_trace()
                    return None
        else: # we got the locked door message but didn't find a door
            a = None
            if environment.env.debug: import pdb; pdb.set_trace()
            pass
        if a is not None:
            menu_plan = menuplan.MenuPlan("kick locked door", self, [
                menuplan.DirectionMenuResponse("In what direction?", a),
            ])
            return Advice(self.__class__, kick, menu_plan)

class WearUnblockedArmorAdvisor(Advisor):
    def advice(self, run_state, rng, character, blstats, inventory, neighborhood, message, flags):
        proposed_items, proposal_blockers = inventory.proposed_attire_changes(character)

        for item, blockers in zip(proposed_items, proposal_blockers):
            if len(blockers) == 0:
                wear = nethack.actions.Command.WEAR

                menu_plan = menuplan.MenuPlan("wear armor", self, [
                    menuplan.CharacterMenuResponse("What do you want to wear?", chr(item.inventory_letter)),
                ], listening_item=item)

                return Advice(self.__class__, wear, menu_plan)
        return None

class WearEvenBlockedArmorAdvisor(Advisor):
    def advice(self, run_state, rng, character, blstats, inventory, neighborhood, message, flags):
        proposed_items, proposal_blockers = inventory.proposed_attire_changes(character)

        for item, blockers in zip(proposed_items, proposal_blockers):
            if len(blockers) == 0:
                wear = nethack.actions.Command.WEAR

                menu_plan = menuplan.MenuPlan("wear armor", self, [
                    menuplan.CharacterMenuResponse("What do you want to wear?", chr(item.inventory_letter)),
                ], listening_item=item)

                return Advice(self.__class__, wear, menu_plan)

            else:
                takeoff = nethack.actions.Command.TAKEOFF
                menu_plan = menuplan.MenuPlan("take off blocking armor", self, [
                    menuplan.CharacterMenuResponse("What do you want to take off?", chr(blockers[0])),
                ])

                return Advice(self.__class__, takeoff, menu_plan)

class EatTopInventoryAdvisor(Advisor):
    def make_menu_plan(self, letter):
        menu_plan = menuplan.MenuPlan("eat from inventory", self, [
            menuplan.NoMenuResponse("here; eat"),
            menuplan.CharacterMenuResponse("want to eat?", chr(letter)),
            menuplan.MoreMenuResponse("You succeed in opening the tin."),
            menuplan.MoreMenuResponse("smells like"),
            menuplan.MoreMenuResponse("It contains"),
            menuplan.YesMenuResponse("Eat it?"),
            menuplan.MoreMenuResponse("You're having a hard time getting all of it down."),
            menuplan.NoMenuResponse("Continue eating"),
            #menuplan.MoreMenuResponse("You resume your meal"),
        ])
        return menu_plan

    def advice(self, run_state, rng, character, blstats, inventory, neighborhood, message, flags):
        eat = nethack.actions.Command.EAT
        food = inventory.get_oclass(inv.Food) # not eating corpses atm TK TK
        if len(food) > 0:
            letter = food[0].inventory_letter
            menu_plan = self.make_menu_plan(letter)
            return Advice(self.__class__, eat, menu_plan)
        return None

class ReadTeleportAdvisor(Advisor):
    def advice(self, run_state, rng, character, blstats, inventory, neighborhood, message, flags):
        read = nethack.actions.Command.READ
        scrolls = inventory.get_oclass(inv.Scroll)

        for scroll in scrolls:
            if scroll.identity and scroll.identity.name() == 'teleport':
                letter = scrolls.inventory_letter
                menu_plan = menuplan.MenuPlan("read teleport scroll", self, [
                    menuplan.CharacterMenuResponse("What do you want to read?", chr(letter))
                ])
                return Advice(self.__class__, read, menu_plan)
        return None

class ZapTeleportOnSelfAdvisor(Advisor):
    def advice(self, run_state, rng, character, blstats, inventory, neighborhood, message, flags):
        zap = nethack.actions.Command.ZAP
        wands = inventory.get_oclass(inv.Wand)

        for wand in wands:
            if wand.identity and wand.identity.name() == 'teleportation':
                letter = wand.inventory_letter
                menu_plan = menuplan.MenuPlan("zap teleportation wand", self, [
                    menuplan.CharacterMenuResponse("What do you want to zap?", chr(letter))
                ])
                return Advice(self.__class__, read, menu_plan)
        return None

class DrinkHealingPotionAdvisor(Advisor):
    def advice(self, run_state, rng, character, blstats, inventory, neighborhood, message, flags):
        quaff = nethack.actions.Command.QUAFF
        potions = inventory.get_oclass(inv.Potion)

        for potion in potions:
            if potion.identity and potion.identity.name() and 'healing' in potion.identity.name():
                menu_plan = menuplan.MenuPlan(
                    "drink healing potion", self, [
                        menuplan.CharacterMenuResponse("What do you want to drink?", chr(letter)),
                        menuplan.NoMenuResponse("Drink from the fountain?"),
                        menuplan.NoMenuResponse("Drink from the sink?"),
                    ])
                return Advice(self.__class__, quaff, menu_plan)
        return None

class FallbackSearchAdvisor(Advisor):
    def advice(self, run_state, rng,character, _1, _2, _3, _4, _5):
        return Advice(self.__class__, nethack.actions.Command.SEARCH, None)

class NoUnexploredSearchAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.on_warning_engraving:
            return None
        if not (neighborhood.visits[neighborhood.walkable] == 0).any() and (utilities.vectorized_map(lambda g: getattr(g, 'possible_secret_door', False), neighborhood.glyphs)).any():
            return Advice(self.__class__, nethack.actions.Command.SEARCH, None)
        return None

class RandomAttackAdvisor(Advisor):
    def get_target_monsters(self, neighborhood):
        always_peaceful = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.always_peaceful, neighborhood.glyphs)
        targeted_monster_mask = neighborhood.is_monster & ~neighborhood.player_location_mask & ~always_peaceful
        return targeted_monster_mask

    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
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
        has_death_throes_mask = utilities.vectorized_map(lambda g: isinstance(g, gd.MonsterGlyph) and g.has_death_throes, neighborhood.glyphs)
        targeted_monster_mask = neighborhood.is_monster & ~neighborhood.player_location_mask & ~has_passive_mask & ~always_peaceful & ~has_death_throes_mask
        return targeted_monster_mask

class DeterministicSafeMeleeAttack(RandomSafeMeleeAttack):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        targeted_monster_mask = self.get_target_monsters(neighborhood)
        monster_directions = neighborhood.action_grid[targeted_monster_mask]
        if monster_directions.any():
            attack_direction = monster_directions[0]
            return Advice(self.__class__, attack_direction, None)
        return None

class RandomRangedAttackAdvisor(RandomAttackAdvisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        targeted_monster_mask = self.get_target_monsters(neighborhood)

        monster_directions = neighborhood.action_grid[targeted_monster_mask]

        if monster_directions.any():
            fire = nethack.actions.Command.FIRE
            attack_direction = rng.choice(monster_directions)

            weapons = inventory.get_oclass(inv.Weapon)
            if len(weapons) > 1:
                menu_plan = menuplan.MenuPlan(
                    "ranged attack", self, [
                        menuplan.DirectionMenuResponse("In what direction?", attack_direction),
                        menuplan.MoreMenuResponse("You have no ammunition"),
                        menuplan.MoreMenuResponse("You ready"),
                        # note throw: means we didn't have anything quivered
                        menuplan.CharacterMenuResponse("What do you want to throw?", '*')
                    ],
                    interactive_menu=menuplan.InteractiveInventoryMenu(run_state, 'extra weapons'),
                )
                return Advice(self.__class__, fire, menu_plan)

            return None
        return None

class PickupFoodAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.desirable_object_on_space:
            menu_plan = menuplan.MenuPlan(
                "pick up comestibles and safe corpses",
                self,
                [],
                interactive_menu=menuplan.InteractivePickupMenu(run_state, 'comestibles'),
            )
            #print("Food pickup")
            return Advice(self.__class__, nethack.actions.Command.PICKUP, menu_plan)
        return None

class PickupArmorAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if flags.desirable_object_on_space: #You have much trouble lifting a splint mail.  Continue? [ynq] (q)     
            menu_plan = menuplan.MenuPlan(
                "pick up armor",
                self,
                [],
                interactive_menu=menuplan.InteractivePickupMenu(run_state, 'armor'),
            )
            #print("Armor pickup")
            return Advice(self.__class__, nethack.actions.Command.PICKUP, menu_plan)
        return None

class EatCorpseAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        if not flags.fresh_corpse_on_square:
            return None

        if flags.am_satiated:
            return None

        if not neighborhood.fresh_corpse_on_square_glyph.safe_to_eat(character):
            return None

        menu_plan = menuplan.MenuPlan(
            "eat corpse on square", self,
            [
                menuplan.YesMenuResponse(f"{neighborhood.fresh_corpse_on_square_glyph.name} corpse here; eat"),
                menuplan.NoMenuResponse("here; eat"),
                menuplan.EscapeMenuResponse("want to eat?"),
                menuplan.MoreMenuResponse("You're having a hard time getting all of it down."),
                #menuplan.MoreMenuResponse("You resume your meal"),
                menuplan.NoMenuResponse("Continue eating"),
            ])
        return Advice(self.__class__, nethack.actions.Command.EAT, menu_plan)

class TravelToDownstairsAdvisor(DownstairsAdvisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        willing_to_descend = self.__class__.check_willingness_to_descend(blstats, inventory, neighborhood)
        
        if willing_to_descend:
            travel = nethack.actions.Command.TRAVEL

            menu_plan = menuplan.MenuPlan(
                "travel down", self, [
                    menuplan.CharacterMenuResponse("Where do you want to travel to?", ">"),
                    menuplan.EscapeMenuResponse("Can't find dungeon feature"),
                ],
                fallback=utilities.keypress_action(ord('.')))
     
            return Advice(self.__class__, travel, menu_plan)
        return None

class EnhanceSkillsAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        enhance = nethack.actions.Command.ENHANCE
        menu_plan = menuplan.MenuPlan(
            "enhance skills",
            self,
            [],
            interactive_menu=menuplan.InteractiveEnhanceSkillsMenu(run_state),
        )

        return Advice(self.__class__, enhance, menu_plan)

class EngraveTestWandsAdvisor(Advisor):
    def advice(self, run_state, rng,character, blstats, inventory, neighborhood, message, flags):
        engrave = nethack.actions.Command.ENGRAVE
        wands = inventory.get_oclass(inv.Wand)
        letter = None
        for w in wands:
            if not w.identity.is_identified() and not w.identity.listened_actions.get(utilities.ACTION_LOOKUP[engrave], False):
                letter = w.inventory_letter
                break

        if letter is None:
            return None

        menu_plan = menuplan.MenuPlan("engrave test wand", self, [
            menuplan.CharacterMenuResponse("What do you want to write with?", chr(letter)),
            menuplan.MoreMenuResponse("You write in the dust with"),
            menuplan.MoreMenuResponse("A lit field surrounds you!"),
            menuplan.MoreMenuResponse("is a wand of lightning!"), # TK regular expressions in MenuResponse matching
            menuplan.MoreMenuResponse("is a wand of digging!"),
            menuplan.MoreMenuResponse("is a wand of fire!"),
            menuplan.MoreMenuResponse("You engrave in the"),
            menuplan.MoreMenuResponse("You engrave in the floor with a wand of digging."),
            menuplan.MoreMenuResponse("You burn into the"),
            menuplan.MoreMenuResponse("Agent the"), # best match for enlightenment without regex
            menuplan.MoreMenuResponse("Your intelligence is"),
            menuplan.MoreMenuResponse("You wipe out the message that was written here"),
            menuplan.MoreMenuResponse("The feeling subsides"),
            menuplan.MoreMenuResponse("The engraving on the floor vanishes!"),
            menuplan.MoreMenuResponse("You may wish for an object"),
            menuplan.PhraseMenuResponse("For what do you wish?", "+2 blessed silver dragon scale mail"),
            menuplan.MoreMenuResponse("silver dragon scale mail"),
            menuplan.PhraseMenuResponse("What do you want to burn", "Elbereth"),
            menuplan.PhraseMenuResponse("What do you want to engrave", "Elbereth"),
            menuplan.PhraseMenuResponse("What do you want to write", "Elbereth"),
        ], listening_item=w)

        #pdb.set_trace()
        return Advice(self.__class__, engrave, menu_plan)
