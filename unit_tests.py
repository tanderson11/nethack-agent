import unittest
from unittest.mock import MagicMock

import enum
from typing import NamedTuple
import numpy as np

from nle import nethack

import constants
import inventory as inv
import map
import monster_messages
import menuplan
import neighborhood
import glyphs as gd
import agents.custom_agent
import environment

environment.env = environment.make_environment(log_runs=False)

class SpecialValues(enum.Enum):
    same_name = "SAME NAME"

class TestItemRegex(unittest.TestCase):
    test_values = {
        "a +0 dagger (alternate weapon; not wielded)": "dagger",
        "a blessed +1 quarterstaff (weapon in hands)": "quarterstaff",
        "a puce potion": "puce",
        "a scroll labeled READ ME": "READ ME",
        "a scroll labeled NR 9": "NR 9",
        "2 food rations": "food ration",
        "30 +2 darts": "dart",
        "an unlabeled scroll": "unlabeled scroll",
        "an uncursed sack containing 1 item": "sack",
        #"a blessed tin of yellow mold": "tin", # currently broken, waiting on a better pattern
        "a +0 pick-axe (alternate weapon; not wielded)": "pick-axe",
        "a corroded +1 long sword (weapon in hand)": "long sword",
        "a thoroughly rusty +0 battle-axe (weapon in hands)": "battle-axe",
        "a rusty corroded +1 long sword (weapon in hand)": "long sword",
        "a rusty thoroughly corroded +1 long sword (weapon in hand)": "long sword",
        "a heavy iron ball (chained to you)": "heavy iron ball",
        "a blessed fireproof +10 ornamental cope": "ornamental cope", # You'd actually know the cloak
        "the blessed +7 silver saber": "silver saber", # Change to a Grayswandir test at some point
    }
    paperback_values = {
        "a paperback book named Guards! Guards! (for sale, 30 zorkmids)": None,
        "a paperback book named The Shepherd's Crown (for sale, 30 zorkmids)": None,
    }

    holy_water_values = {
        "4 potions of holy water": ("water", constants.BUC.blessed),
        "4 potions of unholy water": ("water", constants.BUC.cursed),
    }
    def test_all_test_values(self):
        global_identity_map = gd.GlobalIdentityMap()
        character = MagicMock(global_identity_map=global_identity_map)
        for key, value in self.test_values.items():
            print(key)

            item = menuplan.ParsingInventoryMenu.MenuItem(
                MagicMock(player_character=character), None, "a", False, key
            )
            if item.item is None:
                import pdb; pdb.set_trace()
            self.assertEqual(value, item.item._seen_as)

    def test_holy_water(self):
        global_identity_map = gd.GlobalIdentityMap()
        character = MagicMock(global_identity_map=global_identity_map)
        for key, value in self.holy_water_values.items():
            print(key)

            item = menuplan.ParsingInventoryMenu.MenuItem(
                MagicMock(player_character=character), None, "a", False, key
            )
            #if item.item is None:
            #    import pdb; pdb.set_trace()
            self.assertEqual(value[0], item.item.identity.name())
            self.assertEqual(value[1], item.item.BUC)

    def test_paperbacks_dont_crash(self):
        global_identity_map = gd.GlobalIdentityMap()
        character = MagicMock(global_identity_map=global_identity_map)
        for key, value in self.paperback_values.items():
            print(key)

            item = menuplan.ParsingInventoryMenu.MenuItem(
                MagicMock(player_character=character), None, "a", False, key
            )
            #if item.item is None:
            #    import pdb; pdb.set_trace()
            self.assertEqual(value, item.item)


class TestObjectGlyphIdentities(unittest.TestCase):
    global_identity_map = gd.GlobalIdentityMap()
    def test_from_numeral(self):
        test_values = {
            # Amulets
            2087: None, # shuffled
            2094: "Amulet of Yendor",
            # Armor
            1981: "cornuthaum",
            1985: None, # shuffled
            # Food
            2153: "glob of brown pudding",
            2177: "tin",
            # Gems
            2341: "worthless piece of red glass",
            2348: "luckstone",
            # Potions
            2184: None, # shuffled
            2203: "water",
            # Rings
            2058: None, # shuffled
            # Scrolls
            2245: "blank paper",
            2222: None, # shuffled
            # Spellbooks,
            2288: "Book of the Dead",
            2287: "novel",
            2286: "blank paper",
            2271: None,
            # Tools
            2144: "Bell of Opening",
            2143: "Candelabrum of Invocation",
            2142: "unicorn horn",
            2100: "bag of holding",
            2101: "bag of tricks",
            # Wands
            2289: None, # shuffled
            # Weapons
            1909: "orcish arrow",
            1965: "club",
        }

        for numeral, name in test_values.items():
            identity = self.global_identity_map.identity_by_numeral[numeral]
            self.assertEqual(name, identity.name())

class TestItemParsing(unittest.TestCase):
    '''
        (2021, "an uncursed +0 Hawaiian shirt (being worn)"): ,

    '''

    class ItemTestInputs(NamedTuple):
        numeral: int
        item_str: str

    class ItemTestValues(NamedTuple):
        oclass: type
        name_in_inventory: str
        name_in_stack: str = SpecialValues.same_name

    #ItemTestValues(1299, "a lichen corpse", gd.CorpseGlyph, "lichen"),
    test_values = {
        ItemTestInputs(2104, "an uncursed credit card"): ItemTestValues(inv.Tool, "credit card"),
        ItemTestInputs(1913, "38 +2 darts (at the ready)"): ItemTestValues(inv.Weapon, "dart"),
        ItemTestInputs(1978, "an iron skull cap"): ItemTestValues(inv.Armor, "orcish helm"),
        ItemTestInputs(1299, "6 lichen corpses"): ItemTestValues(inv.Food, "lichen corpse"),
        ItemTestInputs(1466, "a lizard corpse"): ItemTestValues(inv.Food, "lizard corpse"),
        ItemTestInputs(2316, "a gold piece"): ItemTestValues(inv.Coin, "gold piece"),
        #ItemTestInputs(2177, "2 uncursed tins of kobold meat"): ItemTestValues(inv.Food, "tin"),
        ItemTestInputs(2103, "an osaku"): ItemTestValues(inv.Tool, "lock pick"),
        ItemTestInputs(2042, "a +0 pair of yugake (being worn)"): ItemTestValues(inv.Armor, "leather gloves"),
        ItemTestInputs(2042, "a +0 pair of old gloves (being worn)"): ItemTestValues(inv.Armor, None),
        ItemTestInputs(2034, "a blessed +2 tattered cape"): ItemTestValues(inv.Armor, None),
        ItemTestInputs(2181, "2 cursed yellow potions"): ItemTestValues(inv.Potion, None),
        ItemTestInputs(2181, "3 uncursed potions of healing"): ItemTestValues(inv.Potion, "healing"),
        ItemTestInputs(2349, "an uncursed gray stone"): ItemTestValues(inv.Gem, "loadstone", name_in_stack=None),
        ItemTestInputs(1942, "an uncursed runed broadsword"): ItemTestValues(inv.Weapon, "elven broadsword", name_in_stack=None),
        ItemTestInputs(2311, "a long wand"): ItemTestValues(inv.Wand, None),
    }

    test_elimination_values = {
        ItemTestInputs(2031, "a blessed +2 cloak of magic resistance"): ItemTestValues(inv.Armor, "cloak of magic resistance"),
        ItemTestInputs(2032, "a blessed +2 cloak of protection"): ItemTestValues(inv.Armor, "cloak of protection"),
        ItemTestInputs(2033, "a blessed +2 cloak of invisibility"): ItemTestValues(inv.Armor, "cloak of invisibility"),
        ItemTestInputs(2034, "a blessed +2 ornamental cope"): ItemTestValues(inv.Armor, "cloak of displacement"),
    }

    def test_elimination(self):
        global_identity_map = gd.GlobalIdentityMap()
        for inputs, values in self.test_elimination_values.items():
            item = inv.ItemParser.make_item_with_glyph(global_identity_map, inputs.numeral, inputs.item_str)
            self.assertEqual(item.identity.name(), values.name_in_inventory)

    def test_recognition_with_numeral(self):
        #return
        for inputs, values in self.test_values.items():
            global_identity_map = gd.GlobalIdentityMap()
            item = inv.ItemParser.make_item_with_glyph(global_identity_map, inputs.numeral, inputs.item_str)
            self.assertEqual(item.identity.name(), values.name_in_inventory)

    def test_recognition_with_category(self):
        #return
        for inputs, values in self.test_values.items():
            print(inputs)
            global_identity_map = gd.GlobalIdentityMap()
            category = inv.ItemParser.category_by_glyph_class[values.oclass.glyph_class]
            item = inv.ItemParser.make_item_with_string(global_identity_map, inputs.item_str, category=category)
            #print(item)
            self.assertTrue(isinstance(item, values.oclass))
            if values.name_in_stack == SpecialValues.same_name:
                self.assertEqual(values.name_in_inventory, item.identity.name())
            else:
                self.assertEqual(item.identity.name(), values.name_in_stack)

    def test_recognition_with_only_str(self):
        for inputs, values in self.test_values.items():
            global_identity_map = gd.GlobalIdentityMap()
            item = inv.ItemParser.make_item_with_string(global_identity_map, inputs.item_str)
            self.assertTrue(isinstance(item, values.oclass))
            if values.name_in_stack == SpecialValues.same_name:
                self.assertEqual(values.name_in_inventory, item.identity.name())
            else:
                self.assertEqual(item.identity.name(), values.name_in_stack)

