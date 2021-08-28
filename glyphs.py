import csv
import os
import pdb
from typing import NamedTuple
from collections import Counter

from nle import nethack
import pandas as pd
import numpy as np

import constants
import environment
import utilities
from utilities import ARS
from spoilers.monsters_csv_parsing import MONSTERS_BY_NAME

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

    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET
        self.name = None

    def walkable(self, character):
        return False

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
        if character.can_cannibalize() and (self.corpse_spoiler.race_for_cannibalism == character.base_race):
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
        
        self.always_peaceful = False
        if self.is_shopkeeper or self.offset in [278, 279]: # shopkeeper and watch people
            self.always_peaceful = True

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

    def walkable(self, character):
        return True

    def desirable_object(self, global_identity_map, character):
        return False

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

    def desirable_object(self, global_identity_map, character):
        return True

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

    def safe_non_perishable(self, global_identity_map, character):
        identity = global_identity_map.identity_by_numeral[self.numeral]
        if identity is None:
            return False

        if identity and character.sick_from_tripe() and identity.name() == "tripe ration":
            return False

        if identity and ("glob" in identity.name() or identity.name() == "egg"):
            return False

        return True

    def desirable_object(self, global_identity_map, character):
        return self.safe_non_perishable(global_identity_map, character)

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

class GemGlyph(ObjectGlyph):
    OFFSET = CoinGlyph.OFFSET + CoinGlyph.COUNT
    COUNT = 36
    class_number = 13

class RockGlyph(ObjectGlyph):
    # confusingly this is not 'rocks' but 'Statue' and 'Boulder'
    OFFSET = GemGlyph.OFFSET + GemGlyph.COUNT
    COUNT = 2
    class_number = 14

class BallGlyph(ObjectGlyph):
    OFFSET = RockGlyph.OFFSET + RockGlyph.COUNT
    COUNT = 1
    class_number = 15

class ChainGlyph(ObjectGlyph):
    OFFSET = BallGlyph.OFFSET + BallGlyph.COUNT
    COUNT = 1
    class_number = 16

class VenomGlyph(ObjectGlyph):
    OFFSET = ChainGlyph.OFFSET + ChainGlyph.COUNT
    COUNT = 2
    class_number = 17

class CMapGlyph(Glyph):
    OFFSET = nethack.GLYPH_CMAP_OFF
    COUNT = nethack.MAXPCHARS

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
        'explode1', # 87
        'explode2', # 88
        'explode3', # 89
        'explode4', # 90
        'explode5', # 91
        'explode6', # 92
        'explode7', # 93
        'explode8', # 94
        'explode9', # 95
    ]

    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET
        self.name = self.__class__.NAMES[numeral - self.__class__.OFFSET]

        ## Thayer: could also do this with static methods, but either way I think we want these as static attributes to play nicely with getattr
        self.possible_secret_door = self.offset < 3
        
        self.is_floor = self.offset >= 19 and self.offset <= 31

        self.is_wall = self.offset < 12
        # offset 12 is technically the square where a door used to be, we're going to ignore it
        self.is_open_door = self.offset > 12 and self.offset < 15
        self.is_closed_door = self.offset == 15 or self.offset == 16
        self.is_downstairs = self.offset == 24 or self.offset == 26
        self.is_upstairs = self.offset == 23 or self.offset == 25
        self.is_trap = self.offset > 41 and self.offset < 65
        
    def walkable(self, character):
        return (self.offset > 18 and self.offset < 32) or self.offset == 12 or self.is_open_door or self.is_downstairs or self.is_upstairs

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
    
    def walkable(self, character):
        return True

class InvisibleGlyph(Glyph):
    OFFSET = nethack.GLYPH_INVIS_OFF
    COUNT = 1

    def __init__(self, numeral):
        super().__init__(numeral)

class DetectGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_DETECT_OFF
    COUNT = nethack.NUMMONS

class CorpseGlyph(Glyph):
    OFFSET = nethack.GLYPH_BODY_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)

        self.always_safe_non_perishable = (self.offset in [155, 322]) # lichens and lizards!

    def walkable(self, character):
        return True

    def desirable_object(self, global_identity_map, character):
        return self.always_safe_non_perishable

class RiddenGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_RIDDEN_OFF
    COUNT = nethack.NUMMONS

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
    
    def walkable(self, character):
        return True

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


#print(GLYPH_NUMERAL_LOOKUP)
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
        CoinGlyph: '',
        GemGlyph: 'gem_spoiler.csv',
        RockGlyph: 'rock_spoiler.csv',
        BallGlyph: 'ball_spoiler.csv',
        ChainGlyph: '',
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

OBJECT_SPOILERS = ObjectSpoilers()

class ObjectIdentity():
    '''
    Mediates access to the underlying dataframe of spoilers by intelligently handling shuffled glyphs.

    Listens to messages to gain knowledge about the identity of the object.
    '''
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

    def __init__(self, idx):
        self.idx = idx
        self.listened_actions = {}

    @classmethod
    def identity_from_name(cls, name):
        # make an identity that represents the information you know from seeing the object
        matches_name = (cls.data.NAME == name)
        idx = matches_name.index[matches_name]

        return cls(idx)

    def give_name(self, name):
        matches_name = self.data.loc[self.idx].NAME == name
        self.idx = matches_name.index[matches_name]

        if environment.env.debug and self.name() != name: pdb.set_trace()

    def is_identified(self):
        return len(self.idx) == 1

    def process_message(self, message_obj, action):
        pass

    def apply_filter(self, idx):
        self.idx = idx

    def find_values(self, column):
        unique = np.unique(self.data.loc[self.idx][column]) # the filtered dataframe values
        if len(unique) == 1:
            return unique[0] # policy: if we find only one value, just return it
        return unique

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

class ScrollIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[ScrollGlyph]

class SpellbookIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[SpellbookGlyph]

class RingIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[RingGlyph]

class AmuletIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[AmuletGlyph]

class PotionIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[PotionGlyph]

class FoodIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[FoodGlyph]

class ToolIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[ToolGlyph]

class GemIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[GemGlyph]

class RockIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[RockGlyph]

class BallIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[BallGlyph]

class WandIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[WandGlyph]
    def process_message(self, message_obj, action):
        self.listened_actions[action] = True

        # engrave testing
        if action == nethack.actions.Command.ENGRAVE:
            # if there is an engrave message and it is in fact contained in the overheard message
            #pdb.set_trace()
            message_matches = ~self.data.loc[self.idx].ENGRAVE_MESSAGE.isna() & self.data.loc[self.idx].ENGRAVE_MESSAGE.apply(lambda v: pd.isnull(v) or v in message_obj.message)
            #print(message_matches)
            if message_matches.any():
                self.apply_filter(message_matches.index[message_matches])

class ArmorIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[ArmorGlyph]

    def __init__(self, idx):
        super().__init__(idx)

        try:
            self.slot = self.find_values('SLOT')
        except AttributeError:
            if environment.env.debug: pdb.set_trace()
            pass

    def AC(self):
        return self.find_values('AC')

    def gen_cursed(self):
        return self.find_values('GEN_CURSED')

    def MC(self):
        return self.find_values('MC')

    def magic(self):
        return self.find_values('MAGIC')

    def converted_wear_value(self):
        return self.find_values('CONVERTED_WEAR_VALUE')

class WeaponIdentity(ObjectIdentity):
    data = OBJECT_SPOILERS.object_spoilers_by_class[WeaponGlyph]

    def __init__(self, idx):
        super().__init__(idx)

        self.slot = self.find_values('SLOT')

        second_slot = self.find_values('SECOND_SLOT')
        if isinstance(second_slot, np.ndarray):
            has_second_slot = pd.isnull(second_slot).any()
            second_slot = set(second_slot).pop()
        else:
            has_second_slot = pd.isnull(second_slot)


        if has_second_slot:
            self.slot = [self.slot, second_slot]


    def avg_melee_damage(self, monster):
        # TK know about monster size
        return self.find_values('SAVG')

class GlobalIdentityMap():
    identity_by_glyph_class = {
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
    }

    def __init__(self):
        self.identity_by_numeral = {}
        # indexed by (glyph_class, appearance) because of 'blank paper' being both a spellbook and scroll
        self.identity_by_name = {} # this we will have to be careful to keep updated
        self.identity_by_japanese_name = {}
        # indexed by (glyph_class, appearance) for consistency (don't think there are any overlapping appearances, but there could be)
        self.glyph_by_appearance = {}

        self.appearance_counts = {} # when we '#name' or identify an object, we can decrement this

        for numeral in ObjectGlyph.numerals():
            glyph = GLYPH_NUMERAL_LOOKUP[numeral]
            identity_class = self.identity_by_glyph_class.get(type(glyph), ObjectIdentity)

            identity = None # if the class hasn't been implemented, we won't futz with its identity
            idx = [numeral]
            try:
                data = identity_class.data
            except AttributeError:
                data = None

            if data is not None:
                spoiler_row = data.loc[numeral]

                if not spoiler_row['SHUFFLED']:
                    # if it's not shuffled, the numeral accurately picks out the object information
                    # from the spreadsheet
                    idx = [numeral]
                else:
                    # if it is shuffled, it could be any object in the shuffled class
                    same_shuffle_class = data['SHUFFLE_CLASS'] == spoiler_row['SHUFFLE_CLASS']
                    idx = same_shuffle_class.index[same_shuffle_class]

                identity = identity_class(idx)

            self.identity_by_numeral[numeral] = identity

            try:
                self.appearance_counts[(type(glyph), glyph.appearance)] += 1
                # class + appearance no longer uniquely identifies but we can add to the list
                self.glyph_by_appearance[(type(glyph), glyph.appearance)].append(glyph)
            except KeyError:
                self.appearance_counts[(type(glyph), glyph.appearance)] = 1
                self.glyph_by_appearance[(type(glyph), glyph.appearance)] = [glyph] 

            
            name = identity.name() if identity else None
            japanese_name = identity.japanese_name() if identity else None


            if name is not None:
                self.identity_by_name[(type(glyph), name)] = identity

            if japanese_name is not None:
                self.identity_by_japanese_name[(type(glyph), japanese_name)] = identity

        #print(self.identity_by_numeral)

    def associate_identity_and_name(self, identity, name):
        self.identity_by_name[name] = identity
        identity.give_name(name)

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
        if environment.env.debug:
            pdb.set_trace()
        raise Exception("bad glyph name")
    return glyph
