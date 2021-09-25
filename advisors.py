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
    def nuisance_condition(self):
        return (
            self.blstats.check_condition(nethack.BL_MASK_HALLU) or
            self.blstats.check_condition(nethack.BL_MASK_STUN) or
            self.blstats.check_condition(nethack.BL_MASK_CONF)
        )

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
class MenuAdvice(Advice):
    from_menu_plan: menuplan.MenuPlan # Advice generated by
    keypress: int # The ascii ordinal
    new_menu_plan: menuplan.MenuPlan = None # Advising to set this as the new one

    def __post_init__(self):
        utilities.ACTION_LOOKUP[self.keypress] # check that this exists
        if not (self.keypress >= 0 and self.keypress < 128):
            raise Exception("Invalid ascii ordinal")


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
            if advice is not None:
                all_advice.append(advice)
                weights.append(weight)

        if len(all_advice) > 0:
            return rng.choices(all_advice, weights=weights)[0]

class SequentialCompositeAdvisor(CompositeAdvisor):
    def advice(self, rng, run_state, character, oracle):
        for advisor in self.advisors:
            advice = advisor.advice_on_conditions(rng, run_state, character, oracle)
            if advice is not None:
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

class SearchForSecretDoorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        to_search_count = np.count_nonzero(run_state.neighborhood.local_possible_secret_mask)
        if to_search_count == 0:
            return None
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.SEARCH)

class SearchDeadEndAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        # Consider the 8-location square surrounding the player
        # We define a dead end as a situation where a single edge holds all
        # the walkable locations
        walkable_count = np.count_nonzero(run_state.neighborhood.walkable)
        if walkable_count > 3:
            return None
        elif walkable_count > 1:
            edge_counts = [
                np.count_nonzero(run_state.neighborhood.walkable[0,:]),
                np.count_nonzero(run_state.neighborhood.walkable[-1,:]),
                np.count_nonzero(run_state.neighborhood.walkable[:,0]),
                np.count_nonzero(run_state.neighborhood.walkable[:,-1]),
            ]
            if not walkable_count in edge_counts: # i.e. if no edge holds all of them
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

class IdentifyPotentiallyMagicArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        identify_scroll = character.inventory.get_item(inv.Scroll, name="identify")

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

class ReadUnidentifiedScrollsAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        scrolls = character.inventory.get_oclass(inv.Scroll)

        for scroll in scrolls:
            if scroll and scroll.identity and not scroll.identity.is_identified() and scroll.BUC != constants.BUC.cursed:
                letter = scroll.inventory_letter

                interactive_menus = [
                    menuplan.InteractiveIdentifyMenu(run_state, character.inventory), # identifies first choice since we don't specify anything
                ]

                menu_plan = menuplan.MenuPlan("read unidentified scroll", self, [
                    menuplan.CharacterMenuResponse("What do you want to read?", chr(letter)),
                    menuplan.PhraseMenuResponse("What monster do you want to genocide?", "fire ant"),
                    menuplan.EscapeMenuResponse("Where do you want to center the stinking cloud"),
                    menuplan.MoreMenuResponse(re.compile("Where do you want to center the explosion\?$")),
                    # most remote square for placements
                    menuplan.CharacterMenuResponse("(For instructions type a '?')", "Z", follow_with=ord('.')),
                    menuplan.CharacterMenuResponse("What class of monsters do you wish to genocide?", "a", follow_with=ord('\r')),
                    menuplan.MoreMenuResponse("As you read the scroll, it disappears.", always_necessary=False),
                    menuplan.MoreMenuResponse("This is a scroll of"),
                    menuplan.MoreMenuResponse(re.compile("This is a (.+) scroll")),
                    menuplan.MoreMenuResponse("You have found a scroll of"),
                    menuplan.EscapeMenuResponse("What do you want to charge?"),
                    menuplan.NoMenuResponse("Do you wish to teleport?"),
                ], interactive_menu=interactive_menus)

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
            armaments = character.inventory.get_slots('armaments')

            for item in armaments:
                if isinstance(item, inv.Weapon):
                    # don't enchant if it could implode an item
                    # weapon enhancements don't auto id, so possibly we should fail if item.enhancement is None 
                    if item.enhancement is not None and item.enhancement > 5: 
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
                menuplan.YesMenuResponse(f"{run_state.neighborhood.fresh_corpse_on_square_glyph.name} corpse here; eat"),
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