class TestMonsterKill(unittest.TestCase):
    test_values = {
        "You kill the lichen!": "lichen",
        "You feel more confident in your weapon skills.  You kill the kobold!": "kobold",
        "You kill the newt!  The grid bug bites!  You get zapped!": "newt",
        "You kill the poor little dog!": "little dog",
        "You kill the incubus of Kos!": "incubus",
        "You kill the invisible hill orc!": "hill orc",
        "You kill the saddled pony!": "pony",
    }

    def test_all_test_values(self):
        for key, value in self.test_values.items():
            monster_name = monster_messages.RecordedMonsterDeath.involved_monster(key)
            self.assertEqual(value, monster_messages.RecordedMonsterDeath(None, None, monster_name).monster_name)

class TestMonsterFlight(unittest.TestCase):
    test_values = {
        "You hit the straw golem!  The straw golem turns to flee.": "straw golem",
        "You hit the gnome.  The gnome turns to flee.": "gnome",
        "You hit the Green-elf.  The Green-elf turns to flee.": "Green-elf",
        "You hit Croesus!  Croesus turns to flee.": "Croesus",
        "Demogorgon turns to flee.": "Demogorgon", # is this optimistic ... maybe
        #The invisible Demogorgon casts a spell!  A monster appears from nowhere!  The kitten turns to flee.  The fire elemental turns to flee.  The arch-lich casts a spell!--More--
    }

    def test_all_test_values(self):
        for key, value in self.test_values.items():
            print(value)
            monster_name = monster_messages.RecordedMonsterFlight.involved_monster(key)
            self.assertEqual(value, monster_messages.RecordedMonsterFlight(None, monster_name).monster_name)

class TestAttributeScreen(unittest.TestCase):
    def test_easy_case(self):
        screen_content = """
                          You are a Plunderess, a level 1 female human Barbarian.
                          You are neutral, on a mission for Crom                 
                          who is opposed by Mitra (lawful) and Set (chaotic).    """
        run_state = agents.custom_agent.RunState()
        run_state.reading_base_attributes = True
        run_state.update_base_attributes(screen_content)
        self.assertEqual(constants.BaseRole.Barbarian, run_state.character.base_class)
        self.assertEqual(constants.BaseRace.human, run_state.character.base_race)
        self.assertEqual("female", run_state.character.base_sex)
        self.assertEqual("neutral", run_state.character.base_alignment)
        self.assertEqual("Crom", run_state.gods_by_alignment['neutral'])
        self.assertEqual("Mitra", run_state.gods_by_alignment['lawful'])
        self.assertEqual("Set", run_state.gods_by_alignment['chaotic'])

    def test_gendered_class(self):
        screen_content = """
                          You are a Troglodyte, a level 1 dwarven Cavewoman.      
                          You are lawful, on a mission for Anu                    
                          who is opposed by Ishtar (neutral) and Anshar (chaotic)."""
        run_state = agents.custom_agent.RunState()
        run_state.reading_base_attributes = True
        run_state.update_base_attributes(screen_content)
        self.assertEqual(constants.BaseRace.dwarf, run_state.character.base_race)
        self.assertEqual("female", run_state.character.base_sex)
        self.assertEqual(constants.BaseRole.Caveperson, run_state.character.base_class)
        self.assertEqual("lawful", run_state.character.base_alignment)
        self.assertEqual("Ishtar", run_state.gods_by_alignment['neutral'])
        self.assertEqual("Anu", run_state.gods_by_alignment['lawful'])
        self.assertEqual("Anshar", run_state.gods_by_alignment['chaotic'])

    def test_complicated_gods(self):
        screen_content = """
                          You are a Rambler, a level 1 male human Tourist.      
                          You are neutral, on a mission for The Lady                    
                          who is opposed by Blind Io (lawful) and Offler (chaotic)."""
        run_state = agents.custom_agent.RunState()
        run_state.reading_base_attributes = True
        run_state.update_base_attributes(screen_content)
        self.assertEqual(constants.BaseRace.human, run_state.character.base_race)
        self.assertEqual("male", run_state.character.base_sex)
        self.assertEqual(constants.BaseRole.Tourist, run_state.character.base_class)
        self.assertEqual("neutral", run_state.character.base_alignment)
        self.assertEqual("The Lady", run_state.gods_by_alignment['neutral'])
        self.assertEqual("Blind Io", run_state.gods_by_alignment['lawful'])
        self.assertEqual("Offler", run_state.gods_by_alignment['chaotic'])

class TestSpecialRoleAttributes(unittest.TestCase):
    def test_body_armor_penalty(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Monk,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )

        self.assertTrue(character.body_armor_penalty())

    def test_can_eat_tripe(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Caveperson,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )

        self.assertFalse(character.sick_from_tripe())

class TestInnateIntrinsics(unittest.TestCase):
    def test_monk_example(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Monk,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )
        character.set_innate_intrinsics()
        self.assertTrue(character.has_intrinsic(constants.Intrinsics.speed))
        self.assertFalse(character.has_intrinsic(constants.Intrinsics.poison_resistance))
        self.assertFalse(character.has_intrinsic(constants.Intrinsics.warning))

        character.experience_level = 3
        character.set_innate_intrinsics()
        self.assertTrue(character.has_intrinsic(constants.Intrinsics.speed))
        self.assertTrue(character.has_intrinsic(constants.Intrinsics.poison_resistance))
        self.assertFalse(character.has_intrinsic(constants.Intrinsics.warning))


def make_glyphs(vals = {}):
    glyphs = np.full(constants.GLYPHS_SHAPE, 2359)
    for k, v in vals.items():
        glyphs[k] = v
    return glyphs

