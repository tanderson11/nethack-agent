import abc
import functools
import os
import pdb
from typing import NamedTuple
import pandas as pd
import numpy as np


from nle import nethack

import agents.representation.constants as constants
import agents.advice.preferences as preferences
import environment
from agents.representation.spoilers.monsters_csv_parsing import MONSTERS_BY_NAME
from utilities import ARS

class CorpseSpoiler(NamedTuple):
    name: str
    nutrition: int
    vegetarian: bool
    vegan: bool
    race_for_cannibalism: str
    acidic: bool
    poisonous: bool
    aggravate: bool
    slime: bool
    petrify: bool
    instadeath: bool
    stun: bool
    polymorph: bool
    hallucination: bool
    lycanthropy: bool
    teleportitis: bool
    invisibility: bool
    speed_toggle: bool

    _field_mapping = {}

CORPSES_BY_NAME = {}

corpse_df = pd.read_csv(os.path.join(os.path.dirname(__file__), "spoilers", "corpses.csv"))

for field in CorpseSpoiler._fields:
    CorpseSpoiler._field_mapping[field] = field.capitalize().replace("_", " ")
for _, row in corpse_df.iterrows():
    normalized_dict = {}
    for tupleversion, csvversion in CorpseSpoiler._field_mapping.items():
        normalized_dict[tupleversion] = row[csvversion]
    normalized = CorpseSpoiler(**normalized_dict)
    CORPSES_BY_NAME[normalized.name] = normalized

class Glyph():
    OFFSET = 0
    COUNT = 0

    @classmethod
    def class_mask(cls, glyphs):
        return (glyphs >= cls.OFFSET) & (glyphs < cls.OFFSET + cls.COUNT)

    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET
        self.name = None

    @classmethod
    def numeral_mapping(cls):
        mapping = {}
        for numeral in cls.numerals():
            # print(f"{cls} {numeral}")
            mapping[numeral] = cls(numeral)

        return mapping

    def __repr__(self):
        return "{} named {}".format(self.__class__, self.name or 'NO NAME DEFINED')

    @classmethod
    def numerals(cls):
        numerals = range(cls.OFFSET, cls.OFFSET + cls.COUNT)
        return numerals

class MonsterAlikeGlyph(Glyph):
    NEVER_CORPSE = {'lich', 'nalfeshnee', 'yellow light', 'Geryon', 'couatl', 'Baalzebub', 'hezrou', 'ki-rin', 'iron golem', 'lemure', 'master lich', 'djinni', 'flaming sphere', 'sandestin', 'shade', 'straw golem', 'leather golem', 'clay golem', 'Demogorgon', 'fire elemental', 'energy vortex', 'black light', 'ice vortex', 'Angel', 'rope golem', 'Dark One', 'Yeenoghu', 'air elemental', 'Nazgul', 'gas spore', 'steam vortex', 'ice devil', 'Juiblex', 'pit fiend', 'succubus', 'mail daemon', 'stone golem', 'earth elemental', 'manes', 'Orcus', 'bone devil', 'dust vortex', 'Asmodeus', 'Dispater', 'erinys', 'barbed devil', 'barrow wight', 'vrock', 'ghost', 'Minion of Huhetotl', 'fire vortex', 'glass golem', 'marilith', 'balrog', 'Archon', 'skeleton', 'ghoul', 'Ashikaga Takauji', 'water demon', 'Thoth Amon', 'fog cloud', 'shocking sphere', 'Vlad the Impaler', 'incubus', 'wood golem', 'paper golem', 'freezing sphere', 'Nalzok', 'horned devil', 'arch-lich', 'grid bug', 'Aleax', 'demilich', 'gold golem', 'water elemental', 'brown pudding', 'black pudding'}

    @classmethod
    def name_of_animated_dead(cls, name):
        if 'mummy' in name:
            return True
        if 'zombie' in name:
            return True
        if 'vampire' in name:
            return True

    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET
        monster = nethack.permonst(nethack.glyph_to_mon(numeral))
        # Has data:
        # 'ac', 'cnutrit', 'cwt', 'geno', 'mcolor', 'mconveys', 'mflags1', 'mflags2', 'mflags3',
        # 'mlet', 'mlevel', 'mmove', 'mname', 'mr', 'mresists', 'msize', 'msound'
        self.name = monster.mname
        self.animated_dead = self.__class__.name_of_animated_dead(self.name)
        self.corpse_spoiler = None
        if not self.name in self.NEVER_CORPSE and not self.animated_dead and self.name != 'long worm tail':
            self.corpse_spoiler = CORPSES_BY_NAME[self.name]

        self.monster_spoiler = None
        self.monster_spoiler = MONSTERS_BY_NAME[self.name]

    def safe_to_eat(self, character):
        if not self.corpse_spoiler:
            return False
        if self.corpse_spoiler.slime or self.corpse_spoiler.petrify or self.corpse_spoiler.instadeath:
            return False

        # For these remaining checks, maybe skip them if I'm hungry enough
        if character.can_cannibalize() and (self.corpse_spoiler.race_for_cannibalism == character.base_race.value):
            return False
        if character.can_cannibalize() and self.corpse_spoiler.aggravate:
            return False

        if self.corpse_spoiler.poisonous and not character.has_intrinsic(constants.Intrinsics.poison_resistance):
            return False

        if any([
            self.corpse_spoiler.acidic,
            self.corpse_spoiler.stun,
            self.corpse_spoiler.polymorph,
            self.corpse_spoiler.hallucination,
            self.corpse_spoiler.lycanthropy,
            self.corpse_spoiler.teleportitis,
            self.corpse_spoiler.invisibility,
            self.corpse_spoiler.speed_toggle
        ]):
            return False

        return True

    @classmethod
    def names(cls):
        names = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            names.add(cls(numeral).name)
        return names

class MonsterGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_MON_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)
        
        #self.has_passive = False
        #self.has_melee = False
        #self.has_ranged = False
        if self.monster_spoiler is not None:
            self.has_passive = self.monster_spoiler.passive_attack_bundle.num_attacks > 0
            self.has_melee = self.monster_spoiler.melee_attack_bundle.num_attacks > 0
            self.has_ranged = self.monster_spoiler.ranged_attack_bundle.num_attacks > 0
            self.has_death_throes = self.monster_spoiler.death_attack_bundle.num_attacks > 0

        self.is_shopkeeper = self.offset == 267

    @staticmethod
    def shopkeeper_mask(numerals):
        return (numerals == nethack.GLYPH_MON_OFF + 267)

    @staticmethod
    def gas_spore_mask(numerals):
        return (numerals == nethack.GLYPH_MON_OFF + 27)

    @staticmethod
    def floating_eye_mask(numerals):
        return (numerals == nethack.GLYPH_MON_OFF + 28)

    @staticmethod
    def always_peaceful_mask(numerals):
        return (numerals == nethack.GLYPH_MON_OFF + 267) | (numerals  == nethack.GLYPH_MON_OFF + 270) | ((numerals > (nethack.GLYPH_MON_OFF + 277)) & (numerals < (280 + nethack.GLYPH_MON_OFF)))

    def single_always_peaceful(self):
        return self.always_peaceful_mask(np.array([self.numeral])).all()

