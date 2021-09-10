from typing import Optional
from typing import NamedTuple

import pandas as pd
from dataclasses import dataclass

import constants
import inventory as inv

@dataclass
class Character():
    base_race: str
    base_class: str
    base_sex: str
    base_alignment: str
    AC: int = None
    current_hp: int = None
    max_hp: int = None
    inventory: inv.PlayerInventory = None
    attributes: constants.Attributes = None
    last_pray_time: Optional[int] = None
    last_pray_reason: Optional[str] = None
    experience_level: int = 1
    class_skills: pd.Series = None
    innate_intrinsics: constants.Intrinsics = constants.Intrinsics.NONE
    noninnate_intrinsics: constants.Intrinsics = constants.Intrinsics.NONE
    afflicted_with_lycanthropy: bool = False
    can_enhance: bool = False

    def set_class_skills(self):
        self.class_skills = constants.CLASS_SKILLS[self.base_class.value]

    def set_innate_intrinsics(self):
        new_intrinsics = constants.Intrinsics.NONE
        for level in range(1, self.experience_level + 1):
            # TODO eventually use enums anywhere and skip the BaseRace[..] lookups
            race_intrinsics = constants.RACE_TO_INTRINSIC[self.base_race].get(level, constants.Intrinsics.NONE)
            role_intrinsics = constants.ROLE_TO_INTRINSIC[self.base_class].get(level, constants.Intrinsics.NONE)
            new_intrinsics = new_intrinsics | race_intrinsics | role_intrinsics
        self.innate_intrinsics = new_intrinsics

    def has_intrinsic(self, intrinsic):
        return bool((self.innate_intrinsics | self.noninnate_intrinsics) & intrinsic)

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

    def set_attributes(self, attributes):
        self.attributes = attributes

    def set_inventory(self, inventory):
        self.inventory = inventory

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

    def ready_for_mines(self):
        return self.experience_level > 8

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