class TestDLevelMap(unittest.TestCase):
    def setUp(self):
        self.lmap = map.DMap().make_level_map(map.DCoord(0,2), 0, make_glyphs(), (0,0))

    def test_update(self):
        upstair = gd.get_by_name(gd.CMapGlyph, 'upstair')
        monster = gd.get_by_name(gd.MonsterAlikeGlyph, 'fire ant')
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), None)
        self.assertEqual(self.lmap.get_dungeon_glyph((1, 1)), None)
        self.lmap.update(True, 0, (1,1), make_glyphs({(0, 0): upstair.numeral}))
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), upstair)
        self.assertEqual(self.lmap.get_dungeon_glyph((1, 1)), None)
        self.lmap.update(True, 0, (1,1), make_glyphs({(0, 0): monster.numeral}))
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), upstair)
        self.assertEqual(self.lmap.get_dungeon_glyph((1, 1)), None)

    def test_add_feature(self):
        upstair = gd.get_by_name(gd.CMapGlyph, 'upstair')
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), None)
        self.lmap.add_feature((0,0), upstair)
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), upstair)

    def test_add_traversed_staircase(self):
        downstair = gd.get_by_name(gd.CMapGlyph, 'dnstair')
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), None)
        self.lmap.add_traversed_staircase((0,0), map.DCoord(0, 1), (0,0), map.DirectionThroughDungeon.down)
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), downstair)
        staircase = self.lmap.staircases[(0,0)]
        self.assertEqual((0,0), staircase.start_location)

    def test_search_counter(self):
        self.assertEqual(self.lmap.searches_count_map[(0,0)], 0)
        self.assertEqual(self.lmap.searches_count_map[(1,0)], 0)
        self.assertEqual(self.lmap.searches_count_map[(0,1)], 0)
        self.assertEqual(self.lmap.searches_count_map[(1,1)], 0)
        self.lmap.update(True, 0, (0, 0), make_glyphs())
        self.lmap.log_search((0, 0))
        self.assertEqual(self.lmap.searches_count_map[(0,0)], 1)
        self.assertEqual(self.lmap.searches_count_map[(1,0)], 1)
        self.assertEqual(self.lmap.searches_count_map[(0,1)], 1)
        self.assertEqual(self.lmap.searches_count_map[(1,1)], 1)
        self.lmap.update(True, 0, (1, 1), make_glyphs())
        self.lmap.log_search((1, 1))
        self.assertEqual(self.lmap.searches_count_map[(0,0)], 2)
        self.assertEqual(self.lmap.searches_count_map[(1,0)], 2)
        self.assertEqual(self.lmap.searches_count_map[(0,1)], 2)
        self.assertEqual(self.lmap.searches_count_map[(1,1)], 2)
        self.assertEqual(self.lmap.searches_count_map[(1,2)], 1)
        self.assertEqual(self.lmap.searches_count_map[(2,1)], 1)
        self.assertEqual(self.lmap.searches_count_map[(2,2)], 1)
        self.assertEqual(self.lmap.searches_count_map[(0,2)], 1)
        self.assertEqual(self.lmap.searches_count_map[(2,0)], 1)

    def test_need_egress(self):
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((0,0), map.DCoord(map.Branches.DungeonsOfDoom.value, 1), (0,0), map.DirectionThroughDungeon.up)
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((1,1), map.DCoord(map.Branches.DungeonsOfDoom.value, 1), (0,0), map.DirectionThroughDungeon.down)
        self.assertEqual(self.lmap.need_egress(), False)

    def test_need_egress_at_mine_branch(self):
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((0,0), map.DCoord(map.Branches.DungeonsOfDoom.value, 1), (0,0), map.DirectionThroughDungeon.up)
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((1,1), map.DCoord(map.Branches.GnomishMines.value, 1), (0,0), map.DirectionThroughDungeon.down)
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((2,2), map.DCoord(map.Branches.DungeonsOfDoom.value, 1), (0,0), map.DirectionThroughDungeon.down)
        self.assertEqual(self.lmap.need_egress(), False)

class TestCMapGlyphs(unittest.TestCase):
    def test_safely_walkable(self):
        true_labels = {
            'stone': False, # 0
            'vwall': False, # 1
            'hwall': False, # 2
            'tlcorn': False, # 3
            'trcorn': False, # 4
            'blcorn': False, # 5
            'brcorn': False, # 6
            'crwall': False, # 7
            'tuwall': False, # 8
            'tdwall': False, # 9
            'tlwall': False, # 10
            'trwall': False, # 11
            'ndoor': True, # 12
            'vodoor': True, # 13
            'hodoor': True, # 14
            'vcdoor': False, # 15
            'hcdoor': False, # 16
            'bars': False, # 17
            'tree': False, # 18
            'room': True, # 19
            'darkroom': True, # 20
            'corr': True, # 21
            'litcorr': True, # 22
            'upstair': True, # 23
            'dnstair': True, # 24
            'upladder': True, # 25
            'dnladder': True, # 26
            'altar': True, # 27
            'grave': True, # 28
            'throne': True, # 29
            'sink': True, # 30
            'fountain': True, # 31
            'pool': False, # 32
            'ice': True, # 33
            'lava': False, # 34
            'vodbridge': False, # 35
            'hodbridge': False, # 36
            'vcdbridge': False, # 37
            'hcdbridge': False, # 38
            'air': False, # 39
            'cloud': False, # 40
            'water': False, # 41
            'arrow_trap': False, # 42
            'dart_trap': False, # 43
            'falling_rock_trap': False, # 44
            'squeaky_board': False, # 45
            'bear_trap': False, # 46
            'land_mine': False, # 47
            'rolling_boulder_trap': False, # 48
            'sleeping_gas_trap': False, # 49
            'rust_trap': False, # 50
            'fire_trap': False, # 51
            'pit': False, # 52
            'spiked_pit': False, # 53
            'hole': False, # 54
            'trap_door': False, # 55
            'teleportation_trap': False, # 56
            'level_teleporter': False, # 57
            'magic_portal': True, # 58
            'web': False, # 59
            'statue_trap': False, # 60
            'magic_trap': False, # 61
            'anti_magic_trap': False, # 62
            'polymorph_trap': False, # 63
            'vibrating_square': True, # 64
            'vbeam': False, # 65
            'hbeam': False, # 66
            'lslant': False, # 67
            'rslant': False, # 68
            'digbeam': False, # 69
            'flashbeam': False, # 70
            'boomleft': False, # 71
            'boomright': False, # 72
            'ss1': False, # 73
            'ss2': False, # 74
            'ss3': False, # 75
            'ss4': False, # 76
            'poisoncloud': False, # 77
            'goodpos': False, # 78
            'sw_tl': False, # 79
            'sw_tc': False, # 80
            'sw_tr': False, # 81
            'sw_ml': False, # 82
            'sw_mr': False, # 83
            'sw_bl': False, # 84
            'sw_bc': False, # 85
            'sw_br': False, # 86
        }
        for k, v in true_labels.items():
            glyph = gd.GLYPH_NAME_LOOKUP[k]
            self.assertEqual(v, gd.walkable(np.array(glyph.numeral)), k)

        for k, v in true_labels.items():
            glyph = gd.GLYPH_NAME_LOOKUP[k]
            self.assertEqual(gd.walkable(np.array(glyph.numeral)), v, k)

    def test_room_floor(self):
        true_labels = {
            'stone': False, # 0
            'vwall': False, # 1
            'hwall': False, # 2
            'tlcorn': False, # 3
            'trcorn': False, # 4
            'blcorn': False, # 5
            'brcorn': False, # 6
            'crwall': False, # 7
            'tuwall': False, # 8
            'tdwall': False, # 9
            'tlwall': False, # 10
            'trwall': False, # 11
            'ndoor': False, # 12
            'vodoor': False, # 13
            'hodoor': False, # 14
            'vcdoor': False, # 15
            'hcdoor': False, # 16
            'bars': False, # 17
            'tree': False, # 18
            'room': True, # 19
            'darkroom': True, # 20
            'corr': False, # 21
            'litcorr': False, # 22
            'upstair': True, # 23
            'dnstair': True, # 24
            'upladder': True, # 25
            'dnladder': True, # 26
            'altar': True, # 27
            'grave': True, # 28
            'throne': True, # 29
            'sink': True, # 30
            'fountain': True, # 31
            'pool': True, # 32
            'ice': True, # 33
            'lava': True, # 34
            'vodbridge': False, # 35
            'hodbridge': False, # 36
            'vcdbridge': False, # 37
            'hcdbridge': False, # 38
            'air': False, # 39
            'cloud': False, # 40
            'water': False, # 41
            'arrow_trap': True, # 42
            'dart_trap': True, # 43
            'falling_rock_trap': True, # 44
            'squeaky_board': True, # 45
            'bear_trap': True, # 46
            'land_mine': True, # 47
            'rolling_boulder_trap': True, # 48
            'sleeping_gas_trap': True, # 49
            'rust_trap': True, # 50
            'fire_trap': True, # 51
            'pit': True, # 52
            'spiked_pit': True, # 53
            'hole': True, # 54
            'trap_door': True, # 55
            'teleportation_trap': True, # 56
            'level_teleporter': True, # 57
            'magic_portal': True, # 58
            'web': True, # 59
            'statue_trap': True, # 60
            'magic_trap': True, # 61
            'anti_magic_trap': True, # 62
            'polymorph_trap': True, # 63
            'vibrating_square': True, # 64
            'vbeam': False, # 65
            'hbeam': False, # 66
            'lslant': False, # 67
            'rslant': False, # 68
            'digbeam': False, # 69
            'flashbeam': False, # 70
            'boomleft': False, # 71
            'boomright': False, # 72
            'ss1': False, # 73
            'ss2': False, # 74
            'ss3': False, # 75
            'ss4': False, # 76
            'poisoncloud': False, # 77
            'goodpos': False, # 78
            'sw_tl': False, # 79
            'sw_tc': False, # 80
            'sw_tr': False, # 81
            'sw_ml': False, # 82
            'sw_mr': False, # 83
            'sw_bl': False, # 84
            'sw_bc': False, # 85
            'sw_br': False, # 86
        }

        for k, v in true_labels.items():
            self.assertEqual(v, gd.CMapGlyph.is_room_floor_check(np.array([gd.get_by_name(gd.CMapGlyph, k).offset])).all(), k)