class ObjectGlyph(Glyph):
    OFFSET = nethack.GLYPH_OBJ_OFF # kept around so that ObjectGlyph.numerals() gives all object glyphs
    COUNT = nethack.NUM_OBJECTS

    def __init__(self, numeral):
        try:
            obj = nethack.objclass(nethack.glyph_to_obj(numeral))
        except IndexError:
            print(numeral)
            raise(Exception)
        # Has data:
        # 'oc_class', 'oc_color', 'oc_cost', 'oc_delay', 'oc_descr_idx', 'oc_name_idx', 'oc_oprop',
        # 'oc_prob', 'oc_weight'

        object_class_numeral = ord(obj.oc_class)
        appearance = nethack.OBJ_DESCR(obj) or nethack.OBJ_NAME(obj)
        name = nethack.OBJ_NAME(obj) # This is only sometimes accurate. Not for shuffled objects.
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET

        self.appearance = appearance
        self.name = name # not accurate for shuffled glyphs

    def desirable_glyph(self, character):
        identity = character.global_identity_map.identity_by_numeral[self.numeral]
        if not identity:
            if not self.numeral == RandomClassGlyph.OFFSET + RandomClassGlyph.COUNT: # strange objecst
                import pdb; pdb.set_trace()
            return False
        return identity.desirable_identity(character)

    @classmethod
    def names(cls):
        names = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            names.add(cls(numeral).name)
        return names

    @classmethod
    def appearances(cls):
        appearances = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            appearances.add(cls(numeral).appearance)
        return appearances

    @classmethod
    def object_classes_by_appearance(cls):
        classes_by_appearance = {}
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            g = ObjectGlyph(numeral)
            classes_by_appearance[g.appearance] = g.object_class_name

        return classes_by_appearance

    @classmethod
    def object_classes_by_name(cls):
        classes_by_name = {}
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            g = ObjectGlyph(numeral)
            classes_by_name[g.name] = g.object_class_name

        return classes_by_name

class RandomClassGlyph(ObjectGlyph):
    OFFSET = nethack.GLYPH_OBJ_OFF
    COUNT = 0
    class_number = 0

class IllobjGlyph(ObjectGlyph):
    OFFSET = RandomClassGlyph.OFFSET + RandomClassGlyph.COUNT
    COUNT = 1
    class_number = 1

class WeaponGlyph(ObjectGlyph):
    OFFSET = IllobjGlyph.OFFSET + IllobjGlyph.COUNT
    COUNT = 70
    class_number = 2

class ArmorGlyph(ObjectGlyph):
    OFFSET = WeaponGlyph.OFFSET + WeaponGlyph.COUNT
    COUNT = 79
    class_number = 3

class RingGlyph(ObjectGlyph):
    OFFSET = ArmorGlyph.OFFSET + ArmorGlyph.COUNT
    COUNT = 28
    class_number = 4

class AmuletGlyph(ObjectGlyph):
    OFFSET = RingGlyph.OFFSET + RingGlyph.COUNT
    COUNT = 11
    class_number = 5

class ToolGlyph(ObjectGlyph):
    OFFSET = AmuletGlyph.OFFSET + AmuletGlyph.COUNT
    COUNT = 50
    class_number = 6

class FoodGlyph(ObjectGlyph):
    OFFSET = ToolGlyph.OFFSET + ToolGlyph.COUNT
    COUNT = 33
    class_number = 7

class PotionGlyph(ObjectGlyph):
    OFFSET = FoodGlyph.OFFSET + FoodGlyph.COUNT
    COUNT = 26
    class_number = 8

class ScrollGlyph(ObjectGlyph):
    OFFSET = PotionGlyph.OFFSET + PotionGlyph.COUNT
    COUNT = 42
    class_number = 9

class SpellbookGlyph(ObjectGlyph):
    OFFSET = ScrollGlyph.OFFSET + ScrollGlyph.COUNT
    COUNT = 43
    class_number = 10

class WandGlyph(ObjectGlyph):
    OFFSET = SpellbookGlyph.OFFSET + SpellbookGlyph.COUNT
    COUNT = 27
    class_number = 11

class CoinGlyph(ObjectGlyph):
    OFFSET = WandGlyph.OFFSET + WandGlyph.COUNT
    COUNT = 1
    class_number = 12

    def desirable_glyph(self, character):
        return True

class GemGlyph(ObjectGlyph):
    OFFSET = CoinGlyph.OFFSET + CoinGlyph.COUNT
    COUNT = 36
    class_number = 13

class RockGlyph(ObjectGlyph):
    # confusingly this is not 'rocks' but 'Statue' and 'Boulder'
    OFFSET = GemGlyph.OFFSET + GemGlyph.COUNT
    COUNT = 2
    class_number = 14

    @classmethod
    def boulder_mask(cls, numerals):
        return numerals == cls.OFFSET + 0

class BallGlyph(ObjectGlyph):
    OFFSET = RockGlyph.OFFSET + RockGlyph.COUNT
    COUNT = 1
    class_number = 15

class ChainGlyph(ObjectGlyph):
    OFFSET = BallGlyph.OFFSET + BallGlyph.COUNT
    COUNT = 1
    class_number = 16

    def desirable_glyph(self, character):
        return False

class VenomGlyph(ObjectGlyph):
    OFFSET = ChainGlyph.OFFSET + ChainGlyph.COUNT
    COUNT = 2
    class_number = 17

    def desirable_glyph(self, character):
        return False

