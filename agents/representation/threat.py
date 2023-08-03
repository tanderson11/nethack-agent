import enum
from agents.representation.constants import Intrinsics

class Threat(enum.IntEnum):
    safe = 0
    low = 1
    high = 2
    deadly = 3

class ThreatTypes(enum.IntFlag):
    NO_SPECIAL = 0
    # really bad
    DISINTEGRATE = enum.auto()
    WRAP         = enum.auto()
    D_INT        = enum.auto()
    STONE        = enum.auto()
    SLIME        = enum.auto() # both SLIME and LYCAN represented by @ in csv
    LYCAN        = enum.auto()
    DISEASE      = enum.auto()
    PARALYSIS    = enum.auto()
    SLEEP        = enum.auto()
    # quite bad
    STUN   = enum.auto()
    SPELL  = enum.auto()
    RIDER  = enum.auto()
    DIGEST = enum.auto() # can kill you if you wait really long ...
    # mild bad
    SHOCK  = enum.auto()
    FIRE   = enum.auto()
    COLD   = enum.auto()
    POISON = enum.auto()
    D_DEX  = enum.auto()
    SLOW   = enum.auto()
    BLIND  = enum.auto()
    STICK  = enum.auto()
    # not bad in practice
    INTRINSIC = enum.auto()
    ENERGY    = enum.auto()
    DRAIN     = enum.auto()
    TELEPORT  = enum.auto()
    # degrading
    DISENCHANT = enum.auto()
    RUST       = enum.auto()
    ROT        = enum.auto()
    # really annoying
    STEAL  = enum.auto()
    SEDUCE = enum.auto()
    HALLU  = enum.auto()
    CONF   = enum.auto()
    PRICK  = enum.auto()
    # mild annoying
    GOLD = enum.auto()

threat_to_resist = {
    ThreatTypes.DISINTEGRATE: Intrinsics.disint_resistance,
    ThreatTypes.FIRE: Intrinsics.fire_resistance,
    ThreatTypes.COLD: Intrinsics.cold_resistance,
    ThreatTypes.SLEEP: Intrinsics.sleep_resistance,
    ThreatTypes.SHOCK: Intrinsics.shock_resistance,
    ThreatTypes.POISON: Intrinsics.poison_resistance,
    ThreatTypes.D_DEX: Intrinsics.poison_resistance,
    ThreatTypes.BLIND: Intrinsics.telepathy,
    ThreatTypes.WRAP: [Intrinsics.magical_breathing, Intrinsics.amphibiousness],
}

# bool = does the attack do HP damage as well?
csv_str_to_enum = {
    'C': (ThreatTypes.COLD, True),
    'D': (ThreatTypes.DISINTEGRATE, True),
    'E': (ThreatTypes.SHOCK, True),
    'F': (ThreatTypes.FIRE, True),
    'P': (ThreatTypes.POISON, True),
    'R': (ThreatTypes.RUST, True),
    'S': (ThreatTypes.SLEEP, True),
    'V': (ThreatTypes.DRAIN, True),
    'b': (ThreatTypes.BLIND, False),
    'c': (ThreatTypes.CONF, True),
    'd': (ThreatTypes.DIGEST, True),
    'e': (ThreatTypes.ENERGY, False),
    'h': (ThreatTypes.HALLU, False),
    'i': (ThreatTypes.INTRINSIC, True),
    'm': (ThreatTypes.STICK, True),
    'r': (ThreatTypes.ROT, True),
    's': (ThreatTypes.STUN, True),
    't': (ThreatTypes.TELEPORT, True),
    'w': (ThreatTypes.WRAP, True),
    'x': (ThreatTypes.PRICK, True),
    'z': (ThreatTypes.RIDER, True),
    '.': (ThreatTypes.PARALYSIS, True),
    '+': (ThreatTypes.SPELL, True),
    '-': (ThreatTypes.STEAL, True),
    '"': (ThreatTypes.DISENCHANT, True),
    '&': (ThreatTypes.SEDUCE, True),
    '<': (ThreatTypes.SLOW, True),
    '!I': (ThreatTypes.D_INT, False),
    '!D': (ThreatTypes.D_DEX, True),
    '#': (ThreatTypes.DISEASE, True),
    '$': (ThreatTypes.GOLD, False),
    '*': (ThreatTypes.STONE, True),
    '@': (ThreatTypes.LYCAN, True), # OR SLIME!
}