class TestNeighborhood(unittest.TestCase):
    def setUp(self):
        room_numeral = gd.get_by_name(gd.CMapGlyph, 'room').numeral
        ruby_numeral = gd.get_by_name(gd.ObjectGlyph, 'ruby').numeral
        glyphs = make_glyphs({
            (0,0): room_numeral,
            (0,1): room_numeral,
            (0,2): ruby_numeral,
        })
        current_square = neighborhood.CurrentSquare(
            arrival_time=10,
            location=(0,0),
            dcoord=(0,1)
        )
        dmap = map.DMap()
        self.neighborhood = neighborhood.Neighborhood(
            10,
            current_square,
            glyphs,
            dmap.make_level_map(map.DCoord(0,1), 0, glyphs, (0,0)),
            None,
            None,
            False,
        )

    def test_attributes(self):
        self.assertEqual(self.neighborhood.absolute_player_location, (0, 0))

    def test_pathfind(self):
        path = self.neighborhood.path_to_desirable_objects()
        self.assertEqual(path.path_action, nethack.actions.CompassDirection.E)


def labeled_string_to_raw_and_expected(multiline_str):
    expected_by_selector = {}
    string = ""
    for l in multiline_str.split("\n"):
        try:
            game_line, expected_selectors = l.split(">>")
        except ValueError:
            string += l + "\n"
            continue

        string += game_line.rstrip() + "\n"
        corresponding_chr = game_line[0]
        expected_selectors = expected_selectors.lstrip().split("|")
        for s in expected_selectors:
            if len(s) > 0:
                try:
                    expected_by_selector[s].add(corresponding_chr)
                except KeyError:
                    expected_by_selector[s] = set([corresponding_chr])

    return string, expected_by_selector        

def string_to_tty_chars(multiline_str):
    return [[ord(c) for c in line] for line in multiline_str.split("\n")]

class TestBUC(unittest.TestCase):
    class BUCTestOut(NamedTuple):
        non_priest_out: enum.Enum
        priest_out: enum.Enum

    from_glyph_test_values = {
        (1947, "a runed broadsword named Stormbringer"): BUCTestOut(constants.BUC.unknown, constants.BUC.uncursed),
        (1947, "the blessed +5 Stormbringer"): BUCTestOut(constants.BUC.blessed, constants.BUC.blessed),
        (2348, "a gray stone named The Heart of Ahriman"): BUCTestOut(constants.BUC.unknown, constants.BUC.uncursed),
        (2348, "the uncursed Heart of Ahriman"): BUCTestOut(constants.BUC.uncursed, constants.BUC.uncursed),
        (1943, "a long sword named Excalibur"): BUCTestOut(constants.BUC.unknown, constants.BUC.uncursed),
        (1943, "the +0 Excalibur"): BUCTestOut(constants.BUC.uncursed, constants.BUC.uncursed),
        # different amulet glyphs still can be the Eye because shuffled
        (2090, "the blessed Eye of the Aethiopica"): BUCTestOut(constants.BUC.blessed, constants.BUC.blessed),
        (2091, "the cursed Eye of the Aethiopica"): BUCTestOut(constants.BUC.cursed, constants.BUC.cursed),
    }

    def test(self):
        for k,buc in self.from_glyph_test_values.items():
            numeral, item_str = k
            print(k,buc.non_priest_out)

            global_identity_map = gd.GlobalIdentityMap()
            character = MagicMock(global_identity_map=global_identity_map)

            artifact = inv.ItemParser.make_item_with_glyph(global_identity_map, numeral, item_str)

            #print(result.item.artifact_identity)
            self.assertEqual(artifact.BUC, buc.non_priest_out, artifact.identity.name())

    def priest_test(self):
        for k,buc in self.from_glyph_test_values.items():
            numeral, item_str = k
            print(k,buc.priest_out)

            global_identity_map = gd.GlobalIdentityMap()
            global_identity_map.is_priest = True
            character = MagicMock(global_identity_map=global_identity_map)

            artifact = inv.ItemParser.make_item_with_glyph(global_identity_map, numeral, item_str)

            #print(result.item.artifact_identity)
            self.assertEqual(artifact.BUC, buc.priest_out)

