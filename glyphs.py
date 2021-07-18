import csv
import os
import pdb
from typing import NamedTuple
from collections import Counter

from nle import nethack
import pandas as pd

import environment
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
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            # print(f"{cls} {numeral}")
            mapping[numeral] = cls(numeral)

        return mapping


    def __repr__(self):
        return "{} named {}".format(self.__class__, self.name or 'NO NAME DEFINED')

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
        if self.name != 'long worm tail':
            self.monster_spoiler = MONSTERS_BY_NAME[self.name]

    def safe_to_eat(self, character):
        if not self.corpse_spoiler:
            return False
        if self.corpse_spoiler.slime or self.corpse_spoiler.petrify or self.corpse_spoiler.instadeath:
            return False

        # For these remaining checks, maybe skip them if I'm hungry enough
        if character.character.can_cannibalize() and (self.corpse_spoiler.race_for_cannibalism == character.character.base_race):
            return False
        if character.character.can_cannibalize() and self.corpse_spoiler.aggravate:
            return False

        if any([
            self.corpse_spoiler.acidic,
            self.corpse_spoiler.poisonous,
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

        self.always_peaceful = False
        if self.offset == 267: # shopkeeper
            self.always_peaceful = True

    @classmethod
    def names(cls):
        names = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            names.add(cls(numeral).name)
        return names

class ObjectGlyph(Glyph):
    OFFSET = nethack.GLYPH_OBJ_OFF
    COUNT = nethack.NUM_OBJECTS

    OBJECT_CLASSES = [
        'RANDOM_CLASS', # 0
        'ILLOBJ_CLASS', # 1
        'WEAPON_CLASS', # 2
        'ARMOR_CLASS', # 3
        'RING_CLASS', # 4
        'AMULET_CLASS', # 5
        'TOOL_CLASS', # 6
        'FOOD_CLASS', # 7
        'POTION_CLASS', # 8
        'SCROLL_CLASS', # 9
        'SPBOOK_CLASS', # 10
        'WAND_CLASS', # 11
        'COIN_CLASS', # 12
        'GEM_CLASS', # 13
        'ROCK_CLASS', # 14
        'BALL_CLASS', # 15
        'CHAIN_CLASS', # 16
        'VENOM_CLASS', # 17
    ]

    OBJECT_CLASS_LABEL_IN_INVENTORY = [
        'RANDOM_CLASS', # 0
        'ILLOBJ_CLASS', # 1
        'Weapons', # 2
        'Armor', # 3
        'Rings', # 4
        'Amulets', # 5
        'Tools', # 6
        'Comestibles', # 7
        'Potions', # 8
        'Scrolls', # 9
        'Spellbooks', # 10
        'Wands', # 11
        'Coins', # 12
        'Gems/Stones', # 13
        'Gems/Stones', # 14
        'BALL_CLASS', # 15
        'CHAIN_CLASS', # 16
        'VENOM_CLASS', # 17
    ]

    class ObjectIdentity():
        def __init__(self, name, numeral):
            self.numeral = numeral

            self.name = name

            #self.spoiler = spoiler

    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET
        obj = nethack.objclass(nethack.glyph_to_obj(numeral))
        # Has data:
        # 'oc_class', 'oc_color', 'oc_cost', 'oc_delay', 'oc_descr_idx', 'oc_name_idx', 'oc_oprop',
        # 'oc_prob', 'oc_weight'
        self.object_class_numeral = ord(obj.oc_class)
        self.object_class_name = self.__class__.OBJECT_CLASSES[self.object_class_numeral]
        self.appearance = nethack.OBJ_DESCR(obj) or nethack.OBJ_NAME(obj)
        self.name = nethack.OBJ_NAME(obj) # This is only sometimes accurate. Not for shuffled objects.

        #####################################
        ##### Objects that get shuffled #####
        #####################################

        is_shuffled = False
        fully_shuffled_classes = ['WAND_CLASS', 'POTION_CLASS', 'RING_CLASS', 'AMULET_CLASS']
        if self.object_class_name == 'ARMOR_CLASS':
            shuffled_helms = range(78, 82) # get owned, dunce caps
            shuffled_cloaks = range(125, 129)
            shuffled_gloves = range(136, 140)
            shuffled_boots = range(143, 150)
            is_shuffled = self.offset in shuffled_helms or self.offset in shuffled_cloaks or self.offset in shuffled_gloves or self.offset in shuffled_boots

        elif self.object_class_name == 'POTION_CLASS':
            water_offset = 297
            is_shuffled = self.offset != water_offset

        elif self.object_class_name == 'SPBOOK_CLASS':
            magic_and_non_unique = range(340, 380) # blank, paperback, book of the dead are excluded
            is_shuffled = self.offset in magic_and_non_unique

        elif self.object_class_name == 'SCROLL_CLASS': # scrolls work in a unique way, where none of them have names (except blank paper) only appearances. what does this affect?
            blank_paper_offset = 339
            is_shuffled = self.offset != blank_paper_offset

        elif self.object_class_name in fully_shuffled_classes:
            is_shuffled = True

        self.is_shuffled = is_shuffled

        ####################################

        if not self.is_shuffled:
            self.identity = self.__class__.ObjectIdentity(self.name, self.numeral)
        else:
            self.identity = None

    def walkable(self, character):
        return True

    def safe_non_perishable(self, character):
        assert self.object_class_name == "FOOD_CLASS"

        if character.character.sick_from_tripe() and  "tripe" in self.appearance:
            return False

        safe_non_perishable = ("glob" not in self.appearance and "egg" not in self.appearance)
        return safe_non_perishable

    def desirable_object(self, character):
        safe_food = self.object_class_name == "FOOD_CLASS" and self.safe_non_perishable(character)
        good_armor = self.object_class_name == "ARMOR_CLASS" # add some logic here at some point
        desirable = safe_food or good_armor
        return desirable

    @classmethod
    def names(cls):
        names = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            # print(f"{cls} {numeral}")
            names.add(cls(numeral).name)
        return names

    @classmethod
    def distinct_appearances(cls): # distinct, not unique
        appearances = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            # print(f"{cls} {numeral}")
            appearances.add(cls(numeral).appearance)
        return appearances

    @classmethod
    def duplicated_appearances(cls):
        appearances = []
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            # print(f"{cls} {numeral}")
            appearances.append(cls(numeral).appearance)

        duplicates = [k for k,v in Counter(appearances).items() if v>1]

        return duplicates

    @classmethod
    def identities_by_glyph(cls):
        identities = {}
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            identity = cls(numeral).identity

            if identity is not None:
                identities[numeral] = identity

        return identities

    @classmethod
    def identities_by_name(cls):
        identities = {}
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            glyph = cls(numeral)

            if glyph.identity is not None:
                identities[glyph.name] = glyph.identity

        return identities

    @classmethod
    def identities_by_appearance(cls):
        duplicated_appearances = cls.duplicated_appearances()
        identities = {}
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            glyph = cls(numeral)
            if glyph.identity is not None and glyph.appearance not in duplicated_appearances:
                identities[glyph.appearance] = glyph.identity

        return identities


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
        self.is_open_door = self.offset > 11 and self.offset < 15
        self.is_closed_door = self.offset == 15 or self.offset == 16
        self.is_downstairs = self.offset == 24 or self.offset == 26
        self.is_upstairs = self.offset == 23 or self.offset == 25
        self.is_trap = self.offset > 41 and self.offset < 65
        
    def walkable(self, character):
        return (self.offset > 18 and self.offset < 32) or self.is_open_door or self.is_closed_door or self.is_downstairs or self.is_upstairs

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

    def desirable_object(self, character):
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
    ObjectGlyph,
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

if not len(GLYPH_NUMERAL_LOOKUP.keys()) == 5_976:
    raise Exception("Surprising number of glyphs")

GLYPH_NAME_LOOKUP = {}
for glyph in GLYPH_NUMERAL_LOOKUP.values():
    if not glyph.name:
        continue
    GLYPH_NAME_LOOKUP[glyph.name] = glyph

GLYPH_NUMERAL_LOOKUP[5976] = None # Weird and bad thing in the inventory

ALL_OBJECT_NAMES = ObjectGlyph.names()

ALL_OBJECT_APPEARANCES = ObjectGlyph.distinct_appearances() # problem with this and blank paper + blank spellbook

OBJECT_IDENTITIES_BY_GLYPH = ObjectGlyph.identities_by_glyph()

#for k,v in OBJECT_IDENTITIES_BY_GLYPH.items():
#    print(k, v.name)

UNSHUFFLED_OBJECT_IDENTITIES_BY_APPEARNCE = ObjectGlyph.identities_by_appearance()
OBJECT_IDENTITIES_BY_NAME = ObjectGlyph.identities_by_name()


def get_by_name(klass, name):
    glyph = GLYPH_NAME_LOOKUP.get(name, None)
    if not isinstance(glyph, klass):
        if environment.env.debug:
            pdb.set_trace()
        raise Exception("bad glyph name")
    return glyph
