import pdb

from nle import nethack

class Glyph():
    OFFSET = 0
    COUNT = 0

    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET
        self.walkable = False

    @classmethod
    def mapping(cls):
        mapping = {}
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            # print(f"{cls} {numeral}")
            mapping[numeral] = cls(numeral)

        return mapping

    def __repr__(self):
        return "{} named {}".format(self.__class__, getattr(self, 'name', 'NO NAME DEFINED'))

class MonsterAlikeGlyph(Glyph):
    def __init__(self, numeral):
        self.numeral = numeral
        self.offset = self.numeral - self.__class__.OFFSET
        monster = nethack.permonst(nethack.glyph_to_mon(numeral))
        # Has data:
        # 'ac', 'cnutrit', 'cwt', 'geno', 'mcolor', 'mconveys', 'mflags1', 'mflags2', 'mflags3',
        # 'mlet', 'mlevel', 'mmove', 'mname', 'mr', 'mresists', 'msize', 'msound'
        self.name = monster.mname
        self.walkable = False

class MonsterGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_MON_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)
        self.never_melee = self.offset == 28 # floating eye

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
        self.walkable = True

    def is_identified_healing_object(self):
        if self.name is not None:
            return "healing" in self.name
        else:
            return False

    @classmethod
    def names(cls):
        names = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            # print(f"{cls} {numeral}")
            names.add(cls(numeral).name)
        return names

    @classmethod
    def appearances(cls):
        appearances = set()
        for numeral in range(cls.OFFSET, cls.OFFSET + cls.COUNT):
            # print(f"{cls} {numeral}")
            appearances.add(cls(numeral).appearance)
        return appearances

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
        self.is_wall = self.offset < 12
        self.is_open_door = self.offset > 11 and self.offset < 15
        self.is_closed_door = self.offset == 15 or self.offset == 16
        self.is_downstairs = self.offset == 24 or self.offset == 26
        self.is_upstairs = self.offset == 23 or self.offset == 25
        self.walkable = (self.offset > 18 and self.offset < 32) or self.is_open_door or self.is_closed_door or self.is_downstairs or self.is_upstairs
        self.is_trap = self.offset > 41 and self.offset < 65
        

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
        self.walkable = True

class InvisibleGlyph(Glyph):
    OFFSET = nethack.GLYPH_INVIS_OFF
    COUNT = 1

    def __init__(self, numeral):
        super().__init__(numeral)
        self.walkable = True # TK this is so we attack invisible glyphs

class DetectGlyph(MonsterAlikeGlyph):
    OFFSET = nethack.GLYPH_DETECT_OFF
    COUNT = nethack.NUMMONS

class CorpseGlyph(Glyph):
    OFFSET = nethack.GLYPH_BODY_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)
        self.walkable = True

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

class WarningGlyph(Glyph):
    OFFSET = nethack.GLYPH_WARNING_OFF
    COUNT = 6

class StatueGlyph(Glyph):
    OFFSET = nethack.GLYPH_STATUE_OFF
    COUNT = nethack.NUMMONS

    def __init__(self, numeral):
        super().__init__(numeral)
        self.walkable = True

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

GLYPH_LOOKUP = {}

for klass in klasses:
    GLYPH_LOOKUP.update(klass.mapping())

if not len(GLYPH_LOOKUP.keys()) == 5_976:
    raise Exception("Surprising number of glyphs")

GLYPH_LOOKUP[5976] = None # Weird and bad thing in the inventory

ALL_OBJECT_NAMES = ObjectGlyph.names()

ALL_OBJECT_APPEARANCES = ObjectGlyph.appearances()

# WALL_GLPYHS = 2360, 2361 = vertical + horizontal
# 2362, 2363, 2364, 2365 corners
WALL_GLYPHS = list(range(2360, 2366)) + [0]
DOWNSTAIRS_GLYPH = 2383
DOOR_GLYPHS = range(2374, 2376)
