import enum
from typing import NamedTuple

GLYPHS_SHAPE = (21, 79)

class TerrainProperties(enum.Flag):
    NONE = 0
    wall = enum.auto()
    #room = enum.auto() # something that could be inside a room
    #corridor = enum.auto()
    door = enum.auto()
    liquid = enum.auto()
    trap = enum.auto()
    secret_friendly = enum.auto()

class BaseRole(enum.Enum):
    Archeologist = 'Archeologist'
    Barbarian = 'Barbarian'
    Caveperson = 'Caveperson'
    Healer = 'Healer'
    Knight = 'Knight'
    Monk = 'Monk'
    Priest = 'Priest'
    Ranger = 'Ranger'
    Rogue = 'Rogue'
    Samurai = 'Samurai'
    Tourist = 'Tourist'
    Valkyrie = 'Valkyrie'
    Wizard = 'Wizard'

class BaseRace(enum.Enum):
    dwarf = 'dwarf'
    elf = 'elf'
    gnome = 'gnome'
    human = 'human'
    orc = 'orc'

class Attributes(NamedTuple):
    strength: int
    strength_pct: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    @staticmethod
    def strength_to_hit(strength, strength_pct):
        if strength < 6: return -2
        elif strength < 8: return -1
        elif strength < 17: return 0
        elif strength == 18 and strength_pct < 51: return +1
        elif strength == 18 and strength_pct < 100: return +2
        else: return +3

    @staticmethod
    def dexterity_to_hit(dexterity):
        if dexterity < 4: return -3
        elif dexterity < 6: return -2
        elif dexterity < 8: return  -1
        elif dexterity < 15: return 0
        else: return dexterity-14 # increases by 1 each step from 15 and up

    @staticmethod
    def strength_damage(strength, strength_pct):
        if strength < 6: return -1
        elif strength < 16: return 0
        elif strength < 18: return +1
        elif strength == 18 and strength_pct == 0: return +2
        elif strength == 18 and strength_pct < 76: return +3
        elif strength == 18 and strength_pct < 91: return +4
        elif strength == 18 and strength_pct < 100: return +5
        else: return +6

    def melee_to_hit_modifiers(self):
        return self.strength_to_hit(self.strength, self.strength_pct) + self.dexterity_to_hit(self.dexterity)

    def melee_damage_modifiers(self):
        return self.strength_damage(self.strength, self.strength_pct)

class Intrinsics(enum.Flag):
    NONE = 0
    fire_resistance = enum.auto()
    cold_resistance = enum.auto()
    sleep_resistance = enum.auto()
    disint_resistance = enum.auto()
    shock_resistance = enum.auto()
    poison_resistance = enum.auto()
    regeneration = enum.auto()
    searching = enum.auto()
    see_invisible = enum.auto()
    invisible = enum.auto()
    teleportitis = enum.auto()
    teleport_control = enum.auto()
    polymorphitis = enum.auto()
    levitation = enum.auto()
    stealth = enum.auto()
    aggravate_monster = enum.auto()
    conflict = enum.auto()
    protection = enum.auto()
    protection_from_shape_changers = enum.auto()
    warning = enum.auto()
    hunger = enum.auto()
    telepathy = enum.auto()
    speed = enum.auto()
    food_appraisal = enum.auto()
    magical_breathing = enum.auto()
    amphibiousness = enum.auto()
    jumping = enum.auto()
    infravision = enum.auto()

ROLE_TO_INTRINSIC = {
    BaseRole.Archeologist: {
        1: Intrinsics.speed | Intrinsics.stealth,
        10: Intrinsics.searching,
    },
    BaseRole.Barbarian: {
        1: Intrinsics.poison_resistance,
        7: Intrinsics.speed,
        15: Intrinsics.stealth,
    },
    BaseRole.Caveperson: {
        7: Intrinsics.speed,
        15: Intrinsics.warning,
    },
    BaseRole.Healer: {
        1: Intrinsics.poison_resistance,
        15: Intrinsics.warning,
    },
    BaseRole.Knight: {
        1: Intrinsics.jumping,
        7: Intrinsics.speed,
    },
    BaseRole.Monk: {
        1: Intrinsics.see_invisible | Intrinsics.sleep_resistance | Intrinsics.speed,
        3: Intrinsics.poison_resistance,
        5: Intrinsics.stealth,
        7: Intrinsics.warning,
        9: Intrinsics.searching,
        11: Intrinsics.fire_resistance,
        13: Intrinsics.cold_resistance,
        15: Intrinsics.shock_resistance,
        17: Intrinsics.teleport_control,
    },
    BaseRole.Priest: {
        15: Intrinsics.warning,
        10: Intrinsics.fire_resistance,
    },
    BaseRole.Ranger: {
        1: Intrinsics.searching,
        7: Intrinsics.stealth,
        15: Intrinsics.see_invisible,
    },
    BaseRole.Rogue: {
        1: Intrinsics.stealth,
        10: Intrinsics.searching,
    },
    BaseRole.Samurai: {
        1: Intrinsics.speed,
        15: Intrinsics.stealth,
    },
    BaseRole.Tourist: {
        10: Intrinsics.searching,
        20: Intrinsics.poison_resistance,
    },
    BaseRole.Valkyrie: {
        1: Intrinsics.cold_resistance | Intrinsics.stealth,
        7: Intrinsics.speed,
    },
    BaseRole.Wizard: {
        15: Intrinsics.warning,
        17: Intrinsics.teleport_control,
    },
}

RACE_TO_INTRINSIC = {
    BaseRace.dwarf: {
        1: Intrinsics.infravision,
    },
    BaseRace.elf: {
        1: Intrinsics.infravision,
        4: Intrinsics.sleep_resistance,
    },
    BaseRace.gnome: {
        1: Intrinsics.infravision,
    },
    BaseRace.human: {},
    BaseRace.orc: {
        1: Intrinsics.infravision| Intrinsics.poison_resistance,
    },
}