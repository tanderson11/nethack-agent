import abc
from typing import NamedTuple

import glyphs as gd
import nle.nethack as nethack
import numpy as np

import functools

import map
import physics
import environment
import menuplan
import utilities
from utilities import ARS
import inventory as inv
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
        # TK Held, overburndened, etc.
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
    def am_threatened(self):
        return self.neighborhood.threat_on_player > 0.

    @functools.cached_property
    def am_safe(self):
        return not self.weak_with_hunger and not self.am_threatened and self.character.current_hp > self.character.max_hp * 2/3

    @functools.cached_property
    def life_threatened(self):
        return self.neighborhood.threat_on_player > self.character.current_hp

    @functools.cached_property
    def on_warning_engraving(self):
        return self.neighborhood.level_map.warning_engravings.get(self.neighborhood.absolute_player_location, False)

    @functools.cached_property
    def desirable_object_on_space(self):
        prev_glyph = self.neighborhood.previous_glyph_on_player
        desirable_object_on_space = (
            (isinstance(prev_glyph, gd.ObjectGlyph) or isinstance(prev_glyph, gd.CorpseGlyph)) and
            prev_glyph.desirable_object(self.run_state.global_identity_map, self.character)
        )

        return desirable_object_on_space

    @functools.cached_property
    def have_moves(self):
        have_moves = self.neighborhood.walkable.any() # at least one square is walkable
        return have_moves

    @functools.cached_property
    def adjacent_monsters(self):
        return np.count_nonzero(self.neighborhood.is_monster)

    @functools.cached_property
    def urgent_major_trouble(self):
        return self.blstats.check_condition(nethack.BL_MASK_STONE)

    @functools.cached_property
    def major_trouble(self):
        return "You feel feverish." in self.message.message

    @functools.cached_property
    def can_enhance(self):
        can_enhance = "You feel more confident" in self.message.message or "could be more dangerous" in self.message.message
        return can_enhance

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

class Advice():
    def __init__(self, advisor, action, menu_plan):
        self.advisor = advisor
        self.action = action
        self.menu_plan = menu_plan

    def __repr__(self):
        return "Advice: (action={}; advisor={}; menu_plan={})".format(self.action, self.advisor, self.menu_plan)

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
        return Advice(self, wait, None)

class SearchForSecretDoorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        search = nethack.actions.Command.SEARCH
        if (utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.possible_secret_door, run_state.neighborhood.glyphs)).any():
            return Advice(self, search, None)
        return None

class DrinkHealingPotionAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        quaff = nethack.actions.Command.QUAFF
        potions = character.inventory.get_oclass(inv.Potion)

        for potion in potions:
            if potion and potion.identity and potion.identity.name() and 'healing' in potion.identity.name():
                letter = potion.inventory_letter
                menu_plan = menuplan.MenuPlan(
                    "drink healing potion", self, [
                        menuplan.CharacterMenuResponse("What do you want to drink?", chr(letter)),
                        menuplan.NoMenuResponse("Drink from the fountain?"),
                        menuplan.NoMenuResponse("Drink from the sink?"),
                    ])
                return Advice(self, quaff, menu_plan)
        return None