# CURRENTLY DON'T ATTACK INVISIBLE_ETC
class DumbMeleeAttackAdvisor(Advisor):
    def satisfactory_monster(self, monster, rng, run_state, character, oracle):
        '''Returns True if this is a monster the advisor is willing to target. False otherwise.

        Only called on a monster glyph  as identified by the neighborhood (ex. InvisibleGlyph)'''
        return not isinstance(monster, gd.MonsterGlyph) or not monster.always_peaceful

    def prioritize_target(self, monsters, rng, run_state, character, oracle):
        return 0

    def get_monsters(self, rng, run_state, character, oracle):
        it = np.nditer(run_state.neighborhood.is_monster, flags=['multi_index'])
        monsters = []
        monster_squares = []
        for is_monster in it:
            glyph = run_state.neighborhood.glyphs[it.multi_index]
            if is_monster and self.satisfactory_monster(glyph, rng, run_state, character, oracle):
                monsters.append(glyph)
                monster_squares.append(it.multi_index)

        return monsters, monster_squares

    def advice(self, rng, run_state, character, oracle):
        monsters, monster_squares = self.get_monsters(rng, run_state, character, oracle)

        if len(monsters) > 0:
            target_index = self.prioritize_target(monsters, rng, run_state, character, oracle)
            target_square = monster_squares[target_index]
            attack_direction = run_state.neighborhood.action_grid[target_square]
            return ActionAdvice(from_advisor=self, action=attack_direction)
        return None

class MeleeHoldingMonsterAdvisor(DumbMeleeAttackAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if character.held_by is None:
            return None

        #import pdb; pdb.set_trace()
        return super().advice(rng, run_state, character, oracle)

    def satisfactory_monster(self, monster, rng, run_state, character, oracle):
        if not super().satisfactory_monster(monster, rng, run_state, character, oracle):
            return False

        return monster == character.held_by.monster_glyph

class RangedAttackAdvisor(DumbMeleeAttackAdvisor):
    def advice(self, rng, run_state, character, oracle):
        monsters, monster_squares = self.get_monsters(rng, run_state, character, oracle)

        if len(monsters) > 0:
            target_index = self.prioritize_target(monsters, rng, run_state, character, oracle)
            target_square = monster_squares[target_index]
            attack_direction = run_state.neighborhood.action_grid[target_square]

            fire = nethack.actions.Command.FIRE

            weapons = character.inventory.get_oclass(inv.Weapon)
            for w in weapons:
                if w and (w.equipped_status is None or w.equipped_status.status != 'wielded'):
                    menu_plan = menuplan.MenuPlan(
                        "ranged attack", self, [
                            menuplan.DirectionMenuResponse("In what direction?", attack_direction),
                            menuplan.MoreMenuResponse("You have no ammunition"),
                            menuplan.MoreMenuResponse("You ready"),
                            # note throw: means we didn't have anything quivered
                            menuplan.CharacterMenuResponse("What do you want to throw?", chr(w.inventory_letter)),
                        ],
                    )
                    return ActionAdvice(from_advisor=self, action=fire, new_menu_plan=menu_plan)
        return None

class PassiveMonsterRangedAttackAdvisor(RangedAttackAdvisor):
    def satisfactory_monster(self, monster, rng, run_state, character, oracle):
        if not super().satisfactory_monster(monster, rng, run_state, character, oracle):
            return False

        if monster.monster_spoiler.passive_attack_bundle.num_attacks > 0:
            return True
        else:
            return False

    def prioritize_target(self, monsters, rng, run_state, character, oracle):
        max_damage = 0
        target_index = None
        # prioritize by maximum passive damage
        for i,m in enumerate(monsters):
            damage = m.monster_spoiler.passive_attack_bundle.expected_damage

            if target_index is None or damage > max_damage:
                target_index = i
                max_damage = damage

        return target_index

class LowerDPSAsQuicklyAsPossibleMeleeAttackAdvisor(DumbMeleeAttackAdvisor):
    def prioritize_target(self, monsters, rng, run_state, character, oracle):
        if len(monsters) == 1:
            return 0
        else:
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

            return target_index

class UnsafeMeleeAttackAdvisor(LowerDPSAsQuicklyAsPossibleMeleeAttackAdvisor):
    pass

class SafeMeleeAttackAdvisor(LowerDPSAsQuicklyAsPossibleMeleeAttackAdvisor):
    unsafe_hp_loss_fraction = 0.5
    def satisfactory_monster(self, monster, rng, run_state, character, oracle):
        if not super().satisfactory_monster(monster, rng, run_state, character, oracle):
            return False

        if isinstance(monster, gd.MonsterGlyph):
            spoiler = monster.monster_spoiler
            trajectory = character.average_time_to_kill_monster_in_melee(spoiler)

            if spoiler and spoiler.passive_damage_over_encounter(character, trajectory) + spoiler.death_damage_over_encounter(character) > self.unsafe_hp_loss_fraction * character.current_hp:
                return False

        return True

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
    @staticmethod
    def hankering_for_excalibur(character):
        if character.base_alignment == 'lawful' and character.experience_level >= 5:
            current_weapon = character.inventory.wielded_weapon
            if current_weapon.identity is not None and current_weapon.identity.name() == 'long sword' and not current_weapon.identity.is_artifact:
                return True
        return False

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
                menuplan.MoreMenuResponse("You drop"),
                menuplan.ConnectedSequenceMenuResponse("What would you like to drop?", ".")
            ],
            interactive_menu=[
                menuplan.InteractiveDropTypeChooseTypeMenu(selector_name='unknown BUC'),
            ]
        )
        return ActionAdvice(from_advisor=self, action=nethack.actions.Command.DROPTYPE, new_menu_plan=menu_plan)

