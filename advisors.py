import abc
from dataclasses import dataclass
import enum

import glyphs as gd
import nle.nethack as nethack
import numpy as np

import functools

import map
import physics
import environment
import neighborhood
import menuplan
import utilities
from utilities import ARS
import inventory as inv
import constants
import re


class Oracle():
    def __init__(self, run_state, character, neighborhood, message, blstats):
        self.run_state = run_state
        self.character = character
        self.neighborhood = neighborhood
        self.message = message
        self.blstats = blstats

    @functools.cached_property
    def can_move(self):
        # TK Held, overburdened, etc.
        return True

    @functools.cached_property
    def weak_with_hunger(self):
        return self.blstats.get('hunger_state') > 2

    @functools.cached_property
    def am_satiated(self):
        return self.blstats.get('hunger_state') == 0

    @functools.cached_property
    def can_pray_for_hp(self):
        level = self.character.experience_level
        current_hp = self.character.current_hp
        max_hp = self.character.max_hp
        if current_hp < 6: return True
        elif level < 6 and current_hp < max_hp * 1/5: return True
        elif level < 14 and current_hp < max_hp * 1/6: return True
        elif level < 22 and current_hp < max_hp * 1/7: return True
        elif level < 30 and current_hp < max_hp * 1/8: return True
        elif level == 30 and current_hp < max_hp * 1/9: return True
        else: return False

    @functools.cached_property
    def critically_injured(self):
        current_hp = self.character.current_hp
        max_hp = self.character.max_hp

        if current_hp == max_hp: return False
        else: return self.can_pray_for_hp

    @functools.cached_property
    def low_hp(self):
        current_hp = self.character.current_hp
        max_hp = self.character.max_hp
        return current_hp < max_hp * 0.6

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


    @functools.cached_property
    def deadly_condition(self):
        return (
            #self.blstats.check_condition(nethack.BL_MASK_TERMILL) or
            self.blstats.check_condition(nethack.BL_MASK_FOODPOIS)
            # TODO Requires NLE upgrade:
            # self.blstats.check_condition(nethack.BL_MASK_TERMILL)
        )

    @functools.cached_property
    def minor_unicorn_condition(self):
        return (
            self.nuisance_condition or
            self.blind
        )

    @functools.cached_property
    def nuisance_condition(self):
        return (
            self.blstats.check_condition(nethack.BL_MASK_HALLU) or
            self.blstats.check_condition(nethack.BL_MASK_STUN) or
            self.blstats.check_condition(nethack.BL_MASK_CONF)
        )

    @functools.cached_property
    def blind(self):
        return self.blstats.check_condition(nethack.BL_MASK_BLIND)

    @functools.cached_property
    def have_stethoscope(self):
        return self.character.inventory.have_stethoscope()

    @functools.cached_property
    def have_free_stethoscope_action(self):
        return not self.run_state.used_free_stethoscope_move

    @functools.cached_property
    def am_threatened(self):
        return self.neighborhood.threat_on_player > 0.

    @functools.cached_property
    def recently_damaged(self):
        return self.run_state.last_damage_timestamp is not None and (self.run_state.time - self.run_state.last_damage_timestamp < 10)

    @functools.cached_property
    def am_safe(self):
        return not self.weak_with_hunger and not self.am_threatened and self.character.current_hp > self.character.max_hp * 2/3 and not self.recently_damaged

    @functools.cached_property
    def life_threatened(self):
        return self.neighborhood.threat_on_player > self.character.current_hp

    @functools.cached_property
    def on_warning_engraving(self):
        return self.neighborhood.level_map.warning_engravings.get(self.neighborhood.absolute_player_location, False)

    @functools.cached_property
    def desirable_object_on_space(self):
        return self.neighborhood.desirable_object_on_space(self.run_state.global_identity_map, self.character)

    @functools.cached_property
    def have_moves(self):
        have_moves = self.neighborhood.walkable.any() # at least one square is walkable
        return have_moves

    @functools.cached_property
    def adjacent_monsters(self):
        return np.count_nonzero(self.neighborhood.is_monster)

    @functools.cached_property
    def in_shop(self):
        return self.neighborhood.in_shop

    @functools.cached_property
    def urgent_major_trouble(self):
        return (
            self.blstats.check_condition(nethack.BL_MASK_STONE) or
            self.blstats.check_condition(nethack.BL_MASK_SLIME) or
            self.deadly_condition
        )

    @functools.cached_property
    def major_trouble(self):
        return self.character.afflicted_with_lycanthropy

    @functools.cached_property
    def in_gnomish_mines(self):
        in_gnomish_mines = self.blstats.get('dungeon_number') == 2
        return in_gnomish_mines

    @functools.cached_property
    def on_downstairs(self):
        return self.neighborhood.dungeon_glyph_on_player and self.neighborhood.dungeon_glyph_on_player.is_downstairs

    @functools.cached_property
    def on_upstairs(self):
        return self.neighborhood.dungeon_glyph_on_player and self.neighborhood.dungeon_glyph_on_player.is_upstairs

    @functools.cached_property
    def on_stairs(self):
        return self.on_downstairs or self.on_upstairs

class Advisor(abc.ABC):
    def __init__(self, oracle_consultation=None, threat_tolerance=None, threat_threshold=None, no_adjacent_monsters=False):
        self.consult = oracle_consultation
        self.threat_tolerance = threat_tolerance
        self.threat_threshold = threat_threshold
        self.no_adjacent_monsters = no_adjacent_monsters

    def check_conditions(self, run_state, character, oracle):
        if self.threat_tolerance == 0. and (oracle.critically_injured or oracle.life_threatened):
            #import pdb; pdb.set_trace()
            pass

        if self.threat_tolerance is not None and run_state.neighborhood.threat_on_player > (character.current_hp * self.threat_tolerance):
            return False

        if self.threat_threshold is not None and run_state.neighborhood.threat_on_player <= (character.current_hp * self.threat_threshold):
            return False

        if self.no_adjacent_monsters == True and run_state.neighborhood.is_monster.any():
            return False

        if self.consult and self.consult(oracle) == False:
            return False

        return True

    def advice_on_conditions(self, rng, run_state, character, oracle):
        if self.check_conditions(run_state, character, oracle):
            return self.advice(rng, run_state, character, oracle)
        else:
            return None

    @abc.abstractmethod
    def advice(self, rng, run_state, character, oracle):
        pass

    def advice_selected(self):
        pass

class Advice():
    pass

@dataclass
class ActionAdvice(Advice):
    from_advisor: Advisor
    action: enum.IntEnum # The nle Command
    new_menu_plan: menuplan.MenuPlan = None # Advising to set this as the new one

    def __repr__(self):
        return "Advice: (action={}; advisor={}; menu_plan={})".format(self.action, self.from_advisor, self.new_menu_plan)

    def __post_init__(self):
        utilities.ACTION_LOOKUP[self.action] # check that this exists
        # This is kinda sketchy, should be a pre init, but fine for now
        if np.isscalar(self.action):
            self.action = utilities.INT_TO_ACTION[self.action]

@dataclass
class StethoscopeAdvice(Advice):
    from_advisor: Advisor
    action: enum.IntEnum # The nle Command
    direction: int
    new_menu_plan: menuplan.MenuPlan = None # Advising to set this as the new one

    def __repr__(self):
        return "Stethoscope advice: (direction = {}; action={}; advisor={}; menu_plan={})".format(self.direction, self.action, self.from_advisor, self.new_menu_plan)

    def __post_init__(self):
        utilities.ACTION_LOOKUP[self.action] # check that this exists
        # This is kinda sketchy, should be a pre init, but fine for now
        if np.isscalar(self.action):
            self.action = utilities.INT_TO_ACTION[self.action]

@dataclass
class MenuAdvice(Advice):
    from_menu_plan: menuplan.MenuPlan # Advice generated by
    keypress: int # The ascii ordinal
    new_menu_plan: menuplan.MenuPlan = None # Advising to set this as the new one

    def __post_init__(self):
        utilities.ACTION_LOOKUP[self.keypress] # check that this exists
        if not (self.keypress >= 0 and self.keypress < 128):
            raise Exception("Invalid ascii ordinal")

