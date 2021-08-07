import abc
from typing import NamedTuple

import numpy as np

class Advice():
    def __init__(self, advisor, action, menu_plan):
        self.advisor = advisor
        self.action = action
        self.menu_plan = menu_plan

    def __repr__(self):
        return "Advice: (action={}; advisor={}; menu_plan={})".format(self.action.name, self.advisor, self.menu_plan)

class Advisor(abc.ABC):
	def __init__(self, oracle_consultation=lambda o: True, threat_tolerance=None, threat_threshold=None, no_adjacent_monsters=False):
		self.consult = oracle_consultation
		self.threat_tolerance = threat_tolerance,
		self.no_adjacent_monsters = no_adjacent_monsters

	def check_conditions(self, run_state, character, oracle):
		if self.threat_tolerance and run_state.neighborhood.threat_on_player > character.current_hp * self.threat_tolerance:
			return False

		if self.threat_threshold and run_state.neighborhood.threat_on_player < character.current_hp * self.threat_threshold:
			return False

		if self.no_adjacent_monsters == True and run_state.neighborhood.is_monster.any():
			return False

		if self.consult(oracle) == False:
			return False

		return True

	@abc.abstractmethod
	def advice(self, rng, run_state, character, oracle):
		pass

class CompositeAdvisor(Advisor):
	def __init__(advisors=None, oracle_consultation=None, threat_tolerance=None, threat_threshold=None):
		self.advisors = advisors
		super().__init__(oracle_consultation=oracle_consultation, threat_tolerance=threat_tolerance, threat_threshold=threat_threshold)

class RandomCompositeAdvisor(CompositeAdvisor):
	def advice(self, rng, run_state, character, oracle):
		all_advice = []
		weights = []
		for advisor, weight in self.advisors.items():
			advice = advisor.advice(rng, run_state, character, oracle)
			if advice is not None:
				all_advice.append(advice)
				weights.append(weight)

		return rng.choice(all_advice, weights=weights)

class SequentialCompositeAdvisor(CompositeAdvisor):
	def advice(self, run_state, character, oracle):
		for advisor, odds in self.advisors:
			advice = advisor.advice(run_state, character, oracle)
			if advice is not None:
				return advice

class WaitAdvisor(Advisor):
	def advice(self, rng, run_state, character, oracle):
		wait = nethack.actions.MiscDirection.WAIT
		return Advice(self, wait, None)

class GoUpstairsAdvisor(Advisor):
	def advice(self, rng, run_state, character, oracle):
		up = nethack.actions.MiscDirection.UP
		return Advice(self, up, None)

class DrinkHealingPotionAdvisor(Advisor):
    def advice(self, run_state, character, oracle):
        quaff = nethack.actions.Command.QUAFF
        potions = inventory.get_oclass(inv.Potion)

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

class DoCombatHealingAdvisor(SequentialCompositeAdvisor):
	sequential_advisors = [DrinkHealingPotionAdvisor]

	def __init__(oracle_consultation=None, threat_tolerance=None, threat_threshold=None):
		advisors = [adv() for adv in self.sequential_advisors]
		super().__init__(advisors, oracle_consultation, threat_tolerance, threat_threshold)

class ZapTeleportOnSelfAdvisor(Advisor):
    def advice(self, run_state, character, oracle):
        zap = nethack.actions.Command.ZAP
        wands = inventory.get_oclass(inv.Wand)

        for wand in wands:
            if wand and wand.identity and wand.identity.name() == 'teleportation':
                letter = wand.inventory_letter
                menu_plan = menuplan.MenuPlan("zap teleportation wand", self, [
                    menuplan.CharacterMenuResponse("What do you want to zap?", chr(letter)),
                    menuplan.DirectionMenuResponse("In what direction?", neighborhood.action_grid[neighborhood.local_player_location]),
                ])
                return Advice(self, zap, menu_plan)
        return None

class ReadTeleportAdvisor(Advisor):
    def advice(self, run_state, character, oracle):
        read = nethack.actions.Command.READ
        scrolls = inventory.get_oclass(inv.Scroll)

        for scroll in scrolls:
            if scroll and scroll.identity and scroll.identity.name() == 'teleport':
                letter = scrolls.inventory_letter
                menu_plan = menuplan.MenuPlan("read teleport scroll", self, [
                    menuplan.CharacterMenuResponse("What do you want to read?", chr(letter))
                ])
                return Advice(self, read, menu_plan)
        return None

class UseEscapeItemAdvisor(SequentialCompositeAdvisor):
	sequential_advisors = [ZapTeleportOnSelfAdvisor, ReadTeleportAdvisor]

	def __init__(oracle_consultation=None, threat_tolerance=None, threat_threshold=None):
		advisors = [adv() for adv in self.sequential_advisors]
		super().__init__(advisors, oracle_consultation, threat_tolerance, threat_threshold)

class EnhanceSkillsAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        enhance = nethack.actions.Command.ENHANCE
        menu_plan = menuplan.MenuPlan(
            "enhance skills",
            self,
            [],
            interactive_menu=menuplan.InteractiveEnhanceSkillsMenu(run_state),
        )

        return Advice(self, enhance, menu_plan)

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
        food = inventory.get_oclass(inv.Food) # not eating corpses atm TK TK

        for comestible in food:
        	if comestible and self.check_comestible(comestible, rng, run_state, character, oracle):
				letter = comestible.inventory_letter
                menu_plan = self.make_menu_plan(letter)
                return Advice(self, eat, menu_plan)
        return None

class CombatEatAdvisor(Advisor):
	def check_comestible(self, comestible, rng, run_state, character, oracle):
		return comestible.identity and comestible.identity.name() != 'tin'

class PrayerAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        if character.last_pray_time is None and blstats.get('time') <= 300:
            return None
        if character.last_pray_time is not None and (blstats.get('time') - character.last_pray_time) < 250:
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
		return True

	def prioritize_target(self, monsters, rng, run_state, character, oracle):
		return 0

	def get_monsters(self, rng, run_state, character, oracle):
		it = np.nditer(run_state.neighborhood.is_monster, oracle_consultation=['multi_index'])
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
	        attack_direction = neighborhood.action_grid[target_square]
	        return Advice(self, attack_direction, None)
	    return None

class RangedAttackAdvisor(DumbMeleeAttackAdvisor):
    def advice(self, rng, run_state, character, oracle):
    	monsters, monster_squares = self.get_monsters(rng, run_state, character, oracle)

        if len(monsters) > 0:
			target_index = self.prioritize_target(monsters, rng, run_state, character, oracle)
			target_square = monster_squares[target_index]
	        attack_direction = neighborhood.action_grid[target_square]

	        fire = nethack.actions.Command.FIRE

	        weapons = inventory.get_oclass(inv.Weapon)
            for w in weapons:
                if w and (w.equipped_status is None or w.equipped_status.status != 'wielded'):
                    menu_plan = menuplan.MenuPlan(
                        "ranged attack", self, [
                            menuplan.DirectionMenuResponse("In what direction?", attack_direction.action_value),
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
		if monster.monster_spoiler.passive_attack_bundle.num_attacks > 0:
			return True
		else:
			return False

	def prioritize_target(self, monsters, rng, run_state, character, oracle):
		max_damage = 0
		target_monster = None
		# prioritize by maximum passive damage
		for i,m in enumerate(monsters):
			damage = m.monster_spoiler.passive_attack_bundle.expected_damage

			if target_monster is None or damage > max_damage:
				target_monster = i
				max_damage = damage

		return target_monster

class LowerDPSAsQuicklyAsPossibleMeleeAttackAdvisor(DumbMeleeAttackAdvisor):
	def prioritize_target(self, monsters, rng, run_state, character, oracle):
		if len(m) == 1:
			return m[0]
		else:
			target_monster = None
			best_reduction_rate = 0
			for i, m in enumerate(monsters):
				untargeted_dps = m.melee_dps(character.AC)
				kill_trajectory = character.average_time_to_kill_monster_in_melee(m.monster_spoiler)

				dps_reduction_rate = untargeted_dps/kill_trajectory.time_to_kill

				if target_monster is None or dps_reduction_rate > best_reduction:
					target_monster = i
					best_reduction_rate = dps_reduction_rate

			return target_monster

class UnsafeMeleeAttackAdvisor(LowerDPSAsQuicklyAsPossibleMeleeAttackAdvisor):
	pass

class SafeMeleeAttackAdvisor(LowerDPSAsQuicklyAsPossibleMeleeAttackAdvisor):
	unsafe_hp_loss_fraction = 0.5
	def satisfactory_monster(self, monster, rng, run_state, character, oracle):
		spoiler = monster.monster_spoiler
		trajectory = character.average_time_to_kill_monster_in_melee(spoiler)

		if spoiler and spoiler.passive_damage_over_encounter(character, trajectory) + spoiler.death_damage_over_encounter(character) > self.unsafe_hp_loss_fraction * character.current_hp:
			return False

		return True

class MoveAdvisor(Advisor):
	def __init__(self, oracle_consultation=None, no_adjacent_monsters=True, square_threat_tolerance=None):
		self.square_threat_tolerance = square_threat_tolerance
		super().__init__(self, oracle_consultation=oracle_consultation, no_adjacent_monsters=no_adjacent_monsters)

	def would_move_squares(self, rng, run_state, character, oracle):
		move_mask  = run_state.neighborhood.walkable
		# don't move into intolerable threat
		move_mask &= run_state.neighborhood.threat <= self.square_threat_tolerance * character.current_hp
		return move_mask

class RandomMoveAdvisor():
	def advice(self, rng, run_state, character, oracle):
		move_mask = self.would_move_squares(self, rng, run_state, character, oracle)
		possible_actions = neighborhood.action_grid[move_mask]

		return Advice(self, rng.choice(possible_actions), None)

class HuntNearestWeakEnemyAdvisor(Advisor):
    def advice(self, rng, run_state, character, oracle):
        path_step = neighborhood.path_to_weak_monster()

        if path_step is not None:
	        desired_square = (neighborhood.local_player_location[0] + path_step.delta[0], neighborhood.local_player_location[1] + path_step.delta[1])
	        return Advice(self, path_step.path_action, None)


