from typing import Optional
from typing import NamedTuple

import pandas as pd
import numpy as np
from dataclasses import dataclass, field

import nle.nethack as nethack
import environment

import agents.representation.constants as constants
import agents.representation.glyphs as gd
import agents.representation.inventory as inv
import agents.representation.monster_messages as monster_messages
import agents.representation.threat as threat
import agents.advice.preferences as preferences

from utilities import ARS

@dataclass
class HeldBy():
    time_held: int
    monster_glyph: gd.MonsterGlyph
    #monster_square: Tuple[int, int]

@dataclass
class Character():
    base_race: str
    base_class: str
    base_sex: str
    base_alignment: str
    AC: int = None
    current_hp: int = None
    max_hp: int = None
    current_energy: int = None
    inventory: inv.PlayerInventory = None
    attributes: constants.Attributes = None
    last_pray_time: Optional[int] = None
    last_pray_reason: Optional[str] = None
    experience_level: int = 1
    tier: int = 9
    role_tier_mod: int = 0
    class_skills: dict = None
    relevant_skills: dict = None
    innate_intrinsics: constants.Intrinsics = constants.Intrinsics.NONE
    noninnate_intrinsics: constants.Intrinsics = constants.Intrinsics.NONE
    afflicted_with_lycanthropy: bool = False
    can_enhance: bool = False
    held_by: HeldBy = None
    near_burdened: bool = False
    carrying_too_much_for_diagonal: bool = False
    executing_ranged_plan: bool = False
    executing_escape_plan: bool = False
    gold: int = 0
    hunger_state: int = 1
    encumberance: int = 0
    global_identity_map: gd.GlobalIdentityMap = None
    queued_wish_name: tuple = None
    wish_in_progress: tuple = None
    blinding_attempts: dict = field(default_factory=dict)
    spells: list =  field(default_factory=list)

    def set_class_skills(self):
        self.class_skills = constants.CLASS_SKILLS[self.base_class.value].to_dict()
        self.relevant_skills = constants.CLASS_SKILLS[self.base_class.value + "-relevant"].to_dict()

    def set_base_spells(self):
        if self.base_class == constants.BaseRole.Wizard:
            self.spells = ['force bolt']
        if self.base_class == constants.BaseRole.Healer:
            self.spells = ['healing']

    def make_global_identity_map(self):
        self.global_identity_map = gd.GlobalIdentityMap(self.base_class == constants.BaseRole.Priest)

    intrinsic_gain_messages = {
        "You speed up": constants.Intrinsics.speed,
        "You feel healthy": constants.Intrinsics.poison_resistance,
        "You feel especially healthy": constants.Intrinsics.poison_resistance,
        "You feel a strange mental acuity": constants.Intrinsics.telepathy,
        "You feel wide awake": constants.Intrinsics.sleep_resistance,
        "You feel full of hot air": constants.Intrinsics.fire_resistance,
    }

    def listen_for_intrinsics(self, message):
        for k,v in self.intrinsic_gain_messages.items():
            if k in message:
                if self.has_intrinsic(v) and environment.env.debug:
                    import pdb; pdb.set_trace()

                self.add_noninnate_intrinsic(v)

    def add_noninnate_intrinsic(self, intrinsic):
        self.noninnate_intrinsics |= intrinsic

    def set_innate_intrinsics(self):
        new_intrinsics = constants.Intrinsics.NONE
        for level in range(1, self.experience_level + 1):
            # TODO eventually use enums anywhere and skip the BaseRace[..] lookups
            race_intrinsics = constants.RACE_TO_INTRINSIC[self.base_race].get(level, constants.Intrinsics.NONE)
            role_intrinsics = constants.ROLE_TO_INTRINSIC[self.base_class].get(level, constants.Intrinsics.NONE)
            new_intrinsics = new_intrinsics | race_intrinsics | role_intrinsics
        self.innate_intrinsics = new_intrinsics

    def has_intrinsic(self, intrinsic):
        if self.inventory is None:
            intrinsics = (self.innate_intrinsics | self.noninnate_intrinsics)
        else:
            intrinsics = (self.innate_intrinsics | self.noninnate_intrinsics | self.inventory.extrinsics)
        return bool(intrinsics & intrinsic)

    def resists(self, damage_type):
        relevant_resistances = threat.threat_to_resist.get(damage_type, [])
        if not isinstance(relevant_resistances, list): relevant_resistances = [relevant_resistances]

        for r in relevant_resistances:
            if self.has_intrinsic(r):
                return True
        return False

    def speed(self):
        # TK know about burden
        if self.has_intrinsic(constants.Intrinsics.extrinsic_speed):
            return 20
        if self.has_intrinsic(constants.Intrinsics.speed):
            return 16
        return 12

    def wants_excalibur(self):
        if not self.base_alignment == 'lawful': return False
        return self.relevant_skills['long sword'] == True

    def hankering_for_excalibur(self):
        if self.global_identity_map.generated_artifacts['Excalibur'] == True:
            return False
        if self.wants_excalibur() == False:
            return False
        if self.experience_level < 5:
            return False

        #if not self.has_intrinsic(constants.Intrinsics.poison_resistance):
        #    return False
        long_sword = self.inventory.get_item(inv.Weapon, name='long sword', instance_selector=lambda i: not i.identity.is_artifact)
        return long_sword is not None

    def update_from_observation(self, blstats):
        old_experience_level = self.experience_level
        self.experience_level = blstats.get('experience_level')
        if not self.experience_level >= 1:
            raise Exception("Surprising experience level")
        if old_experience_level != self.experience_level: # Just to save us some effort
            self.set_innate_intrinsics()

        old_attributes = self.attributes
        new_attributes = blstats.make_attributes()
        if new_attributes != old_attributes:
            self.attributes = new_attributes

        old_hp = self.current_hp
        if old_hp != blstats.get('hitpoints'):
            self.current_hp = blstats.get('hitpoints')

        old_max_hp = self.max_hp
        if old_max_hp != blstats.get('max_hitpoints'):
            self.max_hp = blstats.get('max_hitpoints')

        old_AC = self.AC
        if old_AC != blstats.get('armor_class'):
            self.AC = blstats.get('armor_class')

        old_gold = self.gold
        if old_gold != blstats.get('gold'):
            self.gold = blstats.get('gold')

        old_hunger_state = self.hunger_state
        if old_hunger_state != blstats.get('hunger_state'):
            self.hunger_state = blstats.get('hunger_state')

        old_encumberance = self.encumberance
        if old_encumberance != blstats.get('encumberance'):
            self.encumberance = blstats.get('encumberance')

        old_energy = self.current_energy
        if old_energy != blstats.get('energy'):
            self.current_energy = blstats.get('energy')

    def want_less_weight(self):
        if self.near_burdened or self.carrying_too_much_for_diagonal:
            return True
        return self.encumberance > 0

    def clear_weight_knowledge(self):
        self.near_burdened = False
        self.carrying_too_much_for_diagonal = False

    def update_from_message(self, message_text, time):
        if "You feel feverish." in message_text:
            self.afflicted_with_lycanthropy = True

        if "You feel purified." in message_text:
            self.afflicted_with_lycanthropy = False

        try:
            self.update_held_by_from_message(message_text, time)
        except Exception as e:
            print(f"Exception while finding holding monster. Are we hallu? {e}")

        self.garbage_collect_camera_shots(time)

    def update_held_by_from_message(self, message_text, time):
        monster_name = None

        possible_grabs = [monster_messages.RecordedSeaMonsterGrab.involved_monster(message_text),
        monster_messages.RecordedMonsterGrab.involved_monster(message_text),
        monster_messages.RecordedCannotEscape.involved_monster(message_text)]

        monster_name = next((name for name in possible_grabs if name is not None), None)

        sticky_monster_messages = [("was a large mimic", "large mimic"),
        ("was a giant mimic", "giant mimic"),
        ("The large mimic hits!", "large mimic"),
        ("The giant mimic hits!", "giant mimic"),
        ("The lichen touches you!", "lichen"),
        ("The violet fungus touches you!", "violet fungus"),]

        for sticky_message, name in sticky_monster_messages:
            if sticky_message in message_text:
                monster_name = name

        if monster_name is not None:
            if monster_name.lower() == "it":
                monster_name = "invisible monster"
            self.held_by = HeldBy(time, gd.GLYPH_NAME_LOOKUP[monster_name])

        possible_releases = [monster_messages.RecordedPullFree.involved_monster(message_text),
        monster_messages.RecordedRelease.involved_monster(message_text)]

        relase_name = next((name for name in possible_releases if name is not None), None)
        if relase_name is not None:
            self.held_by = None

        if "You feel more confident" in message_text or "could be more dangerous" in message_text:
            self.can_enhance = True

        if "more skilled" in message_text or "most skilled" in message_text:
            print(message_text)
            if "more dangerous" not in message_text:
                self.can_enhance = False

    def set_attributes(self, attributes):
        self.attributes = attributes

    def update_inventory_from_observation(self, character, am_hallu, observation):
        if self.inventory and ((observation['inv_strs'] == self.inventory.inv_strs).all()):
            return

        inv_strs = observation['inv_strs'].copy()
        inv_letters = observation['inv_letters'].copy()
        inv_oclasses = observation['inv_oclasses'].copy()

        inv_glyphs = None
        if not am_hallu:
            inv_glyphs = observation['inv_glyphs'].copy()

        self.inventory = inv.PlayerInventory(character.global_identity_map, inv_letters, inv_oclasses, inv_strs, inv_glyphs=inv_glyphs)

    def can_cannibalize(self):
        if self.base_race == constants.BaseRace.orc:
            return False
        if self.base_class == constants.BaseRole.Caveperson:
            return False
        return True

    def sick_from_tripe(self):
        if self.base_class == constants.BaseRole.Caveperson:
            return False
        return True

    def prefer_ranged(self):
        if self.base_class == constants.BaseRole.Tourist:
            if not isinstance(self.inventory.wielded_weapon, inv.BareHands):
                return False
            quivered = self.inventory.quivered
            return quivered is not None and quivered.enhancement == 2 and quivered.identity.name() == 'dart'
        if self.base_class == constants.BaseRole.Ranger:
            quivered = self.inventory.quivered
            return quivered is not None and quivered.enhancement == 2 and quivered.identity.name() == 'arrow'

        return False

    def ready_for_mines(self):
        #if self.base_class == constants.BaseRole.Caveperson: return True
        return self.experience_level > 9
    
    def eager_for_mines1(self):
        return self.base_class == constants.BaseRole.Caveperson

    def attempted_to_blind(self, monster, time):
        self.blinding_attempts[monster] = time
        print(self.blinding_attempts)

    def garbage_collect_camera_shots(self, time):
        self.blinding_attempts = {k:v for k,v in self.blinding_attempts.items() if v >= time - 10}

    def scared_by(self, monster):
        if isinstance(monster, gd.InvisibleGlyph):
            return True
        if not isinstance(monster, gd.MonsterGlyph):
            return False

        spoiler = monster.monster_spoiler
        is_scary = max(spoiler.active_threat(self)) > threat.CharacterThreat.low
        #if is_scary: import pdb; pdb.set_trace()
        return is_scary
    
    unsafe_hp_loss = 0.5
    def death_by_passive(self, spoiler):
        trajectory = self.average_time_to_kill_monster_in_melee(spoiler)
        looks_like_death = spoiler.passive_damage_over_encounter(self, trajectory) + spoiler.death_damage_over_encounter(self) > self.unsafe_hp_loss * self.current_hp
        #if looks_like_death: import pdb; pdb.set_trace()
        return looks_like_death

    exp_lvl_to_max_mazes_lvl = {
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        5: 2,
        6: 4,
        7: 6,
    }

    def comfortable_depth(self):
        return self.exp_lvl_to_max_mazes_lvl.get(self.experience_level, 60)

    def desire_to_eat_corpses(self, neighborhood):
        # not if we're satiated
        if self.hunger_state == 0: return False
        # not if we're in a store
        if neighborhood.in_shop: return False
        return True

    def desperate_for_food(self):
        if self.hunger_state == 0:
            return False 

        if self.hunger_state == 1 and self.inventory.get_nutrition(self) > 0:
            return False

        if self.inventory.get_nutrition(self) >= 1_000:
            return False

        return True

    @staticmethod
    def charisma_price_multiplier(charisma):
        if charisma <= 5: return 2
        elif charisma < 8: return 1.5
        elif charisma < 11: return 4/3
        elif charisma < 16: return 1
        elif charisma < 18: return 0.75
        elif charisma < 19: return 2/3
        elif charisma >= 19: return 1/2

    def am_dupe(self):
        # shirt without body armor/cloak
        # tourist < exp 15
        # dunce cap
        if self.base_class == constants.BaseRole.Tourist and self.experience_level < 15:
            return True

        return False

    def find_base_price_from_sell(self, item, price):
        dupe_mult = 3 if self.am_dupe() else 2
        base1 = price * dupe_mult
        base2 = np.ceil(price * dupe_mult * 4/3)
        base3 = np.floor(price * dupe_mult * 4/3)
        base4 = base1 - 1

        if np.round(base2/2 * 3/4) == price:
            base_prices = [base1, base2, base4]
        elif np.round(base3/2 * 3/4) == price:
            base_prices = [base1, base3, base4]
        else:
            base_prices = [base1, base4]

        base_prices = set(base_prices)

        if isinstance(item, inv.Armor):
            # enhancement affects base price of armor
            for p in base_prices:
                base_prices = base_prices.union(set([p - 10*x for x in range(0,6)]))
        return base_prices

    def find_base_price_from_listed(self, item, price):
        cha_mult = self.charisma_price_multiplier(self.attributes.charisma)
        dupe_mult = 4/3 if self.am_dupe() else 1
        unidentified_surcharge = 4/3 # gems are different but we catch those ahead of time

        base1 = price / (cha_mult * dupe_mult)
        base2 = price / (cha_mult * dupe_mult * unidentified_surcharge)

        base_prices = [np.ceil(base1), np.floor(base1), np.ceil(base2), np.floor(base2)]
        if base2 <= 5:
            base_prices.append(0)

        base_prices = set(base_prices)

        if isinstance(item, inv.Armor):
            # enhancement affects base price of armor
            for p in base_prices:
                base_prices = base_prices.union(set([p - 10*x for x in range(0,6)]))

        return base_prices

    def body_armor_penalty(self):
        if self.base_class == constants.BaseRole.Monk:
            return True
        return False

    def actions_per_unit_time(self):
        base_speed = 12
        speed = 16 if self.has_intrinsic(constants.Intrinsics.speed) else base_speed

        # TK boots of speed
        return speed/base_speed

    def melee_to_hit(self, monster):
        to_hit = 1 # melee has base 1

        to_hit += self.to_hit_modifiers()
        to_hit += self.attributes.melee_to_hit_modifiers()
        #to_hit += self.skills.to_hit_modifiers()
        to_hit += self.inventory.to_hit_modifiers(self, monster)

        return to_hit

    def to_hit_modifiers(self):
        to_hit = self.experience_level
        if self.experience_level == 1 or self.experience_level == 2:
            to_hit += 1

        if self.base_class == constants.BaseRole.Monk:
            armaments = self.inventory.get_slots('armaments')
            if armaments.suit is None and armaments.off_hand is None: # TK check if our off-hand is genuinely a shield
                to_hit += self.experience_level / 3 + 2

        return to_hit

    class KillTrajectory(NamedTuple):
        time_to_kill: float
        swings_to_kill: float
        hits_to_kill: float

    def average_time_to_kill_monster_in_melee(self, monster_spoiler):
        melee_hit_probability = min(self.melee_to_hit(monster_spoiler)/20, 1)
        melee_hit_probability = max(0, melee_hit_probability)

        weapon = self.inventory.wielded_weapon
        damage = weapon.melee_damage(self, monster_spoiler)

        # TK damage from skills
        damage += self.attributes.melee_damage_modifiers()
        damage = max(damage, 1)
        hits_to_kill = monster_spoiler.average_hp() / damage
        swings_to_kill = hits_to_kill / melee_hit_probability
        time_to_kill = swings_to_kill / self.actions_per_unit_time()

        return self.KillTrajectory(time_to_kill, swings_to_kill, hits_to_kill)

    def _dump_threatening_monsters(self):
        danger_rows = []
        columns = ["monster", "time_to_kill", "swings_to_kill", "hits_to_kill", "monster dps", "is dangerous"]
        for n in gd.MonsterGlyph.numerals():
            g = gd.GLYPH_NUMERAL_LOOKUP[n]
            g.monster_spoiler.dangerous_to_player(self)
            danger_row = [g.monster_spoiler.name] + list(self.average_time_to_kill_monster_in_melee(g.monster_spoiler)) + [g.monster_spoiler.melee_dps(self.AC), g.monster_spoiler.dangerous_to_player(self)]
            danger_rows.append(danger_row)
            #pdb.set_trace()

        return pd.DataFrame(danger_rows, columns=columns)

    def get_ranged_attack(self, preference):
        if preference.includes(preferences.RangedAttackPreference.wand):
            wand_attack = self.inventory.get_wand_attack(preference)
            if wand_attack is not None:
                return wand_attack
        if preference.includes(preferences.RangedAttackPreference.spell):
            spell_attack = self.get_spell_attack(preference)
            if spell_attack is not None:
                return spell_attack
        return self.inventory.get_ranged_weapon_attack(preference)
    
    def get_spell_attack(self, preference):
        if self.current_energy is None or self.current_energy < 5:
                return None
        if self.hunger_state > 2:
            return None
        if 'force bolt' in self.spells and preference.includes(preferences.RangedAttackPreference.striking):
            attack_plan = inv.RangedAttackPlan(attack_action=nethack.actions.Command.CAST, attack_item='force bolt')
            proposal = inv.RangedPreparednessProposal(attack_plan=attack_plan)
            return proposal
        return None

    def prefer_ranged(self):
        if not self.inventory.wielded_weapon.uses_relevant_skill(self):
            return True
        if self.base_class == constants.BaseRole.Tourist and self.current_hp < 30:
            return True
        return False