import pandas as pd
import os
from collections import defaultdict
from typing import NamedTuple
import re
import numpy as np
import enum

from utilities import ARS

import agents.representation.threat as threat
import agents.representation.constants as constants

class MonsterSpoiler():
    NORMAL_SPEED = 12

    def __init__(self, name, melee_attack_bundle, ranged_attack_bundle, death_attack_bundle, engulf_attack_bundle, passive_attack_bundle, level, max_level, AC, speed, MR, resists, tier):
        self.name = name
        self.tamed_by_meat = "dog" in name or "cat" in name or "kitten" in name
        self.tamed_by_veg = "horse" in name or "pony" in name
        self.melee_attack_bundle = melee_attack_bundle
        self.ranged_attack_bundle = ranged_attack_bundle
        self.death_attack_bundle = death_attack_bundle
        self.engulf_attack_bundle = engulf_attack_bundle
        self.passive_attack_bundle = passive_attack_bundle

        self.has_active_attacks = (self.melee_attack_bundle.num_attacks + self.ranged_attack_bundle.num_attacks) > 0

        self.level = level
        self.max_level = max_level
        self.AC = AC
        self.speed = speed
        self.MR = MR
        self.tier = tier

        self.resists = resists

    def passive_threat(self, character):
        passive_threat = threat.evaluate_threat(self.expected_passive_damage_to_character(character))
        return passive_threat

    def ranged_threat(self, character):
        ranged_threat = threat.evaluate_threat(self.expected_ranged_damage_to_character(character), character)
        return ranged_threat

    def melee_threat(self, character):
        melee_threat = threat.evaluate_threat(self.expected_melee_damage_to_character(character), character)
        return melee_threat

    def active_threat(self, character):
        ranged_threat = self.ranged_threat(character)
        melee_threat = self.melee_threat(character)

        return max(melee_threat, ranged_threat)

    def char_would_tussle_with(self, character):
        c = character
        ranged = self.expected_ranged_damage_to_character(c)
        melee = self.expected_melee_damage_to_character(c)
        active_danger_from_types = max(threat.evaluate_threat_type(ranged, c), threat.evaluate_threat_type(melee, c))
        active_danger_from_damage = max(threat.evaluate_threat_damage(ranged, c), threat.evaluate_threat_damage(melee, c))
        active_danger = max(active_danger_from_damage, active_danger_from_types)
        # if someone will just beat us up, we can't fret the passives too much
        if active_danger > threat.CharacterThreat.safe:
            return True

        # TK implement avoidance of deadly melee combatants (but pursuit of deadly ranged combatants that are weak in melee)
        cumulative_safety = threat.CharacterThreat.safe
        passive_damage = self.expected_passive_damage_to_character(c)
        # Don't evaluate passive damage TYPE because in general there is avoiding that
        # recall that floating eyes' paralysis will be recorded as damage damage so they will still be unsafe
        cumulative_safety = max(threat.evaluate_threat_damage(passive_damage, c), cumulative_safety)
        death_damage = self.expected_death_damage_to_character(c)
        cumulative_safety = max(threat.evaluate_threat_damage(death_damage, c), threat.evaluate_threat_type(death_damage, c), cumulative_safety)

        if cumulative_safety < threat.CharacterThreat.high:
            return True

        return False

    def expected_melee_damage_to_character(self, character):
        return self.melee_attack_bundle.expected_damage_to_character(character, self.max_level, self.speed)

    def expected_ranged_damage_to_character(self, character):
        return self.ranged_attack_bundle.expected_damage_to_character(character, self.max_level, self.speed)

    def expected_engulf_damage_to_character(self, character):
        return self.engulf_attack_bundle.expected_damage_to_character(character, self.max_level, self.speed)

    def expected_passive_damage_to_character(self, character):
        return self.passive_attack_bundle.expected_damage_to_character(character, self.max_level)

    def expected_death_damage_to_character(self, character):
        return self.death_attack_bundle.expected_damage_to_character(character, self.max_level)

    def actions_per_unit_time(self):
        # assume player has speed 12
        return self.speed / self.NORMAL_SPEED

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

class AttackDamage():
    def __init__(self, dice_damage, damage_type, can_miss, instrument) -> None:
        self.dice_damage = dice_damage
        self.damage_type = damage_type
        self.can_miss = can_miss
        self.instrument = instrument

    def expected_damage_to_character(self, character, mon_level, mon_speed=None):
        reflected = character.has_intrinsic(constants.Intrinsics.reflection) and (self.instrument == 'gaze' or self.instrument == 'breath')
        if reflected:
            return threat.Threat(0, 0)
        resisted = character.resists(self.damage_type)
        return self.expected_damage(mon_level, character.AC, resisted, character.speed(), mon_speed=mon_speed)

    def expected_damage(self, mon_level, AC, resisted, character_speed, mon_speed=None):
        if self.can_miss:
            if AC >= 0:
                hit_threshold = 10 + mon_level + AC
                damage_reduction = 0
            else:
                # random between -1 and AC (subtract AC here because negative)
                expected_AC = -1*(1-AC)/2
                hit_threshold = 10 + expected_AC + mon_level
                damage_reduction = (1-AC)/2

            # roll a d20, it must be below hit threshold
            chance_to_hit = max(5*(hit_threshold-1)/100, 0)
        else:
            damage_reduction = 0
            chance_to_hit = 1

        if self.dice_damage != 0:
            damage = max(self.dice_damage-damage_reduction,1)
        else:
            damage = max(self.dice_damage-damage_reduction,0)

        damage = damage * chance_to_hit
        # mon_speed might be None for non-active attacks
        if mon_speed is not None:
            damage *= mon_speed / character_speed
        if resisted and self.damage_type & ~threat.resist_but_additional:
            damage = 0

        # convention I might change later: damage_type will be non-zero even if the type is resisted
        # pushes the work of checking elsewhere
        return threat.Threat(damage, self.damage_type)