class TestArtifacts(unittest.TestCase):
    test_header = "Pick up what?\n\nWeapons\n"

    class ArtifactValue(NamedTuple):
        artifact_name: str
        base_item_name: str

    from_str_test_values = {
        "n - a runed broadsword named Stormbringer (weapon in hand)": ArtifactValue("Stormbringer", "runesword"),
        "n - the blessed +5 Stormbringer": ArtifactValue("Stormbringer", "runesword"),
        "m - a gray stone named The Heart of Ahriman": ArtifactValue("Heart of Ahriman", "luckstone"),
        "m - the uncursed Heart of Ahriman": ArtifactValue("Heart of Ahriman", "luckstone"),
        "o - a long sword named Excalibur": ArtifactValue("Excalibur", "long sword"),
        "o - the +0 Excalibur": ArtifactValue("Excalibur", "long sword"),
    }

    from_glyph_test_values = {
        (1947, "a runed broadsword named Stormbringer"): ArtifactValue("Stormbringer", "runesword"),
        (1947, "the blessed +5 Stormbringer"): ArtifactValue("Stormbringer", "runesword"),
        (2348, "a gray stone named The Heart of Ahriman"): ArtifactValue("Heart of Ahriman", "luckstone"),
        (2348, "the uncursed Heart of Ahriman"): ArtifactValue("Heart of Ahriman", "luckstone"),
        (1943, "a long sword named Excalibur"): ArtifactValue("Excalibur", "long sword"),
        (1943, "the +0 Excalibur"): ArtifactValue("Excalibur", "long sword"),
        # different amulet glyphs still can be the Eye because shuffled
        (2090, "the blessed Eye of the Aethiopica"): ArtifactValue("Eye of the Aethiopica", "amulet of ESP"),
        (2091, "the blessed Eye of the Aethiopica"): ArtifactValue("Eye of the Aethiopica", "amulet of ESP"),
        (2092, "the blessed Eye of the Aethiopica"): ArtifactValue("Eye of the Aethiopica", "amulet of ESP"),
    }

    def test_base_gets_identified(self):
        numeral, item_str = (2090, "a hexagonal amulet named The Eye of the Aethiopica")
        global_identity_map = gd.GlobalIdentityMap()
        #character = MagicMock(global_identity_map=global_identity_map)

        artifact = inv.ItemParser.make_item_with_glyph(global_identity_map, numeral, item_str)

        numeral, item_str = (2090, "a hexagonal amulet")
        base = inv.ItemParser.make_item_with_glyph(global_identity_map, numeral, item_str)
        self.assertEqual(base.identity.name(), "amulet of ESP")


    def test_from_glyph(self):
        for k,v in self.from_glyph_test_values.items():
            numeral, item_str = k
            print(k,v)

            global_identity_map = gd.GlobalIdentityMap()
            #character = MagicMock(global_identity_map=global_identity_map)

            artifact = inv.ItemParser.make_item_with_glyph(global_identity_map, numeral, item_str)

            #print(result.item.artifact_identity)
            artifact_name, name = v
            self.assertEqual(artifact_name, artifact.identity.artifact_name)
            self.assertEqual(name, artifact.identity.name())

    def test_from_string(self):
        for k,v in self.from_str_test_values.items():
            global_identity_map = gd.GlobalIdentityMap()
            character = MagicMock(global_identity_map=global_identity_map)

            menu_text = string_to_tty_chars(k)
            interactive_menu = menuplan.ParsingInventoryMenu(character)
            result = interactive_menu.search_through_rows(menu_text)
            print(result.item.identity.name())

            artifact_name, name = v

            self.assertEqual(artifact_name, result.item.identity.artifact_name)
            self.assertEqual(name, result.item.identity.name())

class TestWeaponPickup(unittest.TestCase):
    test_header = "Pick up what?\n\nWeapons\n"

    test_values = {
        "d - an uncursed dagger": "d",
        "a - a cursed dagger": None,
        "a - a blessed +5 club": "a",
        "a - a scimitar": "a",
        "a - a blessed -2 scimitar": "a",
        "a - a blessed +5 scimitar": "a",
        "a - a runed broadsword": None
    }

    def test(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Tourist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral',
        )
        character.set_class_skills()

        inventory = inv.PlayerInventory(np.array([]), np.array([]), np.array([]), np.array([]))
        inventory.wielded_weapon = inv.BareHands()
        character.inventory = inventory
        global_identity_map = gd.GlobalIdentityMap()
        character.global_identity_map = global_identity_map

        for k,v in self.test_values.items():
            menu_text = string_to_tty_chars(self.test_header + k)
            interactive_menu = menuplan.InteractivePickupMenu(character, select_desirable='desirable')
            result = interactive_menu.search_through_rows(menu_text)
            print(result)

            if v is None:
                self.assertEqual(result, None, result)
            else:
                self.assertEqual(result.character, v)

class InteractiveMenu(unittest.TestCase):
    labeled_text = """Pick up what?

Coins
$ - 1600 gold pieces >> desirable
Armor
a - a +0 plumed helmet >> armor|desirable
b - a +0 plumed helmet (being worn) (unpaid, 13 zorkmids)
c - a pair of leather gloves (for sale, 30 zorkmids)
d - a pair of buckled boots >> armor|desirable
Weapons
e - an uncursed dagger >> extra weapons|desirable
Comestibles
f - a food ration >> comestibles|desirable
g - a lichen corpse >> desirable
Scrolls
h - a scroll labeled VE FORBRYDERNE >> desirable
i - 2 uncursed scrolls of teleportation >> teleport scrolls|desirable
Potions
j - a smoky potion
k - a blessed potion of full healing >> healing potions|desirable
Wands
l - an iron wand >> desirable
m - a wand of teleportation (0:6) >> teleport wands|desirable

(end)
"""

    def test_pickup(self):
        # use | between selectors for items picked by many selectors
        # TK `e - a lichen corpse >> comestibles`
        global_identity_map = gd.GlobalIdentityMap()
        character = MagicMock(global_identity_map=global_identity_map)
        string, expected = labeled_string_to_raw_and_expected(self.labeled_text)
        text = string_to_tty_chars(string)

        for selector_name in menuplan.InteractivePickupMenu.selectors.keys():
            if selector_name != 'desirable':
                continue
            # enforce that every selector has a test written for it
            print(selector_name)
            self.assertTrue(selector_name in expected.keys())

            #import pdb; pdb.set_trace()
            interactive_menu = menuplan.InteractivePickupMenu(character, selector_name)
            result = interactive_menu.search_through_rows(text)
            print(result)

            # need to collate multiple results TK
            actually_selected_letters = set([result.character])
            print(actually_selected_letters)

            # check that selector correctly pulls the letters
            self.assertEqual(actually_selected_letters, expected[selector_name], actually_selected_letters)


    def test_pickup_desirable(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Tourist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral',
        )
        character.set_class_skills()
        character.attributes = MagicMock(charisma=18)
        global_identity_map = gd.GlobalIdentityMap()
        character.global_identity_map = global_identity_map

        character.inventory = inv.PlayerInventory(np.array([]), np.array([]), np.array([]), np.array([]))
        character.inventory.armaments = inv.ArmamentSlots()
        character.inventory.wielded_weapon = inv.BareHands()

        string, expected = labeled_string_to_raw_and_expected(self.labeled_text)
        text = string_to_tty_chars(string)
        interactive_menu = menuplan.InteractivePickupMenu(character, select_desirable='desirable')
        results = []
        for i in range(0, 20):
            try:
                result = interactive_menu.search_through_rows(text)
            except menuplan.EndOfMenu:
                break
            string = string.replace(f"{result.character} - ", f"{result.character} + ")
            text = string_to_tty_chars(string)
            results.append(result)
        # The armor and food ration
        self.assertEqual(len(expected['desirable']), len(results), [r.item_text for r in results])