class CMapGlyph(Glyph):
    OFFSET = nethack.GLYPH_CMAP_OFF
    COUNT = nethack.MAXPCHARS - 9 # Fascinatingly, the explosions trample the end of this

    NAMES = [
        'stone', # 0
        'vwall', # 1
        'hwall', # 2
        'tlcorn', # 3
        'trcorn', # 4
        'blcorn', # 5
        'brcorn', # 6
        'crwall', # 7
        'tuwall', # 8
        'tdwall', # 9
        'tlwall', # 10
        'trwall', # 11
        'ndoor', # 12
        'vodoor', # 13
        'hodoor', # 14
        'vcdoor', # 15
        'hcdoor', # 16
        'bars', # 17
        'tree', # 18
        'room', # 19
        'darkroom', # 20
        'corr', # 21
        'litcorr', # 22
        'upstair', # 23
        'dnstair', # 24
        'upladder', # 25
        'dnladder', # 26
        'altar', # 27
        'grave', # 28
        'throne', # 29
        'sink', # 30
        'fountain', # 31
        'pool', # 32
        'ice', # 33
        'lava', # 34
        'vodbridge', # 35
        'hodbridge', # 36
        'vcdbridge', # 37
        'hcdbridge', # 38
        'air', # 39
        'cloud', # 40
        'water', # 41
        'arrow_trap', # 42
        'dart_trap', # 43
        'falling_rock_trap', # 44
        'squeaky_board', # 45
        'bear_trap', # 46
        'land_mine', # 47
        'rolling_boulder_trap', # 48
        'sleeping_gas_trap', # 49
        'rust_trap', # 50
        'fire_trap', # 51
        'pit', # 52
        'spiked_pit', # 53
        'hole', # 54
        'trap_door', # 55
        'teleportation_trap', # 56
        'level_teleporter', # 57
        'magic_portal', # 58
        'web', # 59
        'statue_trap', # 60
        'magic_trap', # 61
        'anti_magic_trap', # 62
        'polymorph_trap', # 63
        'vibrating_square', # 64
        'vbeam', # 65
        'hbeam', # 66
        'lslant', # 67
        'rslant', # 68
        'digbeam', # 69
        'flashbeam', # 70
        'boomleft', # 71
        'boomright', # 72
        'ss1', # 73
        'ss2', # 74
        'ss3', # 75
        'ss4', # 76
        'poisoncloud', # 77
        'goodpos', # 78
        'sw_tl', # 79
        'sw_tc', # 80
        'sw_tr', # 81
        'sw_ml', # 82
        'sw_mr', # 83
        'sw_bl', # 84
        'sw_bc', # 85
        'sw_br', # 86
    ]
    @classmethod
    def class_mask_without_stone(cls, glyphs):
        return (glyphs >= cls.OFFSET + 1) & (glyphs < cls.OFFSET + cls.COUNT)

    @classmethod
    def is_poorly_understood_check(cls, offsets):
        # Christian: Glyphs that I don't really know what they are
        return (
            ((offsets >= 39) & (offsets <= 41)) | # air, cloud, water. Planes only?
            (offsets == 60) | # statue trap uses this glyph or not?
            (offsets >= 65) # cruft?
        )

    @classmethod
    def is_room_floor_check(cls, offsets):
        # This is specifically defined as the stuff you find
        # in the guts of a DoD room. Used to define special rooms
        return (
            ((offsets >= 19) & (offsets <= 34) & ~(offsets == 21) & ~(offsets == 22)) |
            ((offsets >= 42) & (offsets <= 64))
        )

    @classmethod
    def is_trap_to_avoid_check(cls, offsets):
        return (
            ((offsets >= 42) & (offsets <= 63)) &
            ~((offsets == 62) | (offsets == 45) | (offsets == 58))
        )

    @classmethod
    def is_safely_walkable_check(cls, offsets):
         return (
             ~((offsets < 0) | (offsets > cls.OFFSET + cls.COUNT)) &
            (((offsets >= 12) & (offsets <= 14)) | # Doors
            ((offsets >= 19) & (offsets <= 34) & (~cls.is_liquid_check(offsets))) | # Room-like
            (offsets == 58) | # Magic portal
            (offsets == 64)) # Vibrating square
         )

    @staticmethod
    def is_liquid_check(offsets):
        return (offsets == 41) | (offsets == 32) | (offsets == 34)

    @staticmethod
    def is_door_check(offsets):
        return (offsets >= 12) & (offsets <= 16)

    @staticmethod
    def is_wall_check(offsets):
        return (offsets < 12)

    @staticmethod
    def is_observed_wall_check(offsets):
        return (offsets > 0) & (offsets < 12)

    @staticmethod
    def is_possible_secret_check(offsets):
        return (offsets >= 0) & (offsets < 3)

    @staticmethod
    def possible_secret_mask(numerals):
        return (numerals >= nethack.GLYPH_CMAP_OFF) & (numerals < 3 + nethack.GLYPH_CMAP_OFF)

    @staticmethod
    def open_door_mask(numerals):
        return (numerals > 12 + nethack.GLYPH_CMAP_OFF) & (numerals < 15 + nethack.GLYPH_CMAP_OFF)

    @classmethod
    def wall_mask(cls, numerals):
        return (numerals >= nethack.GLYPH_CMAP_OFF) & (numerals < nethack.GLYPH_CMAP_OFF + 12)

    @staticmethod
    def closed_door_mask(numerals):
        return (numerals >= 15 + nethack.GLYPH_CMAP_OFF) & (numerals < 17 + nethack.GLYPH_CMAP_OFF)

    @staticmethod
    def tactical_square_mask(numerals):
        return (numerals >= 21 + nethack.GLYPH_CMAP_OFF) & (numerals <= 26 + nethack.GLYPH_CMAP_OFF)

    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.OFFSET
        self.name = self.NAMES[self.offset]

        self.is_wall = self.offset < 12

        self.is_upstairs = self.offset == 23 or self.offset == 25
        self.is_downstairs = self.offset == 24 or self.offset == 26

        self.is_open_door = self.offset > 12 and self.offset < 15
        self.is_closed_door = self.offset == 15 or self.offset == 16

        self.is_fountain = self.offset == 31
        self.is_altar = self.offset == 27

        # not {altar, fountain, grave}
        self.engraveable = not self.is_altar and not self.is_fountain and not (self.offset == 28)
        
def make_glyph_class(base_klass, offset, count):
    class Klass(base_klass):
        OFFSET = offset
        COUNT = count

    return Klass

class PetGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_PET_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)

        self.name = "pet" + self.name

class InvisibleGlyph(Glyph):
    OFFSET = nethack.GLYPH_INVIS_OFF
    COUNT = 1

    def __init__(self, numeral):
        super().__init__(numeral)

        self.name = "invisible monster"

class DetectGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_DETECT_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)
        self.name = "detected" + self.name

class CorpseGlyph(Glyph):
    OFFSET = nethack.GLYPH_BODY_OFF
    COUNT = nethack.NUMMONS

    always_safe_non_perishable_offsets = [155, 322] # lichens and lizards!

    def __init__(self, numeral):
        super().__init__(numeral)

        self.always_safe_non_perishable = (self.offset in self.always_safe_non_perishable_offsets)

    # TODO hard-coding this for now until we have a CorpseIdentity that we can use
    def desirable_glyph(self, character):
        return self.always_safe_non_perishable

class RiddenGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_RIDDEN_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)
        self.name = "ridden" + self.name

class ExplodeGlyph(Glyph):
    OFFSET = nethack.GLYPH_EXPLODE_OFF
    COUNT = nethack.MAXEXPCHARS * nethack.EXPL_MAX

class ZapGlyph(Glyph):
    OFFSET = nethack.GLYPH_ZAP_OFF
    COUNT = nethack.NUM_ZAP * 4

class SwallowGlyph(Glyph):
    OFFSET = nethack.GLYPH_SWALLOW_OFF
    COUNT = nethack.NUMMONS * 8

    def __init__(self, numeral):
        super().__init__(numeral)

        self.swallowing_monster_offset = (self.offset - self.offset % 8)/8 + MonsterGlyph.OFFSET

class WarningGlyph(Glyph):
    OFFSET = nethack.GLYPH_WARNING_OFF
    COUNT = 6

class StatueGlyph(Glyph):
    OFFSET = nethack.GLYPH_STATUE_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)

def walkable(glyphs):
    # Object, Statue, Pet, Corpse, CMap
    walkable_glyphs = np.full_like(glyphs, False, dtype=bool)
    walkable_glyphs = np.where(CMapGlyph.class_mask(glyphs), CMapGlyph.is_safely_walkable_check(glyphs - CMapGlyph.OFFSET), walkable_glyphs)
    walkable_glyphs = np.where(CorpseGlyph.class_mask(glyphs), True, walkable_glyphs)
    walkable_glyphs = np.where(PetGlyph.class_mask(glyphs), True, walkable_glyphs)
    walkable_glyphs = np.where(StatueGlyph.class_mask(glyphs), True, walkable_glyphs)
    walkable_glyphs = np.where(ObjectGlyph.class_mask(glyphs), True, walkable_glyphs)

    return walkable_glyphs