class DipForExcaliburAdvisor(ExcaliburAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if not (self.hankering_for_excalibur(character) and run_state.neighborhood.dungeon_glyph_on_player and run_state.neighborhood.dungeon_glyph_on_player.is_fountain):
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
        if not self.hankering_for_excalibur(character):
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
        if heading is None:
            if environment.env.debug:
                import pdb; pdb.set_trace()
                pass
            return None

        if heading.direction == map.DirectionThroughDungeon.down and not character.am_willing_to_descend(run_state.blstats.get('depth')+1):
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
        if heading is None:
            if environment.env.debug:
                import pdb; pdb.set_trace()
            return None

        if traversed_staircase is not None:
            if traversed_staircase.matches_heading(heading):
                action = nethack.actions.MiscDirection.DOWN if oracle.on_downstairs else nethack.actions.MiscDirection.UP
                #if heading.direction == map.DirectionThroughDungeon.flat:
                #action = nethack.actions.MiscDirection.DOWN if heading.direction == map.DirectionThroughDungeon.down else nethack.actions.MiscDirection.UP
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

        if heading.direction == map.DirectionThroughDungeon.down and not character.am_willing_to_descend(run_state.blstats.get('depth')+1):
            return None

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

class DropUndesirableAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not character.near_burdened:
            return None

        character.near_burdened = False
        undesirable_items = character.inventory.all_undesirable_items(character)
        if len(undesirable_items) == 0:
            return None

        undesirable_letters = [item.inventory_letter for item in undesirable_items]

        menu_plan = menuplan.MenuPlan(
            "drop all undesirable objects",
            self,
            [
                menuplan.YesMenuResponse("Sell it?"),
                menuplan.MoreMenuResponse("You drop"),
            ],
            interactive_menu=[
                menuplan.InteractiveDropTypeChooseTypeMenu(selector_name='all types'),
                menuplan.InteractiveDropTypeMenu(run_state, character.inventory, desired_letter=undesirable_letters)
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

class FallbackSearchAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
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

        menu_plan = menuplan.MenuPlan("wield weaon", self, [
            menuplan.CharacterMenuResponse("What do you want to wield?", chr(best_weapon.inventory_letter)),
            ], listening_item=best_weapon)

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
            if w and not w.identity.is_identified() and not w.identity.listened_actions.get(engrave, False) and not w.shop_owned():
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
            menuplan.PhraseMenuResponse("For what do you wish?", "+2 blessed silver dragon scale mail"),
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

        menu_plan = menuplan.MenuPlan("name item", self, [
                    menuplan.CharacterMenuResponse(re.compile("What do you want to name\?$"), "i"),
                    menuplan.CharacterMenuResponse("What do you want to name? [", chr(name_action.letter)),
                    menuplan.PhraseMenuResponse("What do you want to name this", name_action.name)
            ])

        return ActionAdvice(self, nethack.actions.Command.CALL, menu_plan)