class TestDungeonDirection(unittest.TestCase):
    def test_out_succeed(self):
        # in the dungeons of doom, trying to get out
        current_dcoord = map.DCoord(0, 5)
        target_dcoord = map.DCoord(2,100)

        dmap = map.DMap()
        dmap.add_branch_traversal(map.DCoord(0, 4), map.DCoord(2, 3))

        dmap.target_dcoords = {target_dcoord.branch: target_dcoord}
        direction = dmap.dungeon_direction_to_best_target(current_dcoord).direction
        self.assertEqual(direction, map.DirectionThroughDungeon.up)
    def test_out_succeed_overlapping_branches(self):
        # in the dungeons of doom, trying to get out
        current_dcoord = map.DCoord(0, 5)
        target_dcoord = map.DCoord(2,100)

        dmap = map.DMap()
        dmap.add_branch_traversal(map.DCoord(0, 4), map.DCoord(2, 3))
        dmap.add_branch_traversal(map.DCoord(0, 4), map.DCoord(3, 3))

        dmap.target_dcoords = {target_dcoord.branch: target_dcoord}
        direction = dmap.dungeon_direction_to_best_target(current_dcoord).direction
        self.assertEqual(direction, map.DirectionThroughDungeon.up)
    def test_out_fail(self):
        # in the dungeons of doom trying to get out but can't
        current_dcoord = map.DCoord(0, 5)
        target_dcoord = map.DCoord(2,100)
        dmap = map.DMap()
        dmap.target_dcoords = {target_dcoord.branch: target_dcoord}
        with self.assertRaisesRegex(Exception, "Can't figure out how to get anywhere"):
            dmap.dungeon_direction_to_best_target(current_dcoord)

    def test_same_level(self):
        # trying to get out of dungones
        current_dcoord = map.DCoord(0, 4)
        target_dcoord = map.DCoord(2,2)
        dmap = map.DMap()
        dmap.add_branch_traversal(map.DCoord(0, 4), map.DCoord(2, 3))
        dmap.target_dcoords = {target_dcoord.branch: target_dcoord}
        direction = dmap.dungeon_direction_to_best_target(current_dcoord).direction
        self.assertEqual(direction, map.DirectionThroughDungeon.flat)
    def test_in_succeed(self):
        # out of the dungeons of doom, trying to get in
        current_dcoord = map.DCoord(2, 2)
        target_dcoord = map.DCoord(0,1)
        dmap = map.DMap()
        dmap.add_branch_traversal(map.DCoord(0, 4), map.DCoord(2, 3))
        dmap.target_dcoords = {target_dcoord.branch: target_dcoord}
        direction = dmap.dungeon_direction_to_best_target(current_dcoord).direction
        self.assertEqual(direction, map.DirectionThroughDungeon.down)
    def test_through_succeed(self):
        # out of the dungeons of doom, trying to go through
        current_dcoord = map.DCoord(3, 2)
        target_dcoord = map.DCoord(2,3)

        dmap = map.DMap()
        dmap.add_branch_traversal(map.DCoord(0, 4), map.DCoord(3, 3))
        dmap.add_branch_traversal(map.DCoord(0, 7), map.DCoord(2, 3))

        dmap.target_dcoords = {target_dcoord.branch: target_dcoord}
        direction = dmap.dungeon_direction_to_best_target(current_dcoord).direction
        self.assertEqual(direction, map.DirectionThroughDungeon.down)

    def test_through_fail(self):
        # out of dungeons of doom, trying to go through but can't find
        current_dcoord = map.DCoord(3, 2)
        target_dcoord = map.DCoord(2,3)

        dmap = map.DMap()
        dmap.add_branch_traversal(map.DCoord(0, 7), map.DCoord(2, 3))

        dmap.target_dcoords = {target_dcoord.branch: target_dcoord}
        with self.assertRaisesRegex(Exception, "Can't figure out how to get anywhere"):
            dmap.dungeon_direction_to_best_target(current_dcoord)

        
class TestCharacterUpdateFromMessage(unittest.TestCase):
    grab_messages = {
        "You cannot escape from the lichen!": "lichen",
        "The giant eel bites!  The giant eel swings itself around you!": "giant eel",
        "The owlbear hits!  The owlbear hits!  The owlbear grabs you!": "owlbear",
        "The large mimic hits!": "large mimic",
        "It grabs you!  It bites!  It bites!  It bites!  It bites!  It bites!": "invisible monster",
    }

    release_messages = [
        "You pull free from the violet fungus.",
        "The owlbear releases you.  The grid bug bites!",
    ]
    def test_monster_grabs(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Tourist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral',
        )

        for m, v in self.grab_messages.items():
            character.update_from_message(m, 0)
            self.assertEqual(v, character.held_by.monster_glyph.name)
            character.held_by = None
    
    def test_free_from_monster(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Tourist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral',
        )

        for m in self.release_messages:
            character.held_by = True
            character.update_from_message(m, 0)
            self.assertEqual(None, character.held_by)

class ItemTestInputs(NamedTuple):
    numeral: int
    item_class: type
    item_str: str
    inventory_letter: int = None

class TestWeaponWield(unittest.TestCase):
    pass

def make_inventory(global_identity_map, inventory_inputs):
    numerals = []
    strings = []
    oclasses = []
    letters = []
    for item_inputs in inventory_inputs:
        numeral, item_class, item_str, inventory_letter = item_inputs
        zeroed_string = np.zeros((128), dtype='uint8')
        string = np.array(string_to_tty_chars(item_str)[0], dtype='uint8')
        zeroed_string[0:len(string)] = string
        oclass = item_class.glyph_class.class_number

        numerals.append(numeral)
        strings.append(zeroed_string)
        oclasses.append(oclass)
        letters.append(inventory_letter)
    
    #print(np.array(strings))
    inventory = inv.PlayerInventory(global_identity_map, np.array(letters), np.array(oclasses), np.array(strings), inv_glyphs=np.array(numerals))
    return inventory