klasses = [
    MonsterGlyph,
    RandomClassGlyph,
    IllobjGlyph,
    WeaponGlyph,
    ArmorGlyph,
    RingGlyph,
    AmuletGlyph,
    ArmorGlyph,
    ToolGlyph,
    FoodGlyph,
    PotionGlyph,
    ScrollGlyph,
    SpellbookGlyph,
    WandGlyph,
    CoinGlyph,
    GemGlyph,
    RockGlyph,
    BallGlyph,
    ChainGlyph,
    VenomGlyph,
    CMapGlyph,
    PetGlyph,
    InvisibleGlyph,
    DetectGlyph,
    CorpseGlyph,
    RiddenGlyph,
    ExplodeGlyph,
    ZapGlyph,
    SwallowGlyph,
    WarningGlyph,
    StatueGlyph,
]

GLYPH_NUMERAL_LOOKUP = {}

for klass in klasses:
    GLYPH_NUMERAL_LOOKUP.update(klass.numeral_mapping())


ks = GLYPH_NUMERAL_LOOKUP.keys()
for i in range(0, 5977):
    if i not in ks:
        print(i)

if not len(GLYPH_NUMERAL_LOOKUP.keys()) == 5_976:
    raise Exception("Surprising number of glyphs")

GLYPH_NAME_LOOKUP = {}
for glyph in GLYPH_NUMERAL_LOOKUP.values():
    if not glyph.name:
        continue
    GLYPH_NAME_LOOKUP[glyph.name] = glyph

GLYPH_NUMERAL_LOOKUP[5976] = None # Weird and bad thing in the inventory

#################
# OBJECT GLYPHS #
#################
class ObjectSpoilers():
    OBJECT_GLYPH_CLASSES = [
        RandomClassGlyph,
        IllobjGlyph,
        WeaponGlyph,
        ArmorGlyph,
        RingGlyph,
        AmuletGlyph,
        ArmorGlyph,
        ToolGlyph,
        FoodGlyph,
        PotionGlyph,
        ScrollGlyph,
        SpellbookGlyph,
        WandGlyph,
        CoinGlyph,
        GemGlyph,
        RockGlyph,
        BallGlyph,
        ChainGlyph,
        VenomGlyph,
    ]

    spoiler_file_by_glyph_class = {
        RandomClassGlyph: '',
        IllobjGlyph: '',
        WeaponGlyph: 'weapon_spoiler.csv',
        RingGlyph: 'ring_spoiler.csv',
        AmuletGlyph: 'amulet_spoiler.csv',
        ArmorGlyph: 'armor_spoiler.csv',
        ToolGlyph: 'tool_spoiler.csv',
        FoodGlyph: 'food_spoiler.csv',
        PotionGlyph: 'potion_spoiler.csv',
        ScrollGlyph: 'scroll_spoiler.csv',
        SpellbookGlyph: 'spellbook_spoiler.csv',
        WandGlyph: 'wand_spoiler.csv',
        CoinGlyph: 'coin_spoiler.csv',
        GemGlyph: 'gem_spoiler.csv',
        RockGlyph: 'rock_spoiler.csv',
        BallGlyph: 'ball_spoiler.csv',
        ChainGlyph: 'chain_spoiler.csv',
        VenomGlyph: '',
    }

    def __init__(self):
        object_spoilers_by_class = {}
        object_names_by_class = {}
        for glyph_class, spoiler_file in self.spoiler_file_by_glyph_class.items():
            if spoiler_file != '':
                with open(os.path.join(os.path.dirname(__file__), "spoilers", "object_spoilers", spoiler_file), 'r') as f:
                    df = pd.read_csv(f)
                    df = df.set_index('GLYPH')
                object_spoilers_by_class[glyph_class] = df
                object_names_by_class[glyph_class] = set(df.NAME.to_list())

        self.object_spoilers_by_class = object_spoilers_by_class
        self.object_names_by_class = object_names_by_class

        with open(os.path.join(os.path.dirname(__file__), "spoilers", "object_spoilers", 'artifact_spoiler.csv'), 'r') as f:
            df = pd.read_csv(f)
        self.artifact_spoilers = df

OBJECT_SPOILERS = ObjectSpoilers()

class IdentityLike():
    desirability_if_unidentified = preferences.IdentityDesirability.desire_none
    wearable = False
    has_carried_intrinsics = False
    is_artifact = False

    def __init__(self, idx) -> None:
        self.idx = idx.copy().sort_values()
        self.listened_actions = {}
        self.listened_price_id_methods = {}
        # whenever we find values, if it's unique, we store it in this dictionary
        # and don't have to touch the database repeatedly

    @classmethod
    def appearances(cls):
        return cls.data.APPEARANCE

    @classmethod
    def names(cls):
        return cls.data.NAME

    @classmethod
    def japanese_name_to_english(cls, japanese_name):
        return cls.data[cls.data.JAPANESE_NAME == japanese_name]['NAME'].iloc[0]

    @classmethod
    def japanese_names(cls):
        if 'JAPANESE_NAME' in cls.data.columns:
            return cls.data.JAPANESE_NAME
        else:
            return pd.Series(dtype=str)

    @classmethod
    def stacked_names(cls):
        if 'STACKED_NAME' in cls.data.columns:
            return cls.data.STACKED_NAME
        else:
            return pd.Series(dtype=str)

    @classmethod
    def stacked_name_to_singular(cls, stacked_name):
        return cls.data[cls.data.STACKED_NAME == stacked_name]['NAME'].iloc[0]

    @classmethod
    @functools.cache
    def _find_values_from_idx_bytes(cls, column, idx_bytes, idx_shape, dtype, dropna=False, false_if_na=False):
        idx = np.frombuffer(idx_bytes, dtype=dtype).reshape(idx_shape)
        if dropna:
            unique = np.unique(cls.data.loc[idx][column].dropna()) # the filtered dataframe values
        else:
            unique = np.unique(cls.data.loc[idx][column]) # the filtered dataframe values

        if len(unique) == 1:
            if false_if_na and pd.isna(unique[0]):
                unique[0] = False
            return unique[0] # policy: if we find only one value, just return it
        return unique

    @classmethod
    def _find_values(cls, column, data_idx, dropna=False, false_if_na=False):
        # convert idx to something immutable for caching
        #if len(data_idx) > 1: print(len(data_idx))
        idx_bytes = np.array(data_idx).tobytes()
        shape = data_idx.shape
        dtype = data_idx.dtype
        return cls._find_values_from_idx_bytes(column, idx_bytes, shape, dtype, dropna, false_if_na)

    def is_identified(self):
        return len(self.idx) == 1

    def could_be(self, names):
        if not isinstance(names, list):
            names = [names]

        for name in names:
            if name in self.find_values('NAME', dropna=True):
                return True

        return False

    def weight(self):
        return self.find_values('WEIGHT').max()

    def name(self):
        if self.is_identified():
            return self.find_values('NAME')
        else:
            return None

    def japanese_name(self):
        if self.is_identified():
            try:
                japanese_name = self.data.loc[self.idx].JAPANESE_NAME.iloc[0]
                if pd.isnull(japanese_name):
                    return None
                else:
                    return japanese_name
            # the data doesn't have a JAPANESE_NAME column
            except AttributeError:
                return None

        else:
            return None

    def desirable_identity(self, character):
        if self.is_identified():
            return preferences.IdentityDesirability(self.find_values('IDENTITY_DESIRABILITY'))

        return self.desirability_if_unidentified

    def give_name(self, name):
        matches_name = self.data.loc[self.idx].NAME == name
        new_idx = matches_name.index[matches_name]
        if len(new_idx) == 0:
            if environment.env.debug: import pdb; pdb.set_trace()
            print("FAILED DEDUCTION: giving name and overriding inferences")
            hard_name_match = (self.data.NAME == name)
            new_idx = hard_name_match.index[hard_name_match]
        self.idx = new_idx.sort_values()
        if environment.env.debug and self.name() != name: pdb.set_trace()

    def find_values(self, column, dropna=False, false_if_na=False):
        return self._find_values(column, self.idx, dropna, false_if_na)

    def apply_filter(self, new_idx):
        self.idx = new_idx.sort_values()

    def restrict_by_base_prices(self, base_prices, method='buy'):
        self.listened_price_id_methods[method] = True

        if self.is_identified():
            return
        price_matches = ~self.data.loc[self.idx].COST.isna() & self.data.loc[self.idx].COST.apply(lambda v: v in base_prices)
        #import pdb; pdb.set_trace()
        if price_matches.any():
            self.apply_filter(price_matches.index[price_matches])
        
        if self.is_identified():
            print(f"Identified by price id! name={self.name()}")

    def extrinsics_by_colname(self, column):
        extrinsics = constants.Intrinsics.NONE
        values = self.find_values(column)
        if not values or pd.isna(values):
            return extrinsics

        return constants.intrinsics_from_str(values)

    def worn_extrinsics(self):
        if not self.is_identified(): return constants.Intrinsics.NONE
        if not self.wearable: return constants.Intrinsics.NONE
        return self.extrinsics_by_colname('WORN_INTRINSICS')
    
    def process_message(self, message_obj, action):
        pass

