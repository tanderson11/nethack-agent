import pandas as pd
import os
from collections import defaultdict
from typing import NamedTuple
import re
import numpy as np
import enum

class MonsterSpoiler():
	NORMAL_SPEED = 12

	def __init__(self, name, melee_attack_bundle, ranged_attack_bundle, death_attack_bundle, engulf_attack_bundle, passive_attack_bundle, level, AC, speed, MR, resists):
		self.name = name
		self.melee_attack_bundle = melee_attack_bundle
		self.ranged_attack_bundle = ranged_attack_bundle
		self.death_attack_bundle = death_attack_bundle
		self.engulf_attack_bundle = engulf_attack_bundle
		self.passive_attack_bundle = passive_attack_bundle

		self.level = level
		self.AC = AC
		self.speed = speed
		self.MR = MR

		self.resists = resists

	def probability_to_hit_AC(self, AC):
		# ignoring weapon bonuses/penalties
		# ignoring multi-attack penalty

		if AC >= 0:
			target = 10 + AC + self.level
		else:
			# when AC is negative you get a random number between -1 and AC towards defense
			target = 10 + (AC + (-1))/2 + self.level

		if target < 1:
			target = 1

		probability = min((target-1)/20, 1)

		return probability
    
	def actions_per_unit_time(self):
		# assume player has speed 12
		return self.speed / self.NORMAL_SPEED

	def melee_dps(self, AC):
		p = self.probability_to_hit_AC(AC)
		return self.melee_attack_bundle.expected_damage * p * self.actions_per_unit_time()

	def passive_damage_over_encounter(self, character, kill_trajectory):
		return self.passive_attack_bundle.expected_damage * kill_trajectory.swings_to_kill

	def death_damage_over_encounter(self, character):
		return self.death_attack_bundle.expected_damage

	def excepted_hp_loss_in_melee(self, character, kill_trajectory):
		excepted_hp_loss = self.melee_dps(character.AC) * kill_trajectory.time_to_kill + self.passive_damage_over_encounter(character, kill_trajectory) + self.death_damage_over_encounter(character)
		return excepted_hp_loss

	def fight_outcome(self, character):
		kill_trajectory = character.average_time_to_kill_monster_in_melee(self)
		excepted_hp_loss = self.excepted_hp_loss_in_melee(character, kill_trajectory)

		return excepted_hp_loss, kill_trajectory

	def dangerous_to_player(self, character, time, latest_monster_flight, hp_fraction_tolerance=0.6):
		# if we've recently seen a monster of this type flee, let's assume it's not dangerous
		if latest_monster_flight and (time - latest_monster_flight.time) < 15 and self.name == latest_monster_flight.monster_name:
			return False

		excepted_hp_loss, kill_trajectory = self.fight_outcome(character)

		if excepted_hp_loss < hp_fraction_tolerance * character.current_hp:
			return False
		else:
			return True

	def average_hp(self):
		# know about special things in https://nethackwiki.com/wiki/Hit_points#Monster
		hit_dice = self.level
		if hit_dice == 0:
			return 2.5 # 1d4 hp if level 0
		else:
			return 4.5 * hit_dice # 1d8/level if level > 0

class Resists(enum.Flag):
	NONE = 0
	fire = enum.auto()
	cold = enum.auto()
	sleep = enum.auto()
	disintegration = enum.auto()
	electricity = enum.auto()
	poison = enum.auto()
	acid = enum.auto()
	stoning = enum.auto()

RESIST_MAPPING = {
	'F': Resists.fire,
	'C': Resists.cold,
	'S': Resists.sleep,
	'D': Resists.disintegration,
	'E': Resists.electricity,
	'P': Resists.poison,
	'A': Resists.acid,
	'*': Resists.stoning
}

