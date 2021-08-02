import enum

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