class AmbiguousIdentity(IdentityLike):
    def __init__(self, global_identity_map, possible_numerals) -> None:
        self.possible_numerals = possible_numerals
        self.possible_identities = [global_identity_map.identity_by_numeral[n] for n in self.possible_numerals]
        idx = functools.reduce(pd.Index.union, [p.idx for p in self.possible_identities])

        super().__init__(idx)

    def give_name(self, name):
        # Should do something around reducing possible glyphs it could be?
        # doesn't really matter that much as these shouldn't be very persistent
        #if environment.env.debug: import pdb; pdb.set_trace()

        return super().give_name(name)

    def apply_filter(self, new_idx):
        #import pdb; pdb.set_trace()
        if environment.env.debug: import pdb; pdb.set_trace()

        return super().apply_filter(new_idx)

    def restrict_by_base_prices(self, base_prices, method='buy'):
        #import pdb; pdb.set_trace()
        if environment.env.debug: import pdb; pdb.set_trace()

        return super().restrict_by_base_prices(base_prices, method)

class NumeralIdentity(IdentityLike):
    '''
    Mediates access to the underlying dataframe of spoilers by intelligently handling shuffled glyphs.

    Listens to messages to gain knowledge about the identity of the object.
    '''
    def __init__(self, idx, shuffle_class=None):
        idx = pd.Index(idx, dtype=int).copy()
        super().__init__(idx)

        self.shuffle_class_idx = shuffle_class
        self.is_shuffled = shuffle_class is not None

### Scrolls
class ScrollLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[ScrollGlyph]
    desirability_if_unidentified = preferences.IdentityDesirability.desire_all
    bad_scrolls_any_buc = ['destroy armor', 'amensia']
    bad_scrolls_worse_than_blessed = ['punishment', 'fire', 'stinking cloud']

class AmbiguousScrollIdentity(AmbiguousIdentity, ScrollLike):
    pass

class ScrollIdentity(ScrollLike, NumeralIdentity):
    def __init__(self, idx, shuffle_class=None):
        super().__init__(idx, shuffle_class=shuffle_class)
        self.listened_actions = {}

    def process_message(self, message_obj, action):
        #import pdb; pdb.set_trace()
        self.listened_actions[action] = True
        if action == nethack.actions.Command.READ:

            message_matches = ~self.data.loc[self.idx].READ_MESSAGE.isna() & self.data.loc[self.idx].READ_MESSAGE.apply(lambda v: pd.isnull(v) or v in message_obj.message)
            if message_matches.any():
                self.apply_filter(message_matches.index[message_matches])

### Spellbooks
class SpellbookLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[SpellbookGlyph]

class AmbiguousSpellbookIdentity(SpellbookLike, AmbiguousIdentity):
    pass

class SpellbookIdentity(SpellbookLike, NumeralIdentity):
    pass

### Rings
class RingLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[RingGlyph]
    desirability_if_unidentified = preferences.IdentityDesirability.desire_all
    wearable = True

class AmbiguousRingIdentity(RingLike, AmbiguousIdentity):
    pass
class RingIdentity(RingLike, NumeralIdentity):
    pass

### Amulets
class AmuletLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[AmuletGlyph]
    desirability_if_unidentified = preferences.IdentityDesirability.desire_all
    wearable = True
    slot = 'neck'

class AmbiguousAmuletIdentity(AmuletLike, AmbiguousIdentity):
    pass
class AmuletIdentity(AmuletLike, NumeralIdentity):
    pass

### Potions
class PotionLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[PotionGlyph]
    desirability_if_unidentified = preferences.IdentityDesirability.desire_none

class AmbiguousPotionIdentity(PotionLike, AmbiguousIdentity):
    pass
class PotionIdentity(PotionLike, NumeralIdentity):
    pass

### Food
class FoodLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[FoodGlyph]

    def __init__(self, nutrition, taming_food_type) -> None:
        self.nutrition = nutrition
        self.taming_food_type = taming_food_type

class AmbiguousFoodIdentity(FoodLike, AmbiguousIdentity):
    def safe_non_perishable(self, character):
        return np.array([self.possible_identities.safe_non_perishable(character)]).all()
    
    def __init__(self, global_identity_map, possible_numerals) -> None:
        AmbiguousIdentity.__init__(self, global_identity_map, possible_numerals)
        
        taming_type = np.unique(np.array([p.taming_type for p in self.possible_identities]))
        nutrition = min([p.nutrition for p in self.possible_identities.nutrition])

        FoodLike.__init__(self, nutrition, taming_type)

class FoodIdentity(FoodLike, NumeralIdentity):
    def __init__(self, idx, shuffle_class=None):
        NumeralIdentity.__init__(self, idx, shuffle_class=shuffle_class)
        try:
            self.nutrition = int(self.find_values('NUTRITION'))
        except Exception:
            # A placeholder "non-zero" value
            self.nutrition = 1

        self.taming_food_type = self.find_values('TAME_TYPE')
        if self.taming_food_type == 'none': self.taming_food_type = None

    def safe_non_perishable(self, character):
        if character.sick_from_tripe() and self.name() == "tripe ration":
            return False

        if "glob" in self.name() or self.name() == "egg":
            return False

        return True

### Tools
class ToolLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[ToolGlyph]
    wearable = True

    def __init__(self, type) -> None:
        self.ranged = False
        self.thrown = False
        self.type = type

