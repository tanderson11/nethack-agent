import pandas as pd
import os
from collections import defaultdict
from typing import NamedTuple
import re
import numpy as np

resist_mapping = {'F': 'fire', 'C': 'cold', 'S': 'sleep', 'D': 'disintegration', 'E': 'electric', 'P': 'poison', 'A': 'acid', '*': 'stoning'}

#resist_mapping = pd.read_csv(os.path.join(os.path.dirname(__file__), "monster_attack_suffixes.csv"))
#resist_mapping['clean'] = resist_mapping['inflicts'].str.lower().str.split(' ').str[0]
#resist_mapping = resist_mapping.drop(['inflicts', 'Unnamed: 0'], axis=1).set_index('suffix').squeeze().to_dict()

class MonsterSpoiler():
	def __init__(self, name, melee_attack_bundle, ranged_attack_bundle, death_attack_bundle, engulf_attack_bundle, passive_attack_bundle):
		self.name = ''
		self.melee_attack_bundle = melee_attack_bundle
		self.ranged_attack_bundle = ranged_attack_bundle
		self.death_attack_bundle = death_attack_bundle
		self.engulf_attack_bundle = engulf_attack_bundle
		self.passive_attack_bundle = passive_attack_bundle

class AttackBundle():
	always_matches = False
	prefix_set = set()
	dice_pattern = re.compile('([0-9]+)d([0-9]+)')
	digit_pattern = re.compile('[0-9]')
	suffix_pattern = re.compile('([^0-9\)\]]+)(?:\)|\])?$')

	class DamageTypes(NamedTuple): # some day we should disambiguate damage qualities and damage quantitie
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
			'b': ('blind', True),
			'c': ('confusion', True),
			'd': ('digest', True),
			'e': ('energy', False),
			'h': ('hallucination',True),
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
			'!I': ('int_drain', False),
			'!C': ('con_drain', False),
			'!S': ('str_drain', False),
			'!D': ('dex_drain', False),
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
			if a[0] in self.__class__.prefix_set or self.__class__.always_matches: # we care about this kind of attack
				self.num_attacks += 1
				suffix_match = re.search(self.__class__.suffix_pattern, a)	
				if suffix_match:
					damage_type = suffix_match[1]
					damage_types.append(damage_type)
					attack_does_physical_damage = self.__class__.DamageTypes.suffix_mapping[damage_type][1]
				else:
					attack_does_physical_damage = True # no suffix is normal attack

				damage_dice_match = re.search(self.__class__.dice_pattern, a)
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
			damage_type_dict[self.__class__.DamageTypes.suffix_mapping[t][0]] = True

		#print(damage_type_dict)
		self.damage_types = self.__class__.DamageTypes(**damage_type_dict)

class RangedAttackBundle(AttackBundle):
	prefix_set = set(['B', 'W', 'M', 'G', 'S'])

class DeathAttackBundle(AttackBundle):
	prefix_set = set(['['])

class MeleeAttackBundle(AttackBundle):
	#prefix_set = set('W', 'H', 'X', 'E') # what attacks should match both melee and ranged? TK
	always_matches = True

class PassiveAttackBundle(AttackBundle):
	prefix_set = set(['('])

class EngulfAttackBundle(AttackBundle):
	prefix_set = set(['E'])

monster_df = pd.read_csv(os.path.join(os.path.dirname(__file__), "monsters.csv"))
#monster_df.loc[monster_df['SPECIES'] == 'golden naga hatchlin', 'SPECIES'] = "golden naga hatchling"
#monster_df.loc[monster_df['SPECIES'] == 'guardian naga hatchl', 'SPECIES'] = "guardian naga hatchling"

monster_df=monster_df.set_index('SPECIES')

#monster_df.loc[monster_df.index == 'mind flayer', 'ATTACKS'] = "W1d4 2d1!I 2d1!I 2d1!I"
#monster_df.loc[monster_df.index == 'master mind flayer', 'ATTACKS'] = "W1d8 2d1!I 2d1!I 2d1!I 2d1!I 2d1!I"
#import pdb; pdb.set_trace()
#monster_df

#with open(os.path.join(os.path.dirname(__file__), "monsters_new.csv"), 'w') as f:
#	monster_df.to_csv(f)


# some special cases that I really should save into the csv
#monster_df[]

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

	spoiler = MonsterSpoiler(name, melee_bundle, ranged_bundle, death_bundle, engulf_bundle, passive_bundle)
	#print(name, melee_bundle.max_damage, ranged_bundle.max_damage)
	#print(name, {k:v for k,v in zip(melee_bundle.damage_types._fields, melee_bundle.damage_types) if v==True})
	MONSTERS_BY_NAME[name] = spoiler