class TestWeaponWielding(unittest.TestCase):
    def test_tin_opener(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Tourist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral'
        )
        character.set_class_skills()

        inventory = [
            ItemTestInputs(2120, inv.Tool, "an uncursed tin opener (weapon in hand)", ord("a")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        character.inventory = make_inventory(global_identity_map, inventory)

        proposal = character.inventory.proposed_weapon_changes(character)
        self.assertEqual(chr(proposal.inventory_letter), '-')

    def test_complex(self):
        return True
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Archeologist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )
        character.set_class_skills()

        inventory = [
            ItemTestInputs(1939, inv.Weapon, "a curved sword (weapon in hand)", ord("a")),
            ItemTestInputs(1923, inv.Weapon, "a dagger (at the ready)", ord("b")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        character.inventory = make_inventory(global_identity_map, inventory)

        proposal = character.inventory.proposed_weapon_changes(character)
        assert proposal is None

class TestArmorWearing(unittest.TestCase):
    def test_good_armor_vs_bad(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Samurai,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )
        character.set_class_skills()

        inventory = [
            ItemTestInputs(2020, inv.Armor, "an uncursed +0 leather jacket (being worn)", ord("a")),
            ItemTestInputs(2012, inv.Armor, "an elven mithril-coat", ord("b")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        character.inventory = make_inventory(global_identity_map, inventory)

        proposal = character.inventory.proposed_attire_changes(character)
        self.assertEqual(len(proposal.proposed_items), 1)
        self.assertEqual(len(proposal.proposal_blockers[0]), 1)

    def test_medium_unoccupied_armor(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Wizard,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral'
        )
        character.set_class_skills()

        inventory = [
            ItemTestInputs(2033, inv.Armor, "a blessed +0 cloak of magic resistance (being worn)", ord("a")),
            ItemTestInputs(1978, inv.Armor, "a blessed +0 orcish helm (being worn)", ord("b")),
            ItemTestInputs(2015, inv.Armor, "a scale mail", ord("c")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        character.inventory = make_inventory(global_identity_map, inventory)

        proposal = character.inventory.proposed_attire_changes(character)
        self.assertEqual(len(proposal.proposed_items), 1)
        self.assertEqual(len(proposal.proposal_blockers[0]), 1)

    def test_unrelated_blocker(self):
        # with unaffiliated cursed blocker

        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Samurai,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )
        character.set_class_skills()

        inventory = [
            ItemTestInputs(2020, inv.Armor, "an uncursed +0 leather jacket (being worn)", ord("a")),
            ItemTestInputs(2012, inv.Armor, "an elven mithril-coat", ord("b")),
            ItemTestInputs(1978, inv.Armor, "an iron skull cap", ord("c")),
            ItemTestInputs(1978, inv.Armor, "a cursed -1 iron skull cap (being worn)", ord("d")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        character.inventory = make_inventory(global_identity_map, inventory)

        proposal = character.inventory.proposed_attire_changes(character)
        #import pdb; pdb.set_trace()
        self.assertEqual(len(proposal.proposed_items), 1)
        self.assertEqual(len(proposal.proposal_blockers[0]), 1)

class TestRangedAttack(unittest.TestCase):
    def test_samurai_yumi(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Samurai,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )
        character.set_class_skills()

        inventory = [
            ItemTestInputs(1974, inv.Weapon, "a +0 yumi", ord("a")),
            ItemTestInputs(1911, inv.Weapon, "38 +0 ya", ord("b")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        character.inventory = make_inventory(global_identity_map, inventory)
        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(chr(ranged_proposal.wield_item.inventory_letter), "a")

        inventory = [
            #ItemTestInputs(1913, "38 +2 darts (at the ready)"),
            ItemTestInputs(1974, inv.Weapon, "a +0 yumi (weapon in hand)", ord("a")),
            ItemTestInputs(1911, inv.Weapon, "38 +0 ya", ord("b")),
        ]
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(chr(ranged_proposal.quiver_item.inventory_letter), "b")

        inventory = [
            ItemTestInputs(1974, inv.Weapon, "a +0 yumi (weapon in hand)", ord("a")),
            ItemTestInputs(1911, inv.Weapon, "38 +0 ya (in quiver)", ord("b")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        #import pdb; pdb.set_trace()
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(ranged_proposal.attack_plan.attack_action, nethack.actions.Command.FIRE)

    def test_throw(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Rogue,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='chaotic'
        )
        character.set_class_skills()
        global_identity_map = gd.GlobalIdentityMap()
        
        inventory = [
            ItemTestInputs(1913, inv.Weapon, "38 +2 darts", ord("c")),
            ItemTestInputs(1974, inv.Weapon, "a +0 yumi", ord("a")),
            ItemTestInputs(1911, inv.Weapon, "38 +0 ya", ord("b")),
        ]
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(chr(ranged_proposal.quiver_item.inventory_letter), "c")

        inventory = [
            ItemTestInputs(1913, inv.Weapon, "38 +2 darts (at the ready)", ord("c")),
            ItemTestInputs(1974, inv.Weapon, "a +0 yumi", ord("a")),
            ItemTestInputs(1911, inv.Weapon, "38 +0 ya", ord("b")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        #import pdb; pdb.set_trace()
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(ranged_proposal.attack_plan.attack_action, nethack.actions.Command.FIRE)

    def test_many(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Ranger,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='chaotic'
        )
        character.set_class_skills()

        global_identity_map = gd.GlobalIdentityMap()
        global_identity_map = gd.GlobalIdentityMap()

        inventory = [
            ItemTestInputs(1923, inv.Weapon, "a +1 dagger (weapon in hand)", ord("a")),
            ItemTestInputs(1972, inv.Weapon, "a +1 elven bow (alternate weapon; not wielded)", ord("b")),
            ItemTestInputs(1908, inv.Weapon, "26 +2 elven arrows (in quiver)", ord("c")),
        ]
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(chr(ranged_proposal.wield_item.inventory_letter), "b")

    def test_dont_throw_wielded(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Rogue,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='chaotic'
        )
        character.set_class_skills()
        global_identity_map = gd.GlobalIdentityMap()

        inventory = [
            ItemTestInputs(1923, inv.Weapon, "a dagger (weapon in hand)", ord("a")),
        ]
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(ranged_proposal, None)

        inventory = [
            ItemTestInputs(1913, inv.Weapon, "38 +2 darts (at the ready)", ord("c")),
            ItemTestInputs(1974, inv.Weapon, "a +0 yumi", ord("a")),
            ItemTestInputs(1911, inv.Weapon, "38 +0 ya", ord("b")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        #import pdb; pdb.set_trace()
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(ranged_proposal.attack_plan.attack_action, nethack.actions.Command.FIRE)


    def test_aklys(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Caveperson,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral'
        )
        character.set_class_skills()
        global_identity_map = gd.GlobalIdentityMap()

        inventory = [
            ItemTestInputs(1968, inv.Weapon, "a blessed +5 aklys (tethered weapon in hand)", ord("d")),
            ItemTestInputs(1913, inv.Weapon, "38 +2 darts (at the ready)", ord("c")),
            ItemTestInputs(1974, inv.Weapon, "a +0 yumi", ord("a")),
            ItemTestInputs(1911, inv.Weapon, "38 +0 ya", ord("b")),
        ]
        global_identity_map = gd.GlobalIdentityMap()
        #import pdb; pdb.set_trace()
        character.inventory = make_inventory(global_identity_map, inventory)

        preference = constants.ranged_default
        ranged_proposal = character.get_ranged_attack(preference)
        self.assertEqual(ranged_proposal.attack_plan.attack_action, nethack.actions.Command.THROW)

class TestDrop(unittest.TestCase):

    #ItemTestValues(1299, "a lichen corpse", gd.CorpseGlyph, "lichen"),
    test_values = {
        ItemTestInputs(2104, inv.Tool, "an uncursed credit card"): False,
        #ItemTestInputs(1913, "38 +2 darts (at the ready)"): ItemTestValues(inv.Weapon, "dart"),
        ItemTestInputs(1978, inv.Armor, "an iron skull cap"): False,
        #ItemTestInputs(2177, "2 uncursed tins of kobold meat"): ItemTestValues(inv.Food, "tin"),
        ItemTestInputs(2103, inv.Tool, "an osaku"): False,
        ItemTestInputs(2042, inv.Armor, "a +0 pair of yugake (being worn)"): False,
        ItemTestInputs(2042, inv.Armor, "a +0 pair of old gloves (being worn)"): False,
        ItemTestInputs(2034, inv.Armor, "a blessed +2 tattered cape"): False,
        ItemTestInputs(2181, inv.Potion, "2 cursed yellow potions"): True,
        ItemTestInputs(2181, inv.Potion, "3 uncursed potions of healing"): False,
        ItemTestInputs(2349, inv.Gem, "an uncursed gray stone"): True, # lodestone
        #ItemTestInputs(1942, "an uncursed runed broadsword"): ItemTestValues(inv.Weapon, "elven broadsword", name_in_stack=None),
        ItemTestInputs(2311, inv.Wand, "a long wand"): False,
        ItemTestInputs(1974, inv.Weapon, "a +0 yumi"): False,
        ItemTestInputs(1911, inv.Weapon, "38 +0 ya"): False,
        ItemTestInputs(2174, inv.Food, "6 food rations"): False,
    }

    def test_single_items(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Samurai,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='lawful'
        )
        character.set_class_skills()

        for inputs, do_drop in self.test_values.items():
            global_identity_map = gd.GlobalIdentityMap()
            numeral, item_class, item_str, _ = inputs
            string = np.array(string_to_tty_chars(item_str), dtype='uint8')
            oclass = item_class.glyph_class.class_number
            inventory = inv.PlayerInventory(global_identity_map, np.array([ord("a")]), np.array([oclass]), string, inv_glyphs=np.array([numeral]))
            character.inventory = inventory
            undesirable = inventory.all_undesirable_items(character)

            try:
                if do_drop:
                    self.assertEqual(len(undesirable), 1, item_str)
                else:
                    self.assertEqual(len(undesirable), 0, item_str)
            except:
                import pdb; pdb.set_trace()
                pass

class TestSpecialItemNames(unittest.TestCase):
    def test_no_charges(self):
        numeral, item_class, item_str, _ = ItemTestInputs(2311, inv.Wand, "a wand of digging named C_0")

        global_identity_map = gd.GlobalIdentityMap()
        string = np.array(string_to_tty_chars(item_str), dtype='uint8')
        oclass = item_class.glyph_class.class_number
        inventory = inv.PlayerInventory(global_identity_map, np.array([ord("a")]), np.array([oclass]), string, inv_glyphs=np.array([numeral]))
        item = inventory.all_items()[0]
        self.assertEqual(item.charges, 0)

class TestFloodMap(unittest.TestCase):
    def test_flood_center(self):
        start_mask = np.array([
            [False, False, False, False],
            [False, True, False, False],
            [False, False, False, False],
            [False, False, False, False],
        ])
        target_mask = np.array([
            [True, True, True, False],
            [True, True, True, False],
            [True, True, True, False],
            [False, False, False, False],
        ])
        end_mask = map.FloodMap.flood_one_level_from_mask(start_mask)
        self.assertTrue((end_mask == target_mask).all(), end_mask)
        self.assertEqual(end_mask.dtype, np.dtype('bool'))

    def test_flood_multi(self):
        start_mask = np.array([
            [False, False, False, False],
            [False, True, False, False],
            [False, False, True, False],
            [False, False, False, False],
        ])
        target_mask = np.array([
            [True, True, True, False],
            [True, True, True, True],
            [True, True, True, True],
            [False, True, True, True],
        ])
        end_mask = map.FloodMap.flood_one_level_from_mask(start_mask)
        self.assertTrue((end_mask == target_mask).all(), end_mask)
        self.assertEqual(end_mask.dtype, np.dtype('bool'))

    def test_flood_edge(self):
        start_mask = np.array([
            [False, False, False, False],
            [True, False, False, False],
            [False, False, False, False],
            [False, False, False, False],
        ])
        target_mask = np.array([
            [True, True, False, False],
            [True, True, False, False],
            [True, True, False, False],
            [False, False, False, False],
        ])
        end_mask = map.FloodMap.flood_one_level_from_mask(start_mask)
        self.assertTrue((end_mask == target_mask).all(), end_mask)
        self.assertEqual(end_mask.dtype, np.dtype('bool'))

    def test_flood_corner(self):
        start_mask = np.array([
            [True, False, False, False],
            [False, False, False, False],
            [False, False, False, False],
            [False, False, False, False],
        ])
        target_mask = np.array([
            [True, True, False, False],
            [True, True, False, False],
            [False, False, False, False],
            [False, False, False, False],
        ])
        end_mask = map.FloodMap.flood_one_level_from_mask(start_mask)
        self.assertTrue((end_mask == target_mask).all(), end_mask)
        self.assertEqual(end_mask.dtype, np.dtype('bool'))

# np.savetxt("foo.csv", ARS.rs.glyphs, delimiter=",", fmt='%s')
sokoban_1a_observation = """2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2362,2361,2368,2361,2361,2361,2361,2363,2359,2362,2361,2361,2361,2361,2363,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2382,2360,340,2174,2378,2378,2364,2361,2365,2379,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2411,2370,2363,2378,2353,2353,2379,2379,2379,2379,2353,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2411,2360,2360,2378,2378,2353,2353,2360,2379,2353,2379,2353,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2411,2360,2360,2379,2378,2378,2379,2360,2379,2379,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2411,2360,2364,2361,2361,2361,2368,2365,2353,2361,2361,2361,2361,2369,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2411,2360,2359,2359,2359,2359,2360,2379,2379,2379,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2411,2364,2361,2361,2361,2361,2365,2379,2379,2379,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2379,2411,2411,2411,2411,2353,2353,2353,2353,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2379,2362,2361,2361,2361,2363,2379,2379,2379,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2364,2361,2361,2365,2359,2359,2359,2364,2361,2361,2361,2361,2361,2361,2365,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359"""

sokoban_1b_observation = """2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2362,2361,2361,2361,2361,2363,2359,2359,2362,2361,2361,2361,2363,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2378,2378,2379,2360,2359,2359,2360,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2353,2378,2378,2364,2361,2361,2365,2379,2353,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2353,2379,2378,2378,2378,2147,2378,2353,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2379,2362,2361,2363,340,2362,2361,2363,2353,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2370,2361,2361,2367,2361,2367,2361,2366,2361,2365,2379,2361,2367,2363,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2379,2411,2411,2411,2382,2360,2379,2379,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2379,2362,2361,2361,2361,2369,2353,2379,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2364,2363,2411,2360,2359,2359,2359,2360,2379,2353,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2411,2364,2361,2361,2361,2365,2379,2353,2379,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2379,2411,2411,2411,2411,2353,2379,2353,2379,2379,2360,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2360,2379,2379,2362,2361,2361,2361,2361,2361,2361,2361,2361,2365,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2364,2361,2361,2365,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359
2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359,2359"""

def string_to_glyphs(input_string):
    retval = np.zeros(constants.GLYPHS_SHAPE)
    x = 0
    y = 0
    for line in input_string.split("\n"):
        for glyph_string in line.split(","):
            retval[y, x] = int(glyph_string)
            x += 1
        x = 0
        y += 1
    return retval

class TestSpecialLevelLoader(unittest.TestCase):
    def test_sokoban_1a(self):
        special_level = map.SpecialLevelLoader.load('sokoban_1a')
        self.assertEqual(special_level.cmap_glyphs[0,0], 2359)
        searcher = map.SpecialLevelSearcher([special_level])
        self.assertEqual(len(searcher.lookup[map.Branches.Sokoban][4]), 1)
        player_location = (6, 35)
        observed_level_map = map.DMap().make_level_map(
            map.DCoord(map.Branches.Sokoban, 4),
            0,
            string_to_glyphs(sokoban_1a_observation),
            player_location
        )
        observed_level_map.update(True, 0, player_location, string_to_glyphs(sokoban_1a_observation))
        observed_level_map.add_traversed_staircase(
            player_location,
            to_dcoord=map.DCoord(map.Branches.DungeonsOfDoom, 7),
            to_location=(0,0),
            direction=map.DirectionThroughDungeon.down
        )
        self.assertIsNotNone(searcher.match_level(observed_level_map, player_location))
        
    def test_sokoban_1b(self):
        special_level = map.SpecialLevelLoader.load('sokoban_1b')
        self.assertEqual(special_level.cmap_glyphs[0,0], 2359)
        searcher = map.SpecialLevelSearcher([special_level])
        self.assertEqual(len(searcher.lookup[map.Branches.Sokoban][4]), 1)
        player_location = (9, 38)
        observed_level_map = map.DMap().make_level_map(
            map.DCoord(map.Branches.Sokoban, 4),
            0,
            string_to_glyphs(sokoban_1b_observation),
            player_location
        )
        observed_level_map.update(True, 0, player_location, string_to_glyphs(sokoban_1b_observation))
        observed_level_map.add_traversed_staircase(
            player_location,
            to_dcoord=map.DCoord(map.Branches.DungeonsOfDoom, 7),
            to_location=(0,0),
            direction=map.DirectionThroughDungeon.down
        )
        self.assertIsNotNone(searcher.match_level(observed_level_map, player_location))

if __name__ == '__main__':
    unittest.main()