class AmbiguousToolIdentity(ToolLike, AmbiguousIdentity):
    def __init__(self, global_identity_map, possible_numerals) -> None:
        AmbiguousIdentity.__init__(self, global_identity_map, possible_numerals)
        ToolLike.__init__(self, self.find_values('TYPE'))

class ToolIdentity(ToolLike, NumeralIdentity):
    def __init__(self, idx, shuffle_class=None):
        NumeralIdentity.__init__(self, idx, shuffle_class)
        ToolLike.__init__(self, self.find_values('TYPE'))

### Gems
class GemLike():
    has_carried_intrinsics = True
    data = OBJECT_SPOILERS.object_spoilers_by_class[GemGlyph]
    def __init__(self, is_ammo, ammo_type) -> None:
        self.thrown = False
        self.is_ammo = is_ammo
        self.ammo_type = ammo_type

    def carried_extrinsics(self):
        return self.extrinsics_by_colname('CARRIED_INTRINSICS')

class AmbiguousGemIdentity(GemLike, AmbiguousIdentity):
    def __init__(self, global_identity_map, possible_numerals) -> None:
        AmbiguousIdentity.__init__(self, global_identity_map, possible_numerals)
        is_ammo = False
        ammo_type = None
        if not self.could_be(['luckstone', 'loadstone']):
            is_ammo = True
            ammo_type = "flint stone"

        GemLike.__init__(self, is_ammo, ammo_type)

class GemIdentity(GemLike, NumeralIdentity):
    def __init__(self, idx, shuffle_class=None):
        NumeralIdentity.__init__(self, idx, shuffle_class=shuffle_class)

        is_ammo = False
        ammo_type = None
        if not self.name() == 'luckstone' and not self.name() == 'loadstone':
            is_ammo = True
            ammo_type = "flint stone"

        GemLike.__init__(self, is_ammo, ammo_type)

### Rocks
class RockLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[RockGlyph]

    def __init__(self):
        self.thrown = False
        self.is_ammo = True
        self.ammo_type = "flint stone"

class RockIdentity(RockLike, NumeralIdentity):
    def __init__(self, idx, shuffle_class=None):
        NumeralIdentity.__init__(self, idx, shuffle_class)
        RockLike.__init__(self)