@dataclass
class ReplayAdvice(Advice):
    action: int
    is_menu_action: bool
    new_menu_plan: menuplan.MenuPlan = None # Advising to set this as the new one


class BackgroundActionsAdvisor(Advisor): # dummy advisor to hold background menu plans
    def advice(self, rng, run_state, character, oracle):
        pass

class CompositeAdvisor(Advisor):
    def __init__(self, advisors=None, oracle_consultation=None, threat_tolerance=None, threat_threshold=None):
        self.advisors = advisors
        super().__init__(oracle_consultation=oracle_consultation, threat_tolerance=threat_tolerance, threat_threshold=threat_threshold)

class RandomCompositeAdvisor(CompositeAdvisor):
    def advice(self, rng, run_state, character, oracle):
        all_advice = []
        weights = []
        for advisor, weight in self.advisors.items():
            advice = advisor.advice_on_conditions(rng, run_state, character, oracle)
            if advice is not None and advice.action not in run_state.actions_without_consequence:
                all_advice.append(advice)
                weights.append(weight)

        if len(all_advice) > 0:
            return rng.choices(all_advice, weights=weights)[0]

class SequentialCompositeAdvisor(CompositeAdvisor):
    def advice(self, rng, run_state, character, oracle):
        for advisor in self.advisors:
            advice = advisor.advice_on_conditions(rng, run_state, character, oracle)
            if advice is not None and advice.action not in run_state.actions_without_consequence:
                return advice

class PrebakedSequentialCompositeAdvisor(SequentialCompositeAdvisor):
    sequential_advisors = []

    def __init__(self, oracle_consultation=None, threat_tolerance=None, threat_threshold=None):
        advisors = [adv() for adv in self.sequential_advisors]
        super().__init__(advisors, oracle_consultation=oracle_consultation, threat_tolerance=threat_tolerance, threat_threshold=threat_threshold)

class WaitAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        wait = nethack.actions.MiscDirection.WAIT
        return ActionAdvice(from_advisor=self, action=wait)

class SearchWithStethoscope(Advisor):
    def advice(self, rng, run_state, character, oracle):
        stethoscope = character.inventory.get_item(inv.Tool, name='stethoscope')
        if stethoscope is None:
            return None

        low_search_count = run_state.neighborhood.zoom_glyph_alike(
            run_state.neighborhood.level_map.searches_count_map,
            neighborhood.ViewField.Local
        ) < 1000

        searchable = low_search_count & run_state.neighborhood.local_possible_secret_mask
        searchable[run_state.neighborhood.local_player_location] = False
        to_search = np.where(searchable)
        if len(to_search[0]) == 0:
            return None
        direction = run_state.neighborhood.action_grid[(to_search[0][0], to_search[1][0])]
        menu_plan = menuplan.MenuPlan("search with stethoscope", self, [
                menuplan.CharacterMenuResponse("What do you want to use or apply?", chr(stethoscope.inventory_letter)),
                menuplan.DirectionMenuResponse("In what direction?", direction),
            ], listening_item=stethoscope
        )
        #import pdb; pdb.set_trace()
        apply = nethack.actions.Command.APPLY
        return StethoscopeAdvice(from_advisor=self, action=apply, new_menu_plan=menu_plan, direction=direction)

class SearchForSecretDoorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        to_search_count = np.count_nonzero(run_state.neighborhood.local_possible_secret_mask)
        if to_search_count == 0:
            return None
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.SEARCH)

class SearchDeadEndsWithStethoscope(Advisor):
    def advice(self, rng, run_state, character, oracle):
        stethoscope = character.inventory.get_item(inv.Tool, name='stethoscope')
        if stethoscope is None:
            return None

        if not run_state.neighborhood.at_dead_end():
            return None

        low_search_count = run_state.neighborhood.zoom_glyph_alike(
            run_state.neighborhood.level_map.searches_count_map,
            neighborhood.ViewField.Local
        ) < 1000

        searchable = low_search_count & run_state.neighborhood.local_possible_secret_mask
        searchable[run_state.neighborhood.local_player_location] = False
        to_search = np.where(searchable)
        if len(to_search[0]) == 0:
            return None
        direction = run_state.neighborhood.action_grid[(to_search[0][0], to_search[1][0])]
        menu_plan = menuplan.MenuPlan("search with stethoscope", self, [
                menuplan.CharacterMenuResponse("What do you want to use or apply?", chr(stethoscope.inventory_letter)),
                menuplan.DirectionMenuResponse("In what direction?", direction),
            ], listening_item=stethoscope
        )
        apply = nethack.actions.Command.APPLY
        return StethoscopeAdvice(from_advisor=self, action=apply, new_menu_plan=menu_plan, direction=direction)

class SearchDeadEndAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not run_state.neighborhood.at_dead_end():
            return None
        lowest_search_count = run_state.neighborhood.zoom_glyph_alike(
            run_state.neighborhood.level_map.searches_count_map,
            neighborhood.ViewField.Local
        ).min()
        if lowest_search_count > 30:
            return None
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.SEARCH)

class PotionAdvisor(Advisor):
    def make_menu_plan(self, letter):
        menu_plan = menuplan.MenuPlan(
            "drink potion", self, [
                menuplan.CharacterMenuResponse("What do you want to drink?", chr(letter)),
                menuplan.NoMenuResponse("Drink from the fountain?"),
                menuplan.NoMenuResponse("Drink from the sink?"),
            ])
        
        return menu_plan

class DrinkHealingForMaxHPAdvisor(PotionAdvisor):
    def advice(self, rng, run_state, character, oracle):
        quaff = nethack.actions.Command.QUAFF
        healing_potions = character.inventory.get_items(inv.Potion, instance_selector=lambda i: i.BUC != constants.BUC.cursed, identity_selector=lambda i: i.name() is not None and 'healing' in i.name())

        for potion in healing_potions:
            expected_healing = potion.expected_healing(character)
            if expected_healing < (character.max_hp / 2):
                menu_plan = self.make_menu_plan(potion.inventory_letter)
                #import pdb; pdb.set_trace()
                return ActionAdvice(from_advisor=self, action=quaff, new_menu_plan=menu_plan)

        return None

class DrinkGainAbility(PotionAdvisor):
    def advice(self, rng, run_state, character, oracle):
        quaff = nethack.actions.Command.QUAFF
        gain_ability_potion = character.inventory.get_item(inv.Potion, name="gain ability", instance_selector=lambda i: i.BUC != constants.BUC.cursed)
        if gain_ability_potion is None:
            return None
        menu_plan = self.make_menu_plan(gain_ability_potion.inventory_letter)
        return ActionAdvice(from_advisor=self, action=quaff, new_menu_plan=menu_plan)

class DrinkGainLevel(PotionAdvisor):
    def advice(self, rng, run_state, character, oracle):
        quaff = nethack.actions.Command.QUAFF
        gain_level = character.inventory.get_item(inv.Potion, name="gain level", instance_selector=lambda i: i.BUC != constants.BUC.cursed)
        if gain_level is None:
            return None
        menu_plan = self.make_menu_plan(gain_level.inventory_letter)
        return ActionAdvice(from_advisor=self, action=quaff, new_menu_plan=menu_plan)

class DrinkHealingPotionAdvisor(PotionAdvisor):
    def advice(self, rng, run_state, character, oracle):
        quaff = nethack.actions.Command.QUAFF
        healing_potions = character.inventory.get_items(inv.Potion, identity_selector=lambda i: i.name() is not None and 'healing' in i.name())

        for potion in healing_potions:
                letter = potion.inventory_letter
                menu_plan = self.make_menu_plan(letter)
                return ActionAdvice(from_advisor=self, action=quaff, new_menu_plan=menu_plan)
        return None