class AttackBundle():
	matches_no_prefix = False
	prefix_set = set()
	dice_pattern = re.compile('([0-9]+)d([0-9]+)')
	digit_pattern = re.compile('[0-9]')
	suffix_pattern = re.compile('([^0-9\)\]]+)(?:\)|\])?$')

	class DamageTypes(NamedTuple): # some day we should disambiguate damage qualities and damage quantities
		acid: bool
		cold: bool
		disintegration: bool
		electricity: bool
		fire: bool
		heal: bool
		missiles: bool
		poison: bool
		rust: bool
		sleep: bool
		drain: bool
		blind: bool
		confusion: bool
		digest: bool
		energy: bool
		hallucination: bool
		intrinsic: bool
		stick: bool
		rot: bool
		stun: bool
		teleport: bool
		wrap: bool
		prick: bool
		rider: bool
		paralysis: bool
		spell: bool
		steal: bool
		disenchant: bool
		seduce: bool
		slow: bool
		str_drain: bool
		int_drain: bool
		con_drain: bool
		dex_drain: bool
		disease: bool
		gold: bool
		stone: bool
		lycanthropy: bool

		suffix_mapping = { # bool corresponds to if the damage dice affect actual HP
			'A': ('acid',True),
			'C': ('cold', True),
			'D': ('disintegration', True),
			'E': ('electricity', True),
			'F': ('fire', True),
			'H': ('heal', False),
			'M': ('missiles', True),
			'P': ('poison', True),
			'R': ('rust', True),
			'S': ('sleep', True),
			'V': ('drain', True),
			'b': ('blind', False),
			'c': ('confusion', True),
			'd': ('digest', True),
			'e': ('energy', False),
			'h': ('hallucination',False),
			'i': ('intrinsic', True),
			'm': ('stick', True),
			'r': ('rot', True),
			's': ('stun', True),
			't': ('teleport',True),
			'w': ('wrap', True),
			'x': ('prick', True),
			'z': ('rider', True),
			'.': ('paralysis', True),
			'+': ('spell', True),
			'-': ('steal', True),
			'"': ('disenchant', True),
			'&': ('seduce', True),
			'<': ('slow', True),
			'!I': ('int_drain', False), # mind flayers are only doing int drain with tentacles
			'!C': ('con_drain', True), # rabid rats are actually doing damage
			'!S': ('str_drain', True), # this doesn't actually exist ... just normal poison
			'!D': ('dex_drain', True), # quasits also do real damage
			'#': ('disease', True),
			'$': ('gold', True),
			'*': ('stone', True),
			'@': ('lycanthropy', True),
		}

	def __init__(self, attack_strs):
		self.num_attacks = 0

		self.min_damage = 0
		self.expected_damage = 0
		self.max_damage = 0

		damage_types = []
		for a in attack_strs:
			if "(" in a and "(" in self.prefix_set:
				#import pdb; pdb.set_trace()
				pass

			if a[0] in self.prefix_set or (re.match(self.digit_pattern, a[0]) and self.matches_no_prefix): # we care about this kind of attack
				self.num_attacks += 1
				suffix_match = re.search(self.suffix_pattern, a)
				if suffix_match:
					damage_type = suffix_match[1]
					damage_types.append(damage_type)
					attack_does_physical_damage = self.DamageTypes.suffix_mapping[damage_type][1]
				else:
					attack_does_physical_damage = True # no suffix is normal attack

				damage_dice_match = re.search(self.dice_pattern, a)
				if not damage_dice_match:
					import pdb; pdb.set_trace()

				num_dice = int(damage_dice_match[1])
				num_sides = int(damage_dice_match[2])

				if attack_does_physical_damage:
					self.min_damage += num_dice
					self.max_damage += num_dice * num_sides
					self.expected_damage += num_dice * (num_sides + 1)/2

		keys = [f for f in self.__class__.DamageTypes._fields]
		damage_type_dict = {k: False for k in keys}
		for t in damage_types:
			damage_type_dict[self.DamageTypes.suffix_mapping[t][0]] = True

		self.damage_types = self.DamageTypes(**damage_type_dict)

class RangedAttackBundle(AttackBundle):
	prefix_set = set(['B', 'W', 'M', 'G', 'S'])

class DeathAttackBundle(AttackBundle):
	prefix_set = set(['['])

class MeleeAttackBundle(AttackBundle):
	#prefix_set = set(['B', 'E', 'G', 'H', 'M', 'S', 'W', 'X']) # what attacks should match both melee and ranged? TK
	prefix_set = set(['E', 'G', 'H', 'M', 'W', 'X'])
	matches_no_prefix = True

class PassiveAttackBundle(AttackBundle):
	prefix_set = set(['('])

class EngulfAttackBundle(AttackBundle):
	prefix_set = set(['E'])

monster_df = pd.read_csv(os.path.join(os.path.dirname(__file__), "monsters.csv"))

monster_df=monster_df.set_index('SPECIES')

#with open(os.path.join(os.path.dirname(__file__), "monsters_new.csv"), 'w') as f:
#	monster_df.to_csv(f)

dps_rows = {}
ACs = [10, 5, 0, -5, -10, -15, -20, -25]

MONSTERS_BY_NAME = {}
for _, row in monster_df.iterrows():
	name = row.name

	if row['ATTACKS'] is np.nan:
		attack_strs = []
	else:
		attack_strs = row["ATTACKS"].split(' ')
	ranged_bundle = RangedAttackBundle(attack_strs)
	melee_bundle = MeleeAttackBundle(attack_strs)
	passive_bundle = PassiveAttackBundle(attack_strs)
	engulf_bundle = EngulfAttackBundle(attack_strs)
	death_bundle = DeathAttackBundle(attack_strs)

	level = row['LVL']
	AC = row['AC']
	speed = row['SPD']
	MR = row['MR']

	resists = Resists.NONE
	if row['RESISTS'] is not np.nan:
		for character in row['RESISTS'].upper():
			resists |= RESIST_MAPPING[character]

	spoiler = MonsterSpoiler(name, melee_bundle, ranged_bundle, death_bundle, engulf_bundle, passive_bundle, level, AC, speed, MR, resists)
	#print(name, resists)
	#print(name, melee_bundle.max_damage, ranged_bundle.max_damage, passive_bundle.max_damage, death_bundle.max_damage)
	#print(name, {k:v for k,v in zip(melee_bundle.damage_types._fields, melee_bundle.damage_types) if v==True})
	MONSTERS_BY_NAME[name] = spoiler

	# DPS scratch
	#dps_row = [spoiler.melee_dps(AC) for AC in ACs]
	#dps_rows[name] = dps_row

#dps_df = pd.DataFrame.from_dict(dps_rows, orient='index', columns=ACs)
#with open(os.path.join(os.path.dirname(__file__), "dps.csv"), 'w') as f:
#	dps_df.to_csv(f)