class CoinIdentity(NumeralIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[CoinGlyph]

class BallIdentity(NumeralIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[BallGlyph]

class ChainIdentity(NumeralIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[ChainGlyph]

### Wands
class WandLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[WandGlyph]
    desirability_if_unidentified = preferences.IdentityDesirability.desire_all

class AmbiguousWandIdentity(WandLike, AmbiguousIdentity):
    def is_attack(self):
        return np.array([p.is_attack for p in self.possible_identities]).all()

class WandIdentity(WandLike, NumeralIdentity):
    def is_attack(self):
        is_attack = self.find_values('ATTACK')
        if isinstance(is_attack, np.ndarray):
            return is_attack.all()
        else:
            return is_attack

    def process_message(self, message_obj, action):
        self.listened_actions[action] = True
        if action == nethack.actions.Command.READ:
            if 'glows blue' in message_obj.message:
                return "R_1"
        elif action == nethack.actions.Command.ZAP:
            if "Nothing happens." in message_obj.message and self.name() is not None:
                return "C_0"
        # engrave testing
        elif action == nethack.actions.Command.ENGRAVE:
            if "too worn out to engrave." in message_obj.message and self.name() is not None:
                return "C_0"
            # if there is an engrave message and it is in fact contained in the overheard message
            #pdb.set_trace()
            message_matches = ~self.data.loc[self.idx].ENGRAVE_MESSAGE.isna() & self.data.loc[self.idx].ENGRAVE_MESSAGE.apply(lambda v: pd.isnull(v) or v in message_obj.message)
            #print(message_matches)
            if message_matches.any():
                self.apply_filter(message_matches.index[message_matches])
    
### Armor
class ArmorLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[ArmorGlyph]
    desirability_if_unidentified = preferences.IdentityDesirability.desire_all
    wearable = True

    def __init__(self, slot):
        self.slot = slot

    def tier(self):
        tier = self.find_values('TIER')
        if isinstance(tier, np.ndarray):
            return tier.max()
        return tier

    def AC(self):
        return self.find_values('AC')

    def gen_cursed(self):
        return self.find_values('GEN_CURSED')

    def MC(self):
        return self.find_values('MC')

    def magic(self):
        return self.find_values('MAGIC')

    def potentially_magic(self):
        magic = self.magic()

        if isinstance(magic, np.ndarray):
            return self.magic().any()
        else:
            return magic

    def converted_wear_value(self):
        return self.find_values('CONVERTED_WEAR_VALUE')

class AmbiguousArmorIdentity(ArmorLike, AmbiguousIdentity):
    def __init__(self, global_identity_map, possible_numerals) -> None:
        AmbiguousIdentity.__init__(self, global_identity_map, possible_numerals)
        slot = self.find_values('SLOT')
        ArmorLike.__init__(self, slot)

class ArmorIdentity(ArmorLike, NumeralIdentity):
    def __init__(self, idx, shuffle_class=None):
        NumeralIdentity.__init__(self, idx, shuffle_class=shuffle_class)
        slot = self.find_values('SLOT')
        ArmorLike.__init__(self, slot)

### Weapons
class WeaponLike():
    data = OBJECT_SPOILERS.object_spoilers_by_class[WeaponGlyph]

    def __init__(self):
        self.stackable = self.is_identified() and not pd.isna(self.find_values('STACKED_NAME'))

        self.slot = self.find_values('SLOT')
        self.is_ammo = self.find_values('AMMUNITION', false_if_na=True)
        self.thrown = self.find_values('THROWN', false_if_na=True)
        self.thrown_from = self.find_values('THROWN_FROM')

        self.ammo_type = None
        if self.is_ammo:
            self.ammo_type = self.find_values('AMMO_TYPE')
        self.ammo_type_used = self.find_values('USES_AMMO')

        self.ranged = self.find_values('RANGED', false_if_na=True)
        self.skill = self.find_values('SKILL')

        second_slot = self.find_values('SECOND_SLOT')
        if isinstance(second_slot, np.ndarray):
            has_second_slot = pd.isnull(second_slot).any()
            second_slot = set(second_slot).pop()
        else:
            has_second_slot = not pd.isnull(second_slot)

        if has_second_slot:
            self.slot = [self.slot, second_slot]

    def avg_melee_damage(self, monster):
        # TK know about monster size
        return (self.find_values('SAVG') + self.find_values('LAVG'))/2

class AmbiguousWeaponIdentity(WeaponLike, AmbiguousIdentity):
    def __init__(self, global_identity_map, possible_numerals) -> None:
        AmbiguousIdentity.__init__(self, global_identity_map, possible_numerals)
        WeaponLike.__init__(self)

class WeaponIdentity(WeaponLike, NumeralIdentity):
    def __init__(self, idx, shuffle_class=None):
        NumeralIdentity.__init__(self, idx, shuffle_class)
        WeaponLike.__init__(self)

    def process_message(self, message_obj, action):
        if action == nethack.actions.Command.THROW or nethack.actions.Command.FIRE:
            if "slips as you throw it" in message_obj.message or "misfires" in message_obj.message:
                #import pdb; pdb.set_trace()
                return "BUC_C"

        if action == nethack.actions.Command.WIELD and self.stackable:
            #import pdb; pdb.set_trace()
            return "N_S"

class BareHandsIdentity(WeaponIdentity):
    def __init__(self):
        self.slot = 'hand'
        self.ranged = False
        self.is_ammo = False
        self.thrown = False
        self.stackable = False

    def name(self):
        return "bare hands"

    def is_identified(self):
        return True

### Artifacts
class ArtifactIdentity(IdentityLike):
    is_artifact = True
    # we could tweak the find values method
    # but intrinsics + bonus damage are basically the ONLY things that differ about artifacts
    def artifact_extrinsics(self, extrinsic_type):
        extrinsic_str = self.artifact_row[extrinsic_type]
        if extrinsic_str is None or pd.isna(extrinsic_str):
            return constants.Intrinsics.NONE
        else:
            return constants.intrinsics_from_str(extrinsic_str)

    def wielded_extrinsics(self):
        return self.artifact_extrinsics('WIELDED_INTRINSICS')

    def carried_extrinsics(self):
        if self.has_carried_intrinsics:
            self.artifact_extrinsics('CARRIED_INTRINSICS') | super().carried_extrinsics()
        return self.artifact_extrinsics('CARRIED_INTRINSICS')

    def worn_extrinsics(self):
        if self.wearable:
            return self.artifact_extrinsics('WORN_INTRINSICS') | super().worn_extrinsics()

    def __init__(self, artifact_name, artifact_row) -> None:
        self.artifact_name = artifact_name
        self.artifact_row = artifact_row

class ArtifactWeaponIdentity(ArtifactIdentity, WeaponIdentity):
    associated_glyph_class = WeaponGlyph

    class ArtifactWeaponDamage(NamedTuple):
        damage_mod: int = 0
        damage_mult: int = 1

    def __init__(self, idx, artifact_name, artifact_row, shuffle_class=None):
        ArtifactIdentity.__init__(self, artifact_name, artifact_row)
        WeaponIdentity.__init__(self, idx, shuffle_class=shuffle_class)

        bonus = artifact_row['DAMAGE BONUS']
        if pd.isna(bonus): bonus = 0
        mult  = artifact_row['DAMAGE MULT']
        if pd.isna(mult): mult = 1

        self.artifact_damage = self.ArtifactWeaponDamage(bonus, mult)
        # keep idx pointed at the base item and override any methods with artifact specific stuff

class ArtifactArmorIdentity(ArtifactIdentity, ArmorIdentity):
    associated_glyph_class = ArmorGlyph
    def __init__(self, idx, artifact_name, artifact_row, shuffle_class=None):
        ArtifactIdentity.__init__(self, artifact_name, artifact_row)
        ArmorIdentity.__init__(self, idx, shuffle_class=shuffle_class)

class ArtifactAmuletIdentity(ArtifactIdentity, AmuletIdentity):
    associated_glyph_class = AmuletGlyph
    def __init__(self, idx, artifact_name, artifact_row, shuffle_class=None):
        ArtifactIdentity.__init__(self, artifact_name, artifact_row)
        AmuletIdentity.__init__(self, idx, shuffle_class=shuffle_class)

class ArtifactGemIdentity(ArtifactIdentity, GemIdentity):
    associated_glyph_class = GemGlyph
    def __init__(self, idx, artifact_name, artifact_row, shuffle_class=None):
        ArtifactIdentity.__init__(self, artifact_name, artifact_row)
        GemIdentity.__init__(self, idx, shuffle_class=shuffle_class)

class ArtifactToolIdentity(ArtifactIdentity, ToolIdentity):
    associated_glyph_class = ToolGlyph
    def __init__(self, idx, artifact_name, artifact_row, shuffle_class=None):
        ArtifactIdentity.__init__(self, artifact_name, artifact_row)
        ToolIdentity.__init__(self, idx, shuffle_class=shuffle_class)

class GlobalIdentityMap():
    identity_by_glyph_class = {
        CoinGlyph: CoinIdentity,
        ArmorGlyph: ArmorIdentity,
        WandGlyph: WandIdentity,
        WeaponGlyph: WeaponIdentity,
        FoodGlyph: FoodIdentity,
        AmuletGlyph: AmuletIdentity,
        RingGlyph: RingIdentity,
        GemGlyph: GemIdentity,
        PotionGlyph: PotionIdentity,
        ToolGlyph: ToolIdentity,
        SpellbookGlyph: SpellbookIdentity,
        ScrollGlyph: ScrollIdentity,
        RockGlyph: RockIdentity,
        BallGlyph: BallIdentity,
        ChainGlyph: ChainIdentity,
    }

    ambiguous_identity_by_glyph_class = {
        ArmorGlyph: AmbiguousArmorIdentity,
        WandGlyph: AmbiguousWandIdentity,
        WeaponGlyph: AmbiguousWeaponIdentity,
        FoodGlyph: AmbiguousFoodIdentity,
        AmuletGlyph: AmbiguousAmuletIdentity,
        RingGlyph: AmbiguousRingIdentity,
        GemGlyph: AmbiguousGemIdentity,
        PotionGlyph: AmbiguousPotionIdentity,
        ToolGlyph: AmbiguousToolIdentity,
        SpellbookGlyph: AmbiguousSpellbookIdentity,
        ScrollGlyph: AmbiguousScrollIdentity,
    }

    artifact_identity_by_type = {
        "Weapon": (WeaponGlyph, ArtifactWeaponIdentity),
        "Tool": (ToolGlyph, ArtifactToolIdentity),
        "Amulet": (AmuletGlyph, ArtifactAmuletIdentity),
        "Armor": (ArmorGlyph, ArtifactArmorIdentity),
        "Gem": (GemGlyph, ArtifactGemIdentity),
    }

    def make_ambiguous_identity_with_name(self, glyph_class, name):
        ambiguous_class = self.ambiguous_identity_by_glyph_class[glyph_class]
        data = ambiguous_class.data
        matches_name = (data.NAME == name)
        data_entry_matches = np.unique(matches_name.index[matches_name])
        possible_glyphs = data_entry_matches

        if data[matches_name].SHUFFLED.any():
            same_shuffle_class = data['SHUFFLE_CLASS'] == data.loc[data_entry_matches[0]]['SHUFFLE_CLASS']
            shuffle_class_idx = same_shuffle_class.index[same_shuffle_class]
            possible_glyphs = np.unique(shuffle_class_idx)
        else:
            print("WARNING: A named identity should never be ambiguous if it's not shuffled")
            if environment.env.debug: assert False

        #print(name, possible_glyphs)
        ambiguous_id = ambiguous_class(self, possible_glyphs)
        ambiguous_id.give_name(name)
        return ambiguous_id

    def buc_from_string(self, buc_string):
        if self.is_priest:
            if buc_string is None:
                return constants.BUC.uncursed
            elif buc_string == 'cursed':
                return constants.BUC.cursed
            elif buc_string == 'blessed':
                return constants.BUC.blessed
            assert False, "bad buc string for priest"
        else:
            if buc_string is None:
                return constants.BUC.unknown
            elif buc_string == 'cursed':
                return constants.BUC.cursed
            elif buc_string == 'blessed':
                return constants.BUC.blessed
            elif buc_string == 'uncursed':
                return constants.BUC.uncursed
            assert False, "bad buc string for non-priest"

    def found_artifact(self, artifact):
        if self.generated_artifacts[artifact] == False:
            if artifact == 'Excalibur':
                #import pdb; pdb.set_trace()
                pass
            self.generated_artifacts[artifact] = True

    def load_artifact_identities(self):
        self.generated_artifacts = {}
        self.artifact_identity_by_name = {}
        self.artifact_identity_by_appearance_name = {}
        artifact_df = OBJECT_SPOILERS.artifact_spoilers

        for _, row in artifact_df.iterrows():
            #import pdb; pdb.set_trace()
            glyph_class, artifact_identity_class = self.artifact_identity_by_type[row["BASE OCLASS"]]
            #import pdb; pdb.set_trace()
            #base_idx = self.identity_by_name[(glyph_class, row["BASE ITEM"])].idx
            artifact_name = row["ARTIFACT NAME"]

            artifact_identity = artifact_identity_class([row["IDX"]], artifact_name, row)
            self.artifact_identity_by_name[artifact_name] = artifact_identity
            self.generated_artifacts[artifact_name] = False
            self.artifact_identity_by_appearance_name[row['ARTIFACT APPEARANCE']] = artifact_identity
            self.identity_by_name[(glyph_class,  artifact_name)] = artifact_identity
        
        #import pdb; pdb.set_trace()
        # go through table of artifacts, for each row, find base item row and join it in (dropping some columns)
        # then instantiate the appropriate artifact identity

    def __init__(self, is_priest=False):
        self.identity_by_numeral = {}
        # indexed by (glyph_class, name) because of 'blank paper' being both a spellbook and scroll
        self.identity_by_name = {} # this we will have to be careful to keep updated
        self.identity_by_japanese_name = {}
        # indexed by (glyph_class, appearance) for consistency (don't think there are any overlapping appearances, but there could be)
        self.glyph_by_appearance = {}

        self.appearance_counts = {} # when we '#name' or identify an object, we can decrement this

        self.is_priest = is_priest # If we are a priest then we see BUC differently

        for numeral in ObjectGlyph.numerals():
            glyph = GLYPH_NUMERAL_LOOKUP[numeral]
            identity_class = self.identity_by_glyph_class.get(type(glyph), NumeralIdentity)
            self.make_identity(numeral, glyph, identity_class)

        special_corpses = [1299, 1466]
        for corpse_numeral in special_corpses:
            #import pdb; pdb.set_trace()
            glyph = GLYPH_NUMERAL_LOOKUP[corpse_numeral]
            identity_class = FoodIdentity
            self.make_identity(corpse_numeral, glyph, identity_class)

        self.load_artifact_identities()
        #print(self.identity_by_numeral)

    def make_identity(self, numeral, glyph, identity_class):
        identity = None # if the class hasn't been implemented, we won't futz with its identity
        idx = [numeral]
        try:
            data = identity_class.data
        except AttributeError:
            data = None

        if data is not None:
            spoiler_row = data.loc[numeral]

            if (not spoiler_row['SHUFFLED']) or pd.isna(spoiler_row['SHUFFLED']):
                # if it's not shuffled, the numeral accurately picks out the object information
                # from the spreadsheet
                idx = [numeral]
                shuffle_class_idx = None
            else:
                # if it is shuffled, it could be any object in the shuffled class
                same_shuffle_class = data['SHUFFLE_CLASS'] == spoiler_row['SHUFFLE_CLASS']
                idx = same_shuffle_class.index[same_shuffle_class]
                shuffle_class_idx = same_shuffle_class.index[same_shuffle_class]

            identity = identity_class(idx, shuffle_class=shuffle_class_idx)

        self.identity_by_numeral[numeral] = identity

        ''' Ill-advised attempt to do frequency tracking! We only make each identity once
        try:
            self.appearance_counts[(type(glyph), glyph.appearance)] += 1
            # class + appearance no longer uniquely identifies but we can add to the list
            self.glyph_by_appearance[(type(glyph), glyph.appearance)].append(glyph)
        except KeyError:
            self.appearance_counts[(type(glyph), glyph.appearance)] = 1
            self.glyph_by_appearance[(type(glyph), glyph.appearance)] = [glyph] 
        '''

        name = identity.name() if identity else None
        japanese_name = identity.japanese_name() if identity else None

        glyph_type = type(glyph)
        if glyph_type == CorpseGlyph:
            glyph_type = FoodGlyph
        #print(glyph_type)
        if name is not None:
            self.identity_by_name[(glyph_type, name)] = identity

        if japanese_name is not None:
            self.identity_by_japanese_name[(glyph_type, japanese_name)] = identity

    def associate_identity_and_name(self, identity, name):
        self.identity_by_name[name] = identity
        identity.give_name(name)

        if identity.is_shuffled:
            if len(identity.idx) == 0:
                if environment.env.debug: import pdb; pdb.set_trace()
                return None
            data_idx = identity.idx[0]
            # go through the shuffled class and remove that entry from the idx
            for shuffled_item_idx in identity.shuffle_class_idx:
                other_identity = self.identity_by_numeral[shuffled_item_idx]
                if other_identity == identity:
                    continue
                if data_idx in other_identity.idx:
                    if isinstance(other_identity.idx, pd.Index):
                        other_identity.idx = other_identity.idx.drop(data_idx)
                        #import pdb; pdb.set_trace()
                        if len(other_identity.idx) == 0 and environment.env.debug:
                            import pdb; pdb.set_trace()

#####################
# UTILITY FUNCTIONS #
#####################

def dump_oclass(cls):
    #df_dict = {'glyph': [], 'name': [], 'appearance': [], 'is_shuffled': []}
    rows = []
    for n in cls.numerals():
        identity = OBJECT_IDENTITIES_BY_GLYPH.get(n, None)
        g = GLYPH_NUMERAL_LOOKUP[n]

        if identity is not None:
            name = identity.name
        else:
            name = g.name

        row = [n, name, g.appearance, g.is_shuffled, g.object_class_name]
        rows.append(row)

    for row in rows:
        if len(row) != 4:
            print(row)
    df = pd.DataFrame(columns=['glyph', 'name', 'appearance', 'is_shuffled', 'class'], data=rows)
    print(df)
    with open('glyph_dump.csv', 'w') as f:
        df.to_csv(f)

def get_by_name(klass, name):
    glyph = GLYPH_NAME_LOOKUP.get(name, None)
    if not isinstance(glyph, klass):
        raise Exception(f"bad glyph name: {name}")
    return glyph

def stackable_mask(numerals):
    return ObjectGlyph.class_mask(numerals) | CorpseGlyph.class_mask(numerals) | StatueGlyph.class_mask(numerals)

def stackable_glyph(glyph):
    if isinstance(glyph, ObjectGlyph): return True
    if isinstance(glyph, CorpseGlyph): return True
    if isinstance(glyph, StatueGlyph): return True
    return False

def monster_like_mask(numerals):
    return MonsterGlyph.class_mask(numerals) | InvisibleGlyph.class_mask(numerals) | SwallowGlyph.class_mask(numerals) | WarningGlyph.class_mask(numerals)

#for k,v in MonsterGlyph.numeral_mapping().items():
#    print(k, v)
#print(MonsterGlyph.OFFSET)

#for k,v in ArmorGlyph.numeral_mapping().items():
#    print(k, v)