class DoCombatHealingAdvisor(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [DrinkHealingPotionAdvisor]

class ApplyUnicornHornAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        unicorn_horn = character.inventory.get_item(inv.Tool, identity_selector=lambda i: i.name() == 'unicorn horn', instance_selector=lambda i: i.BUC != constants.BUC.cursed)
        if unicorn_horn is not None:
            apply = nethack.actions.Command.APPLY
            menu_plan = menuplan.MenuPlan("apply unicorn horn", self, [
                menuplan.CharacterMenuResponse("What do you want to use or apply?", chr(unicorn_horn.inventory_letter)),
            ], listening_item=unicorn_horn)
            return ActionAdvice(from_advisor=self, action=apply, new_menu_plan=menu_plan)

class GainSpeedFromWand(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if character.has_intrinsic(constants.Intrinsics.speed):
            return None

        zap = nethack.actions.Command.ZAP
        wand_of_speed_monster = character.inventory.get_item(inv.Wand, identity_selector=lambda i: i.name() == 'speed monster')
        if wand_of_speed_monster is not None and (wand_of_speed_monster.charges is None or wand_of_speed_monster.charges > 0):
            menu_plan = menuplan.MenuPlan("zap speed monster wand", self, [
                menuplan.CharacterMenuResponse("What do you want to zap?", chr(wand_of_speed_monster.inventory_letter)),
                menuplan.CharacterMenuResponse("In what direction?", '.'),
            ], listening_item=wand_of_speed_monster)

            #import pdb; pdb.set_trace()
            return ActionAdvice(from_advisor=self, action=zap, new_menu_plan=menu_plan)

class ZapDiggingDownAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if character.held_by is not None:
            return None

        zap = nethack.actions.Command.ZAP
        wand_of_digging = character.inventory.get_item(inv.Wand, identity_selector=lambda i: i.name() == 'digging')

        if wand_of_digging is not None and (wand_of_digging.charges is None or wand_of_digging.charges > 0):
            menu_plan = menuplan.MenuPlan("zap digging wand", self, [
                menuplan.CharacterMenuResponse("What do you want to zap?", chr(wand_of_digging.inventory_letter)),
                menuplan.CharacterMenuResponse("In what direction?", '>'),
            ], listening_item=wand_of_digging)
            return ActionAdvice(from_advisor=self, action=zap, new_menu_plan=menu_plan)

class ZapTeleportOnSelfAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        zap = nethack.actions.Command.ZAP
        wand_of_teleport = character.inventory.get_item(inv.Wand, identity_selector=lambda i: i.name() == 'teleportation')

        if wand_of_teleport is not None and (wand_of_teleport.charges is None or wand_of_teleport.charges > 0):
            menu_plan = menuplan.MenuPlan("zap teleportation wand", self, [
                menuplan.CharacterMenuResponse("What do you want to zap?", chr(wand_of_teleport.inventory_letter)),
                menuplan.DirectionMenuResponse("In what direction?", run_state.neighborhood.action_grid[run_state.neighborhood.local_player_location]),
            ], listening_item=wand_of_teleport)
            return ActionAdvice(from_advisor=self, action=zap, new_menu_plan=menu_plan)

class ReadTeleportAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        scrolls = character.inventory.get_oclass(inv.Scroll)

        for scroll in scrolls:
            if scroll and scroll.identity and scroll.identity.name() == 'teleport':
                letter = scroll.inventory_letter
                menu_plan = menuplan.MenuPlan("read teleport scroll", self, [
                    menuplan.CharacterMenuResponse("What do you want to read?", chr(letter)),
                    menuplan.YesMenuResponse("Do you wish to teleport?"),
                ])
                return ActionAdvice(from_advisor=self, action=read, new_menu_plan=menu_plan)
        return None

class UseEscapeItemAdvisor(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [ZapDiggingDownAdvisor, ZapTeleportOnSelfAdvisor, ReadTeleportAdvisor]

class ReadRemoveCurse(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        remove_curse = character.inventory.get_item(inv.Scroll, instance_selector=lambda i: i.BUC != constants.BUC.cursed, identity_selector=lambda i: i.name() == 'remove curse')
        if remove_curse is None:
            return None

        armaments = character.inventory.armaments
        have_cursed = False
        for item in armaments:
            if item is not None and item.BUC == constants.BUC.cursed:
                have_cursed = True
                break

        if not have_cursed:
            return None

        letter = remove_curse.inventory_letter
        menu_plan = menuplan.MenuPlan("read remove curse scroll", self, [
            menuplan.CharacterMenuResponse("What do you want to read?", chr(letter)),
        ])
        #import pdb; pdb.set_trace()
        return ActionAdvice(from_advisor=self, action=read, new_menu_plan=menu_plan)

class IdentifyUnidentifiedScrolls(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        identify_scroll = character.inventory.get_item(inv.Scroll, name="identify", instance_selector=lambda i: not i.shop_owned)

        if identify_scroll is None:
            return None

        unidentified_scrolls = character.inventory.get_item(
            inv.Scroll,
            identity_selector=lambda i: i.name() is None
        )

        if unidentified_scrolls is None:
            return None

        print("Trying to identify")

        menu_plan = menuplan.MenuPlan("identify boilerplate", self, [
            menuplan.CharacterMenuResponse("What do you want to read?", chr(identify_scroll.inventory_letter)),
            menuplan.MoreMenuResponse("As you read the scroll, it disappears."),
        ], interactive_menu=menuplan.InteractiveIdentifyMenu(run_state, character.inventory, desired_letter=chr(unidentified_scrolls.inventory_letter)))

        return ActionAdvice(self, read, menu_plan)

class IdentifyPotentiallyMagicArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        identify_scroll = character.inventory.get_item(inv.Scroll, name="identify", instance_selector=lambda i: not i.shop_owned)

        if identify_scroll is None:
            return None

        unidentified_magic_armor = character.inventory.get_item(
            inv.Armor,
            identity_selector=lambda i: i.name() is None and i.potentially_magic()
        )

        if unidentified_magic_armor is None:
            return None

        print("Trying to identify")

        menu_plan = menuplan.MenuPlan("identify boilerplate", self, [
            menuplan.CharacterMenuResponse("What do you want to read?", chr(identify_scroll.inventory_letter)),
            menuplan.MoreMenuResponse("As you read the scroll, it disappears."),
        ], interactive_menu=menuplan.InteractiveIdentifyMenu(run_state, character.inventory, desired_letter=chr(unidentified_magic_armor.inventory_letter)))

        return ActionAdvice(self, read, menu_plan)

class AnyScrollAdvisor(Advisor):
    def make_menu_plan(self, run_state, character, scroll):
        interactive_menus = [
            menuplan.InteractiveIdentifyMenu(run_state, character.inventory), # identifies first choice since we don't specify anything
        ]

        menu_plan = menuplan.MenuPlan("read unidentified scroll", self, [
                menuplan.CharacterMenuResponse("What do you want to read?", chr(scroll.inventory_letter)),
                menuplan.PhraseMenuResponse("What monster do you want to genocide?", "fire ant"),
                menuplan.EscapeMenuResponse("Where do you want to center the stinking cloud"),
                menuplan.MoreMenuResponse(re.compile("Where do you want to center the explosion\?$")),
                # most remote square for placements
                menuplan.ConnectedSequenceMenuResponse("(For instructions type a '?')", "Z."),
                menuplan.ConnectedSequenceMenuResponse("What class of monsters do you wish to genocide?", "a\r"),
                menuplan.MoreMenuResponse("As you read the scroll, it disappears.", always_necessary=False),
                menuplan.MoreMenuResponse("This is a scroll of"),
                menuplan.MoreMenuResponse(re.compile("This is a (.+) scroll")),
                menuplan.MoreMenuResponse("You have found a scroll of"),
                menuplan.EscapeMenuResponse("What do you want to charge?"),
                menuplan.NoMenuResponse("Do you wish to teleport?"),
            ], interactive_menu=interactive_menus, listening_item=scroll
        )

        return menu_plan

class ReadSafeUnidentifiedScrolls(AnyScrollAdvisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        safe_scroll = character.inventory.get_item(inv.Scroll, instance_selector=lambda i: i.safe_to_read(character), identity_selector=lambda i:not i.is_identified() and not i.listened_actions.get(read, False))

        if safe_scroll is not None:
            menu_plan = self.make_menu_plan(run_state, character, safe_scroll)
            #import pdb; pdb.set_trace()
            return ActionAdvice(self, read, menu_plan)

class ReadUnidentifiedScrollsAdvisor(AnyScrollAdvisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        scrolls = character.inventory.get_oclass(inv.Scroll)

        for scroll in scrolls:
            if scroll and scroll.identity and not scroll.identity.is_identified() and scroll.BUC != constants.BUC.cursed:
                menu_plan = self.make_menu_plan(run_state, character, scroll)
                return ActionAdvice(self, read, menu_plan)

class EnchantArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ

        enchant_armor_scroll = character.inventory.get_item(inv.Scroll, name='enchant armor', instance_selector=lambda i: i.BUC != constants.BUC.cursed)

        if enchant_armor_scroll is not None:
            armaments = character.inventory.get_slots('armaments')

            for item in armaments:
                if isinstance(item, inv.Armor):
                    if item.enhancement is not None and item.enhancement > 3: # don't enchant if it could implode an item
                        return None
            
            menu_plan = menuplan.MenuPlan("read enchant armor", self, [
                menuplan.CharacterMenuResponse("What do you want to read?", chr(enchant_armor_scroll.inventory_letter))
            ])
            return ActionAdvice(self, read, menu_plan)

class EnchantWeaponAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ

        enchant_weapon_scroll = character.inventory.get_item(inv.Scroll, name='enchant weapon', instance_selector=lambda i: i.BUC != constants.BUC.cursed)

        if enchant_weapon_scroll is not None:
            wielded_weapon = character.inventory.wielded_weapon
            if isinstance(wielded_weapon, inv.BareHands) or (wielded_weapon.enhancement is not None and wielded_weapon.enhancement > 5):
                return None
            
            menu_plan = menuplan.MenuPlan("read enchant weapon", self, [
                menuplan.CharacterMenuResponse("What do you want to read?", chr(enchant_weapon_scroll.inventory_letter))
            ])
            return ActionAdvice(self, read, menu_plan)

class ReadKnownBeneficialScrolls(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [EnchantArmorAdvisor, EnchantWeaponAdvisor]


class EnhanceSkillsAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not run_state.character.can_enhance:
            return None

        enhance = nethack.actions.Command.ENHANCE
        menu_plan = menuplan.MenuPlan(
            "enhance skills",
            self,
            [
                menuplan.NoMenuResponse("Advance skills without practice?"),
            ],
            interactive_menu=menuplan.InteractiveEnhanceSkillsMenu(),
        )

        return ActionAdvice(from_advisor=self, action=enhance, new_menu_plan=menu_plan)

class EatCorpseAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if run_state.neighborhood.in_shop:
            return None

        if run_state.neighborhood.fresh_corpse_on_square_glyph is None:
            return None

        if not run_state.neighborhood.fresh_corpse_on_square_glyph.safe_to_eat(character):
            return None

        if oracle.am_satiated:
            return None

        eat = nethack.actions.Command.EAT

        menu_plan = menuplan.MenuPlan(
            "eat corpse on square", self,
            [
                menuplan.YesMenuResponse(f" {run_state.neighborhood.fresh_corpse_on_square_glyph.name} corpse here; eat"),
                menuplan.YesMenuResponse(f" {run_state.neighborhood.fresh_corpse_on_square_glyph.name} corpses here; eat"),
                menuplan.NoMenuResponse("here; eat"),
                menuplan.EscapeMenuResponse("want to eat?"),
                menuplan.MoreMenuResponse("You're having a hard time getting all of it down."),
                #menuplan.MoreMenuResponse("You resume your meal"),
                menuplan.NoMenuResponse("Continue eating"),
            ])

        return ActionAdvice(from_advisor=self, action=eat, new_menu_plan=menu_plan)

class InventoryEatAdvisor(Advisor):
    def make_menu_plan(self, letter):
        menu_plan = menuplan.MenuPlan("eat from inventory", self, [
            menuplan.NoMenuResponse("here; eat"),
            menuplan.CharacterMenuResponse("want to eat?", chr(letter)),
            menuplan.MoreMenuResponse("You succeed in opening the tin."),
            menuplan.MoreMenuResponse("Using your tin opener you try to open the tin"),
            menuplan.MoreMenuResponse("smells like"),
            menuplan.MoreMenuResponse("It contains"),
            menuplan.YesMenuResponse("Eat it?"),
            menuplan.MoreMenuResponse("You're having a hard time getting all of it down."),
            menuplan.NoMenuResponse("Continue eating"),
        ])
        return menu_plan

    def check_comestible(self, comestible, rng, run_state, character, oracle):
        if comestible.identity is None:
            return True

        return comestible.identity.safe_non_perishable(character)

    def advice(self, rng, run_state, character, oracle):
        eat = nethack.actions.Command.EAT
        food = character.inventory.get_oclass(inv.Food)

        for comestible in food:
            if comestible and self.check_comestible(comestible, rng, run_state, character, oracle):
                letter = comestible.inventory_letter
                menu_plan = self.make_menu_plan(letter)
                return ActionAdvice(from_advisor=self, action=eat, new_menu_plan=menu_plan)
        return None

class CombatEatAdvisor(InventoryEatAdvisor):
    def check_comestible(self, comestible, rng, run_state, character, oracle):
        if not super().check_comestible(comestible, rng, run_state, character, oracle):
            return False
        if comestible.identity: # if statement = bandaid for lack of corpse identities
            return comestible.identity and comestible.identity.name() != 'tin'
        else:
            return True

class PrayerAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if character.last_pray_time is None and run_state.blstats.get('time') <= 300:
            return None
        if character.last_pray_time is not None and (run_state.blstats.get('time') - character.last_pray_time) < 250:
            return None
        pray = nethack.actions.Command.PRAY
        menu_plan = menuplan.MenuPlan("yes pray", self, [
            menuplan.YesMenuResponse("Are you sure you want to pray?")
        ])
        return ActionAdvice(from_advisor=self, action=pray, new_menu_plan=menu_plan)

class PrayForUrgentMajorTroubleAdvisor(PrayerAdvisor):
    pass

class PrayForHPAdvisor(PrayerAdvisor):
    pass

class PrayForNutritionAdvisor(PrayerAdvisor):
    pass

class PrayForLesserMajorTroubleAdvisor(PrayerAdvisor):
    pass

###################
# ATTACK ADVISORS #
###################

class Attack(Advisor):
    def advice(self, rng, run_state, character, oracle):
        targets = self.targets(run_state.neighborhood, character)
        if targets is None:
            return None

        attack_direction = self.prioritize(targets, character)

        if attack_direction is None:
            return None
        return ActionAdvice(from_advisor=self, action=attack_direction)

    def targets(self, neighborhood, character):
        return neighborhood.target_monsters(lambda m: True)

    def prioritize(self, targets, character):
        return targets.directions[0]

class MeleeHoldingMonster(Attack):
    def prioritize(self, targets, character):
        return targets.directions[0]

    def targets(self, neighborhood, character):
        if character.held_by is None:
            return None

        targets = neighborhood.target_monsters(lambda m: m == character.held_by.monster_glyph)
        return targets

class MeleePriorityTargets(Attack):
    def targets(self, neighborhood, character):
        return neighborhood.target_monsters(lambda m: isinstance(m, gd.MonsterGlyph) and character.melee_prioritize_monster_beyond_damage(m.monster_spoiler))

class RangedAttackAdvisor(Attack):
    attack_strength = 'ordinary'
    def prepare_for_ranged(self, character):
        ranged_plan = character.inventory.get_ordinary_ranged_attack(character)
        if ranged_plan is None or ranged_plan.attack_plan is not None:
            return None

        if ranged_plan.quiver_item is not None:
            action = nethack.actions.Command.QUIVER
            menu_plan = menuplan.MenuPlan("quiver for ranged", self, [
                menuplan.CharacterMenuResponse("What do you want to ready?", chr(ranged_plan.quiver_item.inventory_letter)),
                menuplan.YesMenuResponse("Ready it instead?"),
                menuplan.NoMenuResponse(re.compile(" Ready [0-9]+ of them\?")),
                menuplan.YesMenuResponse("Ready all of them instead?"),
            ])
        if ranged_plan.wield_item is not None:
            action = nethack.actions.Command.WIELD
            character.executing_ranged_plan = self
            menu_plan = menuplan.MenuPlan("wield weapon for ranged", self, [
                menuplan.CharacterMenuResponse("What do you want to wield?", chr(ranged_plan.wield_item.inventory_letter)),
                ],
            )
        #import pdb; pdb.set_trace()
        return ActionAdvice(from_advisor=self, action=action, new_menu_plan=menu_plan)

    def make_throw_plan(self, item, direction):
        menu_plan = menuplan.MenuPlan("throw attack", self, [
            menuplan.CharacterMenuResponse("What do you want to throw?", chr(item.inventory_letter)),
            menuplan.DirectionMenuResponse("In what direction?", direction),
        ], listening_item=item)
        return menu_plan

    def make_fire_plan(self, quivered, direction):
        menu_plan = menuplan.MenuPlan("fire ranged attack", self, [
            menuplan.DirectionMenuResponse("In what direction?", direction),
        ], listening_item=quivered)
        return menu_plan

    def make_zap_plan(self, item, direction):
        menu_plan = menuplan.MenuPlan("zap ranged attack wand", self, [
            menuplan.CharacterMenuResponse("What do you want to zap?", chr(item.inventory_letter)),
            menuplan.DirectionMenuResponse("In what direction?", direction),
        ],)
        return menu_plan

    def advice(self, rng, run_state, character, oracle):
        targets = self.targets(run_state.neighborhood, character)
        if targets is None:
            return None
        attack_direction = self.prioritize(targets, character)
        if attack_direction is None:
            return None
        ranged_preparation = self.prepare_for_ranged(character)
        if ranged_preparation is not None:
            return ranged_preparation
        if self.attack_strength == 'ordinary':
            ranged_plan = character.inventory.get_ordinary_ranged_attack(character)
        elif self.attack_strength == 'powerful':
            ranged_plan = character.inventory.get_powerful_ranged_attack(character)
        if ranged_plan is None:
            return None
        attack_plan = ranged_plan.attack_plan
        if attack_plan is None:
            return None

        if attack_plan.attack_action == nethack.actions.Command.THROW:
            menu_plan = self.make_throw_plan(attack_plan.attack_item, attack_direction)
        elif attack_plan.attack_action == nethack.actions.Command.FIRE:
            menu_plan = self.make_fire_plan(character.inventory.quivered, attack_direction)
        elif attack_plan.attack_action == nethack.actions.Command.ZAP:
            menu_plan = self.make_zap_plan(attack_plan.attack_item, attack_direction)
        else:
            assert False
        return ActionAdvice(from_advisor=self, action=attack_plan.attack_action, new_menu_plan=menu_plan)

class RangedAttackNuisanceMonsters(RangedAttackAdvisor):
    attack_strength = 'powerful'
    def advice(self, rng, run_state, character, oracle):
        advice = super().advice(rng, run_state, character, oracle)
        if advice is not None:
            pass
            #import pdb; pdb.set_trace()
        return advice
    def targets(self, neighborhood, character):
        range = physics.AttackRange('line', 4)
        targets = neighborhood.target_monsters(lambda m: character.scared_by(m), attack_range=range)
        if targets is not None:
            print(f"Annoying monster at range: {targets.monsters[0]}")
        return targets

class TameCarnivores(RangedAttackAdvisor):
    def targets(self, neighborhood, character):
        range = physics.AttackRange('line', 3)
        return neighborhood.target_monsters(lambda m: isinstance(m, gd.MonsterGlyph) and m.monster_spoiler.tamed_by_meat and (m.monster_spoiler.level + 3) > character.experience_level)

    def advice(self, rng, run_state, character, oracle):
        targets = self.targets(run_state.neighborhood, character)
        if targets is None:
            return None
        #import pdb; pdb.set_trace()
        attack_direction = self.prioritize(targets, character)
        if attack_direction is None:
            return None
        food = character.inventory.get_item(inv.Food, identity_selector=lambda i: i.taming_food_type == 'meat')
        if food is None:
            return None

        menu_plan = self.make_throw_plan(food, attack_direction)
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.THROW, new_menu_plan=menu_plan)

class TameHerbivores(RangedAttackAdvisor):
    def targets(self, neighborhood, character):
        range = physics.AttackRange('line', 3)
        return neighborhood.target_monsters(lambda m: isinstance(m, gd.MonsterGlyph) and m.monster_spoiler.tamed_by_veg and (m.monster_spoiler.level + 3) > character.experience_level)

    def advice(self, rng, run_state, character, oracle):
        targets = self.targets(run_state.neighborhood, character)
        if targets is None:
            return None
        #import pdb; pdb.set_trace()
        attack_direction = self.prioritize(targets, character)
        if attack_direction is None:
            return None
        food = character.inventory.get_item(inv.Food, identity_selector=lambda i: i.taming_food_type == 'veg')
        if food is None:
            return None

        menu_plan = self.make_throw_plan(food, attack_direction)
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.THROW, new_menu_plan=menu_plan)

class RangedAttackHighlyThreateningMonsters(RangedAttackAdvisor):
    unsafe_hp_loss_fraction = 0.5
    def advice(self, rng, run_state, character, oracle):
        advice = super().advice(rng, run_state, character, oracle)
        if advice is not None:
            print("Attacking highly threatening monster at range")
            #import pdb; pdb.set_trace()
        return advice
    def targets(self, neighborhood, character):
        range = physics.AttackRange('line', 4)
        def target_p(monster):
            if not isinstance(monster, gd.MonsterGlyph):
                return False
            spoiler = monster.monster_spoiler
            damage_from_attacks, trajectory = spoiler.fight_outcome(character)
            if damage_from_attacks + spoiler.passive_damage_over_encounter(character, trajectory) + spoiler.death_damage_over_encounter(character) > self.unsafe_hp_loss_fraction * character.current_hp:
                #print(f"Highly threatening monster at range: {monster}")
                return True
            return False
        return neighborhood.target_monsters(lambda m: target_p(m), attack_range=range)

class PassiveMonsterRangedAttackAdvisor(RangedAttackAdvisor):
    def targets(self, neighborhood, character):
        range = physics.AttackRange('line', 4)
        return neighborhood.target_monsters(lambda m: isinstance(m, gd.MonsterGlyph) and m.monster_spoiler.passive_attack_bundle.num_attacks > 0, attack_range=range)

    def prioritize(self, targets, character):
        monsters = targets.monsters
        max_damage = 0
        target_index = None
        # prioritize by maximum passive damage
        for i,m in enumerate(monsters):
            damage = m.monster_spoiler.passive_attack_bundle.expected_damage

            if target_index is None or damage > max_damage:
                target_index = i
                max_damage = damage

        return targets.directions[target_index]

class AdjustRangedPlanDummy(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not character.executing_ranged_plan:
            return None

        ranged_advisor = character.executing_ranged_plan
        targets = ranged_advisor.targets(run_state.neighborhood, character)
        if targets is None:
            character.executing_ranged_plan = False

        return None

class LowerDPSAttack(Attack):
    def prioritize(self, targets, character):
        monsters = targets.monsters
        if len(monsters) == 1:
            return targets.directions[0]
        target_index = None
        best_reduction_rate = 0
        for i, m in enumerate(monsters):
            # prioritize invisible / swallow / whatever immediately as a patch
            if not isinstance(m, gd.MonsterGlyph):
                target_index = i
                break
            untargeted_dps = m.monster_spoiler.melee_dps(character.AC)
            kill_trajectory = character.average_time_to_kill_monster_in_melee(m.monster_spoiler)

            dps_reduction_rate = untargeted_dps/kill_trajectory.time_to_kill

            if target_index is None or dps_reduction_rate > best_reduction_rate:
                target_index = i
                best_reduction_rate = dps_reduction_rate

        return targets.directions[target_index]

class UnsafeMeleeAttackAdvisor(LowerDPSAttack):
    pass

class SafeMeleeAttackAdvisor(LowerDPSAttack):
    unsafe_hp_loss_fraction = 0.5

    def targets(self, neighborhood, character):
        def target_p(monster):
            if not isinstance(monster, gd.MonsterGlyph):
                return True
            spoiler = monster.monster_spoiler
            trajectory = character.average_time_to_kill_monster_in_melee(spoiler)
            if spoiler and spoiler.passive_damage_over_encounter(character, trajectory) + spoiler.death_damage_over_encounter(character) > self.unsafe_hp_loss_fraction * character.current_hp:
                return False
            return True

        return neighborhood.target_monsters(target_p)

class MoveAdvisor(Advisor):
    def __init__(self, oracle_consultation=None, no_adjacent_monsters=False, square_threat_tolerance=None):
        self.square_threat_tolerance = square_threat_tolerance
        super().__init__(oracle_consultation=oracle_consultation, no_adjacent_monsters=no_adjacent_monsters)

    def would_move_squares(self, rng, run_state, character, oracle):
        move_mask  = run_state.neighborhood.walkable
        # don't move into intolerable threat
        if self.square_threat_tolerance is not None:
            return move_mask & (run_state.neighborhood.threat <= (self.square_threat_tolerance * character.current_hp))
        return move_mask

    def advice(self, rng, run_state, character, oracle):
        move_mask = self.would_move_squares(rng, run_state, character, oracle)
        move_action = self.get_move(move_mask, rng, run_state, character, oracle)

        if move_action is not None:
            return ActionAdvice(from_advisor=self, action=move_action)

class MoveToBetterSearchAdvisor(MoveAdvisor):
    def get_move(self, move_mask, rng, run_state, character, oracle):
        search_adjacencies = run_state.neighborhood.count_adjacent_searches(SEARCH_THRESHOLD)
        if search_adjacencies[run_state.neighborhood.local_player_location] != 1:
            return # If zero, no idea where to go. If 2+ this is a good place to search
        priority_mask = (search_adjacencies > 1) & move_mask
        possible_actions = run_state.neighborhood.action_grid[priority_mask]
        if possible_actions.any():
            return rng.choice(possible_actions)

class RandomMoveAdvisor(MoveAdvisor):
    def get_move(self, move_mask, rng, run_state, character, oracle):
        possible_actions = run_state.neighborhood.action_grid[move_mask]

        if possible_actions.any():
            return rng.choice(possible_actions)

class MostNovelMoveAdvisor(MoveAdvisor):
    def get_move(self, move_mask, rng, run_state, character, oracle):
        visits = run_state.neighborhood.visits[move_mask]

        possible_actions = run_state.neighborhood.action_grid[move_mask]

        if possible_actions.any():
            most_novel = possible_actions[visits == visits.min()]

            return rng.choice(most_novel)

class ReduceThreatFromManyEnemiesWithMove(MoveAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if not oracle.adjacent_monsters > 1:
            return None
        return super().advice(rng, run_state, character, oracle)

    def get_move(self, move_mask, rng, run_state, character, oracle):
        possible_actions = run_state.neighborhood.action_grid[move_mask]

        if not possible_actions.any():
            return None

        threat = run_state.neighborhood.threat[move_mask]
        current_threat = run_state.neighborhood.threat_on_player
        cost = threat - current_threat

        if (cost < 0).any():
            idx = np.argmin(cost)
        else:
            return None

        desired_action = possible_actions[idx]
        #import pdb; pdb.set_trace()
        return desired_action

class UnvisitedSquareMoveAdvisor(MoveAdvisor):
    def get_move(self, move_mask, rng, run_state, character, oracle):
        visits = run_state.neighborhood.visits[move_mask]

        possible_actions = run_state.neighborhood.action_grid[move_mask]

        if possible_actions.any():
            unvisited = possible_actions[visits == 0]

            if unvisited.any():
                return rng.choice(unvisited)

class PathAdvisor(Advisor):
    def __init__(self, oracle_consultation=None, no_adjacent_monsters=True, path_threat_tolerance=None):
        super().__init__(oracle_consultation=oracle_consultation, no_adjacent_monsters=no_adjacent_monsters)
        self.path_threat_tolerance = path_threat_tolerance

    @abc.abstractmethod
    def find_path(self, rng, run_state, character, oracle):
        pass

    def advice(self, rng, run_state, character, oracle):
        path = self.find_path(rng, run_state, character, oracle)

        if path is not None:
            if self.path_threat_tolerance is not None and path.threat > (self.path_threat_tolerance * character.current_hp):
                return None

            return ActionAdvice(from_advisor=self, action=path.path_action)

class ExcaliburAdvisor(Advisor):
    pass

class TravelToAltarAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        any_unknown = character.inventory.get_item(instance_selector=lambda i: (i.BUC == constants.BUC.unknown and (i.equipped_status is None or i.equipped_status.status != 'worn')))
        if any_unknown is None:
            return None

        travel = nethack.actions.Command.TRAVEL
        menu_plan = menuplan.MenuPlan(
            "travel down", self, [
                menuplan.CharacterMenuResponse("Where do you want to travel to?", '_'),
                menuplan.EscapeMenuResponse("Can't find dungeon feature"),
            ],
            fallback=ord('.')
        )
        return ActionAdvice(from_advisor=self, action=travel, new_menu_plan=menu_plan)

class DropUnknownOnAltarAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not (run_state.neighborhood.dungeon_glyph_on_player and run_state.neighborhood.dungeon_glyph_on_player.is_altar):
            return None

        any_unknown = character.inventory.get_item(instance_selector=lambda i: (i.BUC == constants.BUC.unknown and (i.equipped_status is None or i.equipped_status.status != 'worn')))
        if any_unknown is None:
            return None

        menu_plan = menuplan.MenuPlan(
            "drop all undesirable objects",
            self,
            [
                menuplan.NoMenuResponse("Sell it?"),
                menuplan.MoreMenuResponse("You drop", always_necessary=False),
                menuplan.ConnectedSequenceMenuResponse("What would you like to drop?", ".")
            ],
            interactive_menu=[
                menuplan.InteractiveDropTypeChooseTypeMenu(selector_name='unknown BUC'),
            ]
        )
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.DROPTYPE, new_menu_plan=menu_plan)

class DipForExcaliburAdvisor(ExcaliburAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if not (character.hankering_for_excalibur() and run_state.neighborhood.dungeon_glyph_on_player and run_state.neighborhood.dungeon_glyph_on_player.is_fountain):
            return None
        dip = nethack.actions.Command.DIP
        long_sword = character.inventory.wielded_weapon
        menu_plan = menuplan.MenuPlan(
            "dip long sword", self, [
                menuplan.CharacterMenuResponse("What do you want to dip?", chr(long_sword.inventory_letter)),
                menuplan.YesMenuResponse("into the fountain?"),
            ],
        )
        #import pdb; pdb.set_trace()
        return ActionAdvice(from_advisor=self, action=dip, new_menu_plan=menu_plan)

class TravelToFountainAdvisorForExcalibur(ExcaliburAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if not character.hankering_for_excalibur():
            return None

        travel = nethack.actions.Command.TRAVEL
        lmap = run_state.neighborhood.level_map

        fountains = np.transpose(np.where(lmap.fountain_map))

        if len(fountains > 0):
            nearest_square_idx = np.argmin(np.sum(np.abs(fountains - np.array(run_state.neighborhood.absolute_player_location)), axis=1))
            target_square = physics.Square(*fountains[nearest_square_idx])
            menu_plan = menuplan.MenuPlan(
                "travel to fountain", self, [
                    menuplan.TravelNavigationMenuResponse(re.compile(".*"), run_state.tty_cursor, target_square),
                ],
                fallback=ord('.')
            )
            #import pdb; pdb.set_trace()
            return ActionAdvice(from_advisor=self, action=travel, new_menu_plan=menu_plan)

class TravelToDesiredEgress(Advisor):
    def advice(self, rng, run_state, character, oracle):
        travel = nethack.actions.Command.TRAVEL
        lmap = run_state.neighborhood.level_map

        heading = run_state.dmap.dungeon_direction_to_best_target(lmap.dcoord)

        if heading.direction == map.DirectionThroughDungeon.flat:
            return None

        for location, staircase in lmap.staircases.items():
            if staircase.matches_heading(heading):
                menu_plan = menuplan.MenuPlan(
                    "travel to unexplored", self, [
                        menuplan.TravelNavigationMenuResponse(re.compile(".*"), run_state.tty_cursor, neighborhood.Square(*location)),
                    ],
                    fallback=ord('.'))

                return ActionAdvice(self, travel, menu_plan)

        if environment.env.debug and heading.direction == map.DirectionThroughDungeon.flat:
            import pdb; pdb.set_trace()

        target_symbol = "<" if heading.direction == map.DirectionThroughDungeon.up else ">"
        menu_plan = menuplan.MenuPlan(
            "travel down", self, [
                menuplan.CharacterMenuResponse("Where do you want to travel to?", target_symbol),
                menuplan.EscapeMenuResponse("Can't find dungeon feature"),
            ],
            fallback=ord('.')
        )
        return ActionAdvice(from_advisor=self, action=travel, new_menu_plan=menu_plan)

class TravelToBespokeUnexploredAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        travel = nethack.actions.Command.TRAVEL
        lmap = run_state.neighborhood.level_map

        desirable_unvisited = np.transpose(np.where(
            (lmap.frontier_squares) &
            (~lmap.exhausted_travel_map)
        ))

        if len(desirable_unvisited) > 0:
            nearest_square_idx = np.argmin(np.sum(np.abs(desirable_unvisited - np.array(run_state.neighborhood.absolute_player_location)), axis=1))
            self.target_square = physics.Square(*desirable_unvisited[nearest_square_idx])
            if lmap.visits_count_map[self.target_square] != 0:
                import pdb; pdb.set_trace()
            self.lmap = lmap
            menu_plan = menuplan.MenuPlan(
                "travel to unexplored", self, [
                    menuplan.TravelNavigationMenuResponse(re.compile(".*"), run_state.tty_cursor, self.target_square), # offset because cursor row 0 = top line
                ],
                fallback=ord('.')) # fallback seems broken if you ever ESC out? check TK

            #print(f"initial location = {run_state.neighborhood.absolute_player_location} travel target = {target_square}")
            return ActionAdvice(self, travel, menu_plan)

    def advice_selected(self):
        self.lmap.travel_attempt_count_map[self.target_square] += 1
        if self.lmap.travel_attempt_count_map[self.target_square] > 5:
            self.lmap.exhausted_travel_map[self.target_square] = True


class TravelToUnexploredSquareAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not run_state.neighborhood.level_map.need_egress():
            return None

        travel = nethack.actions.Command.TRAVEL

        menu_plan = menuplan.MenuPlan(
            "travel to unexplored", self, [
                menuplan.CharacterMenuResponse("Where do you want to travel to?", "x"),
            ],
            fallback=ord('.')
        )

        return ActionAdvice(from_advisor=self, action=travel, new_menu_plan=menu_plan)  

class TakeStaircaseAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not (oracle.can_move and oracle.on_stairs):
            return None
        
        current_level = run_state.neighborhood.level_map.dcoord
        traversed_staircase = run_state.neighborhood.level_map.staircases.get(run_state.neighborhood.absolute_player_location, None)
        heading = run_state.dmap.dungeon_direction_to_best_target(current_level)

        if traversed_staircase is not None:
            if traversed_staircase.matches_heading(heading):
                action = nethack.actions.MiscDirection.DOWN if oracle.on_downstairs else nethack.actions.MiscDirection.UP
            else:
                return None
        if traversed_staircase is None:
            if oracle.on_upstairs:
                if current_level == map.DCoord(map.Branches.DungeonsOfDoom.value, 1):
                    return None
                action = nethack.actions.MiscDirection.UP
            elif oracle.on_downstairs:
                action = nethack.actions.MiscDirection.DOWN
            else:
                import pdb; pdb.set_trace()
                assert False, "on stairs but not on up or downstairs"

        return ActionAdvice(from_advisor=self, action=action)

class OpenClosedDoorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        # don't open diagonally so we can be better about warning engravings
        door_mask = ~run_state.neighborhood.diagonal_moves & utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_closed_door, run_state.neighborhood.glyphs)
        door_directions = run_state.neighborhood.action_grid[door_mask]
        if len(door_directions > 0):
            a = rng.choice(door_directions)
            return ActionAdvice(from_advisor=self, action=a)
        else:
            return None

class KickLockedDoorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        # don't kick outside dungeons of doom
        if oracle.blstats.get('dungeon_number') != 0:
            return None
        if oracle.on_warning_engraving:
            return None
        if not "This door is locked" in oracle.message.message:
            return None
        kick = nethack.actions.Command.KICK
        door_mask = ~run_state.neighborhood.diagonal_moves & utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_closed_door, run_state.neighborhood.glyphs)
        door_directions = run_state.neighborhood.action_grid[door_mask]
        if len(door_directions) > 0:
            a = rng.choice(door_directions)
        else: # we got the locked door message but didn't find a door
            a = None
        if a is not None:
            menu_plan = menuplan.MenuPlan("kick locked door", self, [
                menuplan.DirectionMenuResponse("In what direction?", a),
            ])
            return ActionAdvice(from_advisor=self, action=kick, new_menu_plan=menu_plan)

class DropToPriceIDAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not oracle.in_shop:
            return None

        doors = gd.CMapGlyph.is_door_check(run_state.neighborhood.raw_glyphs - gd.CMapGlyph.OFFSET)
        if np.count_nonzero(doors) > 0:
            # don't drop if on the first square of the shop next to the door
            return None

        unidentified_items = character.inventory.all_unidentified_items()
        unidentified_items = [i for i in unidentified_items if not i.identity.listened_price_id_methods.get('sell', False)]
        unidentified_items = [i for i in unidentified_items if i.equipped_status is None or i.equipped_status.status != 'worn']
        if len(unidentified_items) == 0:
            return None

        unidentified_letters = [i.inventory_letter for i in unidentified_items]
        menu_plan = menuplan.MenuPlan(
            "drop all objects to price id",
            self,
            [
                menuplan.NoMenuResponse("Sell it?"),
                menuplan.NoMenuResponse("Sell them?"),
                menuplan.MoreMenuResponse("You drop", always_necessary=False),
                menuplan.MoreMenuResponse("seems uninterested", always_necessary=False),
                menuplan.MoreMenuResponse(re.compile("(y|Y)ou sold .+ for"), always_necessary=False),
            ],
            interactive_menu=[
                menuplan.InteractiveDropTypeChooseTypeMenu(selector_name='all types'),
                menuplan.InteractiveDropTypeMenu(run_state, character.inventory, desired_letter=unidentified_letters),
            ]
        )
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.DROPTYPE, new_menu_plan=menu_plan)

class DropUndesirableAdvisor(Advisor):
    def drop_undesirable(self, run_state, character):
        undesirable_items = character.inventory.all_undesirable_items(character)
        undesirable_items = [item for item in undesirable_items if item.equipped_status is None or item.equipped_status.status != 'worn']
        if len(undesirable_items) == 0:
            return None

        undesirable_letters = [item.inventory_letter for item in undesirable_items]

        menu_plan = menuplan.MenuPlan(
            "drop all undesirable objects",
            self,
            [
                menuplan.YesMenuResponse("Sell it?"),
                menuplan.YesMenuResponse("Sell them?"),
                menuplan.MoreMenuResponse("You drop", always_necessary=False),
                menuplan.MoreMenuResponse("seems uninterested", always_necessary=False),
                menuplan.MoreMenuResponse(re.compile("(y|Y)ou sold .+ for"), always_necessary=False),
            ],
            interactive_menu=[
                menuplan.InteractiveDropTypeChooseTypeMenu(selector_name='all types'),
                menuplan.InteractiveDropTypeMenu(run_state, character.inventory, desired_letter=undesirable_letters)
            ]
        )
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.DROPTYPE, new_menu_plan=menu_plan)

class DropUndesirableInShopAdvisor(DropUndesirableAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if not oracle.in_shop:
            return None
        doors = gd.CMapGlyph.is_door_check(run_state.neighborhood.raw_glyphs - gd.CMapGlyph.OFFSET)
        if np.count_nonzero(doors) > 0:
            # don't drop if on the first square of the shop next to the door
            return None

        return self.drop_undesirable(run_state, character)

class DropUndesirableWantToLowerWeight(DropUndesirableAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if not character.want_less_weight():
            return None

        #import pdb; pdb.set_trace()
        return self.drop_undesirable(run_state, character)

class BuyDesirableAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not oracle.in_shop:
            return None
        shop_owned = [i for i in character.inventory.all_items() if i.shop_owned]

        if len(shop_owned) == 0:
            return None

        pay = nethack.actions.Command.PAY

        menu_plan = menuplan.MenuPlan(
            "buy items",
            self,
            [
                menuplan.EscapeMenuResponse("Pay whom?"),
                menuplan.NoMenuResponse("Itemized billing?"),
                menuplan.YesMenuResponse("Pay?"),
            ],
        )
        return ActionAdvice(from_advisor=self, action=pay, new_menu_plan=menu_plan)

class DropShopOwnedAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not oracle.in_shop:
            return None

        shop_owned = [i for i in character.inventory.all_items() if i.shop_owned]

        if len(shop_owned) == 0:
            return None

        #import pdb; pdb.set_trace()
        shop_owned_letters = [item.inventory_letter for item in shop_owned]

        menu_plan = menuplan.MenuPlan(
            "drop all shop owned objects",
            self,
            [
                menuplan.YesMenuResponse("Sell it?"),
                menuplan.YesMenuResponse("Sell them?"),
                menuplan.MoreMenuResponse("You drop", always_necessary=False),
                menuplan.MoreMenuResponse("seems uninterested", always_necessary=False),
                menuplan.MoreMenuResponse(re.compile("(y|Y)ou sold .+ for"), always_necessary=False),
            ],
            interactive_menu=[
                menuplan.InteractiveDropTypeChooseTypeMenu(selector_name='all types'),
                menuplan.InteractiveDropTypeMenu(run_state, character.inventory, desired_letter=shop_owned_letters)
            ]
        )
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.DROPTYPE, new_menu_plan=menu_plan)

class PickupDesirableItems(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not (oracle.desirable_object_on_space or run_state.neighborhood.stack_on_square):
            return
        if not run_state.neighborhood.lootable_current_square():
            return
        menu_plan = menuplan.MenuPlan(
            "pick up all desirable objects",
            self,
            [],
            interactive_menu=menuplan.InteractivePickupMenu(run_state, select_desirable='desirable')
        )
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.PICKUP, new_menu_plan=menu_plan)

class HuntNearestWeakEnemyAdvisor(PathAdvisor):
    def find_path(self, rng, run_state, character, oracle):
        return run_state.neighborhood.path_to_nearest_weak_monster()

class HuntNearestEnemyAdvisor(PathAdvisor):
    def find_path(self, rng, run_state, character, oracle):
        #import pdb; pdb.set_trace()
        return run_state.neighborhood.path_to_nearest_monster()

class PathfindDesirableObjectsAdvisor(PathAdvisor):
    def find_path(self, rng, run_state, character, oracle):
        return run_state.neighborhood.path_to_desirable_objects()

class PathfindUnvisitedShopSquares(PathAdvisor):
    def find_path(self, rng, run_state, character, oracle):
        return run_state.neighborhood.path_to_unvisited_shop_sqaures()

class FallbackSearchAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if environment.env.debug:
            import pdb; pdb.set_trace()
        search = nethack.actions.Command.SEARCH
        return ActionAdvice(from_advisor=self, action=search)

class WieldBetterWeaponAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        wield = nethack.actions.Command.WIELD

        if character.inventory.wielded_weapon.BUC == constants.BUC.cursed:
            return None

        best_weapon = character.inventory.proposed_weapon_changes(character)
        if best_weapon is None:
            return None

        assert best_weapon.quantity == 1, "shouldn't be in the business of wielding stacks"
        menu_plan = menuplan.MenuPlan("wield weaon", self, [
            menuplan.CharacterMenuResponse("What do you want to wield?", chr(best_weapon.inventory_letter)),
            ], listening_item=best_weapon)
        #import pdb; pdb.set_trace()
        print(f"Wielding better weapon: {character.inventory.wielded_weapon} -> {best_weapon}")
        #import pdb; pdb.set_trace()
        return ActionAdvice(from_advisor=self, action=wield, new_menu_plan=menu_plan)

class WearUnblockedArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        proposed_items, proposal_blockers = character.inventory.proposed_attire_changes(character)

        for item, blockers in zip(proposed_items, proposal_blockers):
            if len(blockers) == 0:
                wear = nethack.actions.Command.WEAR

                menu_plan = menuplan.MenuPlan("wear armor", self, [
                    menuplan.CharacterMenuResponse("What do you want to wear?", chr(item.inventory_letter)),
                ], listening_item=item)

                return ActionAdvice(from_advisor=self, action=wear, new_menu_plan=menu_plan)
        return None

class UnblockedWardrobeChangesAdvisor(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [WearUnblockedArmorAdvisor]

class WearEvenBlockedArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        proposed_items, proposal_blockers = character.inventory.proposed_attire_changes(character)

        for item, blockers in zip(proposed_items, proposal_blockers):
            if len(blockers) == 0:
                wear = nethack.actions.Command.WEAR

                menu_plan = menuplan.MenuPlan("wear armor", self, [
                    menuplan.CharacterMenuResponse("What do you want to wear?", chr(item.inventory_letter)),
                ], listening_item=item)

                #import pdb; pdb.set_trace()
                return ActionAdvice(from_advisor=self, action=wear, new_menu_plan=menu_plan)

            else:
                if blockers[0].BUC != constants.BUC.cursed:
                    takeoff = nethack.actions.Command.TAKEOFF
                    menu_plan = menuplan.MenuPlan("take off blocking armor", self, [
                        menuplan.CharacterMenuResponse("What do you want to take off?", chr(blockers[0].inventory_letter)),
                    ])

                    return ActionAdvice(from_advisor=self, action=takeoff, new_menu_plan=menu_plan)
                else:
                    pass
                    #print("Blocking armor is cursed. Moving on")

class AnyWardrobeChangeAdvisor(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [WearEvenBlockedArmorAdvisor]

class EngraveTestWandsAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        engrave = nethack.actions.Command.ENGRAVE
        wands = character.inventory.get_oclass(inv.Wand)
        letter = None
        for w in wands:
            if w and not w.identity.is_identified() and not w.shop_owned and not w.identity.listened_actions.get(engrave, False):
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
            menuplan.MoreMenuResponse("You feel self-knowledgeable..."),
            menuplan.NoMenuResponse("Do you want to add to the current engraving?"),
            menuplan.MoreMenuResponse("Agent the"), # best match for enlightenment without regex
            menuplan.MoreMenuResponse("Your intelligence is"),
            menuplan.MoreMenuResponse("You wipe out the message that was written"),
            menuplan.MoreMenuResponse("usage fee"),
            menuplan.MoreMenuResponse("The feeling subsides"),
            menuplan.MoreMenuResponse("The engraving on the floor vanishes!"),
            menuplan.MoreMenuResponse("The engraving on the ground vanishes"),
            menuplan.MoreMenuResponse("You may wish for an object"),
            menuplan.WishMenuResponse("For what do you wish?", character, wand=w),
            menuplan.MoreMenuResponse("silver dragon scale mail"),
            menuplan.PhraseMenuResponse("What do you want to burn", "Elbereth"),
            menuplan.PhraseMenuResponse("What do you want to engrave", "Elbereth"),
            menuplan.PhraseMenuResponse("What do you want to write", "Elbereth"),
            menuplan.PhraseMenuResponse("Create what kind of monster?", "lichen"),
        ], listening_item=w)

        return ActionAdvice(from_advisor=self, action=engrave, new_menu_plan=menu_plan)

class NameItemAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        name_action = run_state.queued_name_action
        run_state.queued_name_action = None
        if name_action is None:
            return None

        #import pdb; pdb.set_trace()
        character.inventory.all_items()
        # sometimes the item has left our inventory when we wish to name it. handle that
        try:
            character.inventory.items_by_letter[name_action.letter]
        except KeyError:
            return None


        menu_plan = menuplan.MenuPlan("name item", self, [
                    menuplan.CharacterMenuResponse(re.compile("What do you want to name\?$"), "i"),
                    menuplan.CharacterMenuResponse("What do you want to name? [", chr(name_action.letter)),
                    menuplan.PhraseMenuResponse("What do you want to name th", name_action.name)
            ])

        return ActionAdvice(self, nethack.actions.Command.CALL, menu_plan)