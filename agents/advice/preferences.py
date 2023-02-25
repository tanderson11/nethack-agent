import enum
from agents.representation.constants import BaseRole

class RangedAttackPreference(enum.Flag):
    wand = enum.auto()
    spell = enum.auto()
    death = enum.auto()
    striking = enum.auto()
    sleep = enum.auto()
    setup = enum.auto()
    strong = enum.auto()
    weak = enum.auto()
    adjacent = enum.auto()

    def includes(self, flag):
        return self & flag == flag

ranged_default = ~RangedAttackPreference.wand & ~RangedAttackPreference.adjacent & ~RangedAttackPreference.weak
#ranged_powerful = ~RangedAttackPreference.setup & ~RangedAttackPreference.death
ranged_powerful = ~RangedAttackPreference.death & ~RangedAttackPreference.adjacent & ~RangedAttackPreference.weak

class ChangeSquarePreference(enum.Flag):
    slow = enum.auto()
    teleport = enum.auto()
    digging = enum.auto()
    up = enum.auto()
    down = enum.auto()

    def includes(self, flag):
        return self & flag == flag

escape_urgent = ~ChangeSquarePreference.slow
escape_default = escape_urgent | ChangeSquarePreference.slow

class IdentityDesirability(enum.Enum):
    desire_all = "desire all"
    desire_all_uncursed = "desire all uncursed"
    desire_one = "desire one"
    desire_seven = "desire seven"
    desire_as_raw_material = "desire as raw"
    desire_none = "none"

best_skills_by_class = {
    BaseRole.Archeologist: 'saber',
    BaseRole.Barbarian: 'axe',
    BaseRole.Caveperson: 'spear',
    BaseRole.Healer: 'quarterstaff',
    BaseRole.Knight: 'long sword',
    BaseRole.Monk: 'martial arts',
    BaseRole.Priest: 'mace',
    BaseRole.Ranger: 'spear',
    BaseRole.Rogue: 'long sword',
    BaseRole.Samurai: 'long sword',
    BaseRole.Tourist: 'saber',
    BaseRole.Valkyrie: 'long sword',
    BaseRole.Wizard: 'dagger',
}