class DoCombatHealingAdvisor(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [DrinkHealingPotionAdvisor]

class ZapTeleportOnSelfAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        zap = nethack.actions.Command.ZAP
        wands = character.inventory.get_oclass(inv.Wand)

        for wand in wands:
            if wand and wand.identity and wand.identity.name() == 'teleportation':
                letter = wand.inventory_letter
                menu_plan = menuplan.MenuPlan("zap teleportation wand", self, [
                    menuplan.CharacterMenuResponse("What do you want to zap?", chr(letter)),
                    menuplan.DirectionMenuResponse("In what direction?", run_state.neighborhood.action_grid[run_state.neighborhood.local_player_location]),
                ])
                return Advice(self, zap, menu_plan)
        return None

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
                return Advice(self, read, menu_plan)
        return None

class UseEscapeItemAdvisor(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [ZapTeleportOnSelfAdvisor, ReadTeleportAdvisor]

class IdentifyPotentiallyMagicArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        scrolls = character.inventory.get_oclass(inv.Scroll)

        found_identify = False
        for scroll in scrolls:
            if scroll and scroll.identity and scroll.identity.name() == 'identify':
                found_identify = True
                break

        if not found_identify:
            return None

        armor = character.inventory.get_oclass(inv.Armor)

        found_magic = False
        for item in armor:
            # could it be magical?
            if item.identity and item.identity.name() is None and item.identity.magic().any():
                found_magic = True
                break

        if not found_magic:
            return None

        print("Trying to identify")
        
        menu_plan = menuplan.MenuPlan("identify boilerplate", self, [
            menuplan.CharacterMenuResponse("What do you want to read?", chr(scroll.inventory_letter)),
            menuplan.MoreMenuResponse("As you read the scroll, it disappears."),
        ], interactive_menu=menuplan.InteractiveIdentifyMenu(run_state, character.inventory, desired_letter=chr(item.inventory_letter)))

        return Advice(self, read, menu_plan)

class ReadUnidentifiedScrolls(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        scrolls = character.inventory.get_oclass(inv.Scroll)

        for scroll in scrolls:
            if scroll and scroll.identity and not scroll.identity.is_identified() and scroll.BUC != 'cursed':
                letter = scroll.inventory_letter

                interactive_menus = [
                    menuplan.InteractiveIdentifyMenu(run_state, character.inventory), # identifies first choice since we don't specify anything
                    #menuplan.InteractiveValidPlacementMenu(run_state, pick_last=True) # get farthest possible valid square for fireballs
                ]

                menu_plan = menuplan.MenuPlan("read unidentified scroll", self, [
                    menuplan.CharacterMenuResponse("What do you want to read?", chr(letter)),
                    menuplan.PhraseMenuResponse("What monster do you want to genocide?", "fire ant"),
                    menuplan.EscapeMenuResponse("Where do you want to center the stinking cloud"),
                    menuplan.MoreMenuResponse(re.compile("Where do you want to center the explosion\?$")),
                    # open interactive menu of valid placements for fireballs; NLE very stupidly doesn't give a better message match than this
                    menuplan.CharacterMenuResponse("(For instructions type a '?')", "Z", follow_with=utilities.keypress_action(ord('.'))),
                    menuplan.CharacterMenuResponse("What class of monsters do you wish to genocide?", "a", follow_with=utilities.keypress_action(ord('\r'))),
                    menuplan.MoreMenuResponse("As you read the scroll, it disappears.", always_necessary=False),
                    menuplan.MoreMenuResponse("This is a scroll of"),
                    menuplan.MoreMenuResponse(re.compile("This is a (.+) scroll")),
                    menuplan.MoreMenuResponse("You have found a scroll of"),
                    menuplan.EscapeMenuResponse("What do you want to charge?"),
                    menuplan.NoMenuResponse("Do you wish to teleport?"),
                ], interactive_menu=interactive_menus)

                #import pdb; pdb.set_trace()
                return Advice(self, read, menu_plan)

class ReadKnownBeneficialScrolls(Advisor):
    def advice(self, rng, run_state, character, oracle):
        read = nethack.actions.Command.READ
        scrolls = character.inventory.get_oclass(inv.Scroll)

        for scroll in scrolls:
            if (scroll and scroll.identity and
                (scroll.BUC is not None and scroll.BUC != 'cursed') and
                (scroll.identity.name() == 'enchant armor' or scroll.identity.name() == 'enchant weapon')
                ):
                letter = scroll.inventory_letter

                menu_plan = menuplan.MenuPlan("read enchant scroll", self, [
                    menuplan.CharacterMenuResponse("What do you want to read?", chr(letter))
                ])
                return Advice(self, read, menu_plan)


class EnhanceSkillsAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if not oracle.can_enhance:
            return None

        enhance = nethack.actions.Command.ENHANCE
        menu_plan = menuplan.MenuPlan(
            "enhance skills",
            self,
            [],
            interactive_menu=menuplan.InteractiveEnhanceSkillsMenu(),
        )

        return Advice(self, enhance, menu_plan)

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

        return Advice(self, eat, menu_plan)

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
        return True

    def advice(self, rng, run_state, character, oracle):
        eat = nethack.actions.Command.EAT
        food = character.inventory.get_oclass(inv.Food) # not eating corpses atm TK TK

        for comestible in food:
            if comestible and self.check_comestible(comestible, rng, run_state, character, oracle):
                letter = comestible.inventory_letter
                menu_plan = self.make_menu_plan(letter)
                return Advice(self, eat, menu_plan)
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
        return Advice(self, pray, menu_plan)

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
            return Advice(self, attack_direction, None)
        return None

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
                    return Advice(self, fire, menu_plan)
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
            return Advice(self, move_action, None)

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

            desired_square = (run_state.neighborhood.local_player_location[0] + path.delta[0], run_state.neighborhood.local_player_location[1] + path.delta[1])
            return Advice(self, path.path_action, None)

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
            if staircase.end_dcoord[0] == map.Branches.GnomishMines.value:
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

class TravelToDownstairsAdvisor(DownstairsAdvisor):
    def advice(self, rng, run_state, character, oracle):
        willing_to_descend = self.check_willingness_to_descend(run_state.blstats, character.inventory, run_state.neighborhood)
        
        if willing_to_descend:
            travel = nethack.actions.Command.TRAVEL

            menu_plan = menuplan.MenuPlan(
                "travel down", self, [
                    menuplan.CharacterMenuResponse("Where do you want to travel to?", ">"),
                    menuplan.EscapeMenuResponse("Can't find dungeon feature"),
                ],
                fallback=utilities.keypress_action(ord('.')))
     
            return Advice(self, travel, menu_plan)
        return None

class GoDownstairsAdvisor(DownstairsAdvisor):
    def advice(self, rng, run_state, character, oracle):
        if oracle.can_move and oracle.on_downstairs:
            willing_to_descend = self.check_willingness_to_descend(run_state.blstats, character.inventory, run_state.neighborhood)
            if willing_to_descend:
                return Advice(self, nethack.actions.MiscDirection.DOWN, None)

class UpstairsAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if oracle.can_move and oracle.on_upstairs:
            willing_to_ascend = self.willing_to_ascend(rng, run_state, character, oracle)
            if willing_to_ascend:
                menu_plan = menuplan.MenuPlan("go upstairs", self, [
                      menuplan.NoMenuResponse("Beware, there will be no return!  Still climb? [yn] (n)"),
                  ])
                return Advice(self, nethack.actions.MiscDirection.UP, None)
            return None
        return None

    def willing_to_ascend(self, rng, run_state, character, oracle):
        if oracle.blstats.get('depth') == 1:
            return False
        return True 

class TraverseUnknownUpstairsAdvisor(UpstairsAdvisor):
    def willing_to_ascend(self, rng, run_state, character, oracle):
        if oracle.blstats.get('depth') == 1:
            return False
        try:
            # if we know about this staircase, we're not interested
            run_state.neighborhood.level_map.staircases[run_state.neighborhood.absolute_player_location]
            return False
        except:
            return True

class OpenClosedDoorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        # coarse check
        if oracle.on_warning_engraving:
            return None

        # don't open diagonally so we can be better about warning engravings
        door_mask = ~run_state.neighborhood.diagonal_moves & utilities.vectorized_map(lambda g: isinstance(g, gd.CMapGlyph) and g.is_closed_door, run_state.neighborhood.glyphs)
        door_directions = run_state.neighborhood.action_grid[door_mask]
        if len(door_directions > 0):
            a = rng.choice(door_directions)
            # another check: don't want to open doors if they are adjacent to an engraving
            for location in run_state.neighborhood.level_map.warning_engravings.keys():
                door_loc = physics.offset_location_by_action(run_state.neighborhood.absolute_player_location, utilities.ACTION_LOOKUP[a])
                if np.abs(door_loc[0] - location[0]) < 2 and np.abs(door_loc[1] - location[1]) < 2:
                    return None

            return Advice(self, a, None)
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
            for location in run_state.neighborhood.level_map.warning_engravings.keys():
                door_loc = physics.offset_location_by_action(run_state.neighborhood.absolute_player_location, utilities.ACTION_LOOKUP[a])
                # another check: don't want to kick doors if they are adjacent to an engraving
                if np.abs(door_loc[0] - location[0]) < 2 and np.abs(door_loc[1] - location[1]) < 2:
                    return None
        else: # we got the locked door message but didn't find a door
            a = None
        if a is not None:
            menu_plan = menuplan.MenuPlan("kick locked door", self, [
                menuplan.DirectionMenuResponse("In what direction?", a),
            ])
            return Advice(self, kick, menu_plan)

class PickupFoodAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if oracle.desirable_object_on_space:
            menu_plan = menuplan.MenuPlan(
                "pick up comestibles and safe corpses",
                self,
                [],
                interactive_menu=menuplan.InteractivePickupMenu(run_state, selector_name='comestibles'),
            )
            #print("Food pickup")
            return Advice(self, nethack.actions.Command.PICKUP, menu_plan)
        return None

class PickupArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if oracle.desirable_object_on_space: #You have much trouble lifting a splint mail.  Continue? [ynq] (q)     
            menu_plan = menuplan.MenuPlan(
                "pick up armor",
                self,
                [],
                interactive_menu=menuplan.InteractivePickupMenu(run_state, selector_name='armor'),
            )
            #print("Armor pickup")
            return Advice(self, nethack.actions.Command.PICKUP, menu_plan)
        return None

class PickupDesirableItems(PrebakedSequentialCompositeAdvisor):
    sequential_advisors = [PickupFoodAdvisor, PickupArmorAdvisor]

class HuntNearestWeakEnemyAdvisor(PathAdvisor):
    def find_path(self, rng, run_state, character, oracle):
        return run_state.neighborhood.path_to_nearest_weak_monster()

class HuntNearestEnemyAdvisor(PathAdvisor):
    def find_path(self, rng, run_state, character, oracle):
        #import pdb; pdb.set_trace()
        return run_state.neighborhood.path_to_nearest_monster()

class FallbackSearchAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        search = nethack.actions.Command.SEARCH
        return Advice(self, search, None)

class WearUnblockedArmorAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        proposed_items, proposal_blockers = character.inventory.proposed_attire_changes(character)

        for item, blockers in zip(proposed_items, proposal_blockers):
            if len(blockers) == 0:
                wear = nethack.actions.Command.WEAR

                menu_plan = menuplan.MenuPlan("wear armor", self, [
                    menuplan.CharacterMenuResponse("What do you want to wear?", chr(item.inventory_letter)),
                ], listening_item=item)

                return Advice(self, wear, menu_plan)
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

                return Advice(self, wear, menu_plan)

            else:
                if blockers[0].BUC != 'cursed':
                    takeoff = nethack.actions.Command.TAKEOFF
                    menu_plan = menuplan.MenuPlan("take off blocking armor", self, [
                        menuplan.CharacterMenuResponse("What do you want to take off?", chr(blockers[0].inventory_letter)),
                    ])

                    return Advice(self, takeoff, menu_plan)
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
            if w and not w.identity.is_identified() and not w.identity.listened_actions.get(utilities.ACTION_LOOKUP[engrave], False):
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
            menuplan.MoreMenuResponse("The feeling subsides"),
            menuplan.MoreMenuResponse("The engraving on the floor vanishes!"),
            menuplan.MoreMenuResponse("The engraving on the ground vanishes"),
            menuplan.MoreMenuResponse("You may wish for an object"),
            menuplan.PhraseMenuResponse("For what do you wish?", "+2 blessed silver dragon scale mail"),
            menuplan.MoreMenuResponse("silver dragon scale mail"),
            menuplan.PhraseMenuResponse("What do you want to burn", "Elbereth"),
            menuplan.PhraseMenuResponse("What do you want to engrave", "Elbereth"),
            menuplan.PhraseMenuResponse("What do you want to write", "Elbereth"),
        ], listening_item=w)

        #pdb.set_trace()
        return Advice(self, engrave, menu_plan)