class AttackBundle():
    never_misses = True
    matches_no_prefix = False
    prefix_set = set()
    dice_pattern = re.compile('([0-9]+)d([0-9]+)')
    digit_pattern = re.compile('[0-9]')
    suffix_pattern = re.compile('([^0-9\)\]]+)(?:\)|\])?$')

    def expected_damage_to_character(self, character, level, mon_speed=None):
        cum_damage = 0
        damage_types = threat.ThreatTypes.NO_SPECIAL
        for attack in self.attack_damages:
            damage, damage_type = attack.expected_damage_to_character(character, level, mon_speed=mon_speed)
            cum_damage += damage
            damage_types |= damage_type
        return threat.Threat(cum_damage, damage_types)

    def __init__(self, attack_strs, name):
        self.attack_damages = []

        for a in attack_strs:
            if a[0] not in self.prefix_set and not (self.matches_no_prefix and re.match(self.digit_pattern, a[0])):
                # this type of attack doesn't apply to our bundle
                continue

            if re.match(self.digit_pattern, a[0]):
                prefix = None
                instrument = None
            else:
                prefix = a[0]
                instrument = prefix_instrument.get(prefix, None)

            suffix_match = re.search(self.suffix_pattern, a)
            damage_type = threat.ThreatTypes.NO_SPECIAL
            if suffix_match:
                damage_type = suffix_match[1]
                damage_type, attack_does_physical_damage = threat.csv_str_to_enum.get(damage_type, (threat.ThreatTypes.NO_SPECIAL, True))
            else:
                attack_does_physical_damage = True # no suffix == normal attack

            if name == 'grid bug':
                damage_type = threat.ThreatTypes.NO_SPECIAL

            damage_dice_match = re.search(self.dice_pattern, a)
            if not damage_dice_match:
                import pdb; pdb.set_trace()

            num_dice = int(damage_dice_match[1])
            num_sides = int(damage_dice_match[2])

            if attack_does_physical_damage:
                dice_damage = num_dice * (num_sides + 1)/2

                if instrument == 'weapon':
                    dice_damage += 4.5 # roughly approximate weapon damage as +1d8
            else:
                dice_damage = 0

            can_miss = True
            if self.never_misses:
                can_miss = False
            elif instrument == 'magic':
                can_miss = False
            elif instrument == 'explode':
                # technically dex affects these but whatever
                can_miss = False
            elif instrument == 'gaze':
                can_miss = False
            damage = AttackDamage(dice_damage, damage_type, can_miss, instrument)
            self.attack_damages.append(damage)

        self.num_attacks = len(self.attack_damages)

prefix_instrument = {
    'B': 'breath',
    'W': 'weapon',
    'M': 'magic', # never misses
    'G': 'gaze', # never misses
    'S': 'spit',
    'E': 'engulf', # can miss (fail to engulf) except once you are engulfed it can't
    'H': 'held',
    'X': 'explode'
}
class RangedAttackBundle(AttackBundle):
    prefix_set = set(['B', 'W', 'M', 'G', 'S'])

class DeathAttackBundle(AttackBundle):
    never_misses = True
    prefix_set = set(['['])

class MeleeAttackBundle(AttackBundle):
    #prefix_set = set(['B', 'E', 'G', 'H', 'M', 'S', 'W', 'X']) # what attacks should match both melee and ranged? TK
    prefix_set = set(['E', 'G', 'H', 'M', 'W', 'X'])
    matches_no_prefix = True

class PassiveAttackBundle(AttackBundle):
    never_misses = True
    prefix_set = set(['('])

class EngulfAttackBundle(AttackBundle):
    never_misses = True
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

    level = int(row['LVL'])
    if name == 'Wizard of Yendor':
        max_level = 49
    elif name in ['Demogorgon', 'Asmodeus', 'Baalzebub', 'Dispater', 'Geryon', 'Orcus', 'Yeenoghu', 'Juiblex']:
        max_level = level
    else:
        max_level = np.floor(level*1.5)


    if row['ATTACKS'] is np.nan:
        attack_strs = []
    else:
        attack_strs = row["ATTACKS"].split(' ')
    ranged_bundle = RangedAttackBundle(attack_strs, name)
    melee_bundle = MeleeAttackBundle(attack_strs, name)
    passive_bundle = PassiveAttackBundle(attack_strs, name)
    engulf_bundle = EngulfAttackBundle(attack_strs, name)
    death_bundle = DeathAttackBundle(attack_strs, name)

    AC = row['AC']
    speed = row['SPD']
    MR = row['MR']
    tier = row['TIER']
    resists = Resists.NONE
    if row['RESISTS'] is not np.nan:
        for character in row['RESISTS'].upper():
            resists |= RESIST_MAPPING[character]

    spoiler = MonsterSpoiler(name, melee_bundle, ranged_bundle, death_bundle, engulf_bundle, passive_bundle, level, max_level, AC, speed, MR, resists, tier)
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
