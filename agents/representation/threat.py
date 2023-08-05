import enum
from agents.representation.constants import Intrinsics
from typing import NamedTuple

class CharacterThreat(enum.IntEnum):
    safe = 0
    low = 1
    high = 2
    deadly = 3

class ThreatTypes(enum.IntFlag):
    NO_SPECIAL = 0
    # deadly
    DISINTEGRATE = enum.auto()
    WRAP         = enum.auto()
    STONE        = enum.auto()
    SLIME        = enum.auto() # both SLIME and LYCAN represented by @ in csv
    DISEASE      = enum.auto()
    RIDER  = enum.auto()
    # really bad
    PARALYSIS    = enum.auto()
    SLEEP        = enum.auto()
    LYCAN        = enum.auto()
    D_INT        = enum.auto()
    # quite bad
    STUN   = enum.auto()
    SPELL  = enum.auto()
    DIGEST = enum.auto() # can kill you if you wait really long ...
    # sometimes bad
    SHOCK  = enum.auto()
    FIRE   = enum.auto()
    COLD   = enum.auto()
    POISON = enum.auto()
    SLOW   = enum.auto()
    BLIND  = enum.auto()
    STICK  = enum.auto()
    DRAIN  = enum.auto()
    # not bad in practice
    INTRINSIC = enum.auto()
    ENERGY    = enum.auto()
    TELEPORT  = enum.auto()
    D_DEX     = enum.auto()
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
    # not special
    MISSILES = enum.auto()

# these two attacks can be resisted but don't have their base damage negated when they are
resist_but_additional = ThreatTypes.POISON | ThreatTypes.DRAIN

class Threat(NamedTuple):
    damage: int
    threat_type: ThreatTypes

class ThreatLevels(enum.Enum):
    deadly = ThreatTypes.DISINTEGRATE | ThreatTypes.WRAP | ThreatTypes.STONE | ThreatTypes.SLIME | ThreatTypes.DISEASE | ThreatTypes.RIDER
    really_bad = ThreatTypes.PARALYSIS | ThreatTypes.SLEEP | ThreatTypes.LYCAN | ThreatTypes.D_INT
    mid_bad = ThreatTypes.STUN | ThreatTypes.SPELL | ThreatTypes.DIGEST
    little_bad = ThreatTypes.SHOCK | ThreatTypes.FIRE | ThreatTypes.COLD | ThreatTypes.POISON | ThreatTypes.SLOW | ThreatTypes.BLIND  | ThreatTypes.DRAIN
    not_bad = ThreatTypes.INTRINSIC | ThreatTypes.ENERGY | ThreatTypes.TELEPORT | ThreatTypes.D_DEX | ThreatTypes.STICK
    degrading = ThreatTypes.DISENCHANT | ThreatTypes.RUST | ThreatTypes.ROT
    annoying = ThreatTypes.STEAL | ThreatTypes.SEDUCE | ThreatTypes.HALLU | ThreatTypes.CONF | ThreatTypes.PRICK
    mild_annoying = ThreatTypes.GOLD

def evaluate_threat_type(threat, character):
    _, threat_types = threat
    # remove threats that we resist
    for intrinsic, threat in resist_to_threat.items():
        if character.has_intrinsic(intrinsic):
            threat_types &= ~threat

    present_levels = []
    for level in ThreatLevels:
        if level.value & threat_types:
            present_levels.append(level)
    present_levels = set(present_levels)

    if ThreatLevels.deadly in present_levels or ThreatLevels.really_bad in present_levels:
        return CharacterThreat.deadly

    if ThreatLevels.mid_bad in present_levels or ThreatLevels.annoying in present_levels or ThreatLevels.little_bad in present_levels or ThreatLevels.degrading in present_levels:
        return CharacterThreat.high

    return CharacterThreat.safe

def evaluate_threat_damage(threat, character):
    damage_threat, _ = threat

    if damage_threat >= character.current_hp * 0.5:
        return CharacterThreat.deadly

    if damage_threat >= character.current_hp * 0.15:
        return CharacterThreat.high

    if damage_threat > 0:
        return CharacterThreat.low

    return CharacterThreat.safe

def evaluate_threat(threat, character):
    return (evaluate_threat_damage(threat,character), evaluate_threat_type(threat,character))

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
    ThreatTypes.PARALYSIS: Intrinsics.free_action,
    ThreatTypes.MISSILES: Intrinsics.magic_resistance,
}

resist_to_threat = {}
for k,v in threat_to_resist.items():
    if not isinstance(v, list):
        v = [v]
    for res in v:
        resist_to_threat[res] = k

# 1st bool = does the attack do HP damage as well?
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
    '.': (ThreatTypes.PARALYSIS, True), # the all important decision to pretend paralysis causes damage so we are very scared of floating eyes
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
    'M': (ThreatTypes.MISSILES, True)
}