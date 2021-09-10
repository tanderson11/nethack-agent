import unittest
from unittest.mock import MagicMock

import enum
from typing import NamedTuple
import numpy as np

from nle import nethack

import constants
import inventory as inv
import map
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
        "a +0 pick-axe (alternate weapon; not wielded)": "pick-axe",
        "a corroded +1 long sword (weapon in hand)": "long sword",
        "a thoroughly rusty +0 battle-axe (weapon in hands)": "battle-axe",
        "a rusty corroded +1 long sword (weapon in hand)": "long sword",
        "a rusty thoroughly corroded +1 long sword (weapon in hand)": "long sword",
        "a heavy iron ball (chained to you)": "heavy iron ball",
        "a blessed fireproof +10 ornamental cope": "ornamental cope", # You'd actually know the cloak
        "the blessed +7 silver saber": "silver saber", # Change to a Grayswandir test at some point
    }
    def test_all_test_values(self):
        for key, value in self.test_values.items():
            print(key)

            item = menuplan.ParsingInventoryMenu.MenuItem(
                MagicMock(run_state=agents.custom_agent.RunState()), None, "a", False, key            )
            if item.item is None:
                import pdb; pdb.set_trace()
            self.assertEqual(value, item.item._seen_as)

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
        #ItemTestInputs(1913, "38 +2 darts (at the ready)"): ItemTestValues(inv.Weapon, "dart"),
        ItemTestInputs(1978, "an iron skull cap"): ItemTestValues(inv.Armor, "orcish helm"),
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
            monster_name = agents.custom_agent.RecordedMonsterDeath.involved_monster(key)
            self.assertEqual(value, agents.custom_agent.RecordedMonsterDeath(None, None, monster_name).monster_name)

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
            monster_name = agents.custom_agent.RecordedMonsterFlight.involved_monster(key)
            self.assertEqual(value, agents.custom_agent.RecordedMonsterFlight(None, monster_name).monster_name)

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
        self.lmap = map.DMap().make_level_map(0, 2, make_glyphs(), (0,0))

    def test_update(self):
        upstair = gd.get_by_name(gd.CMapGlyph, 'upstair')
        monster = gd.get_by_name(gd.MonsterAlikeGlyph, 'fire ant')
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), None)
        self.assertEqual(self.lmap.get_dungeon_glyph((1, 1)), None)
        self.lmap.update((1,1), make_glyphs({(0, 0): upstair.numeral}))
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), upstair)
        self.assertEqual(self.lmap.get_dungeon_glyph((1, 1)), None)
        self.lmap.update((1,1), make_glyphs({(0, 0): monster.numeral}))
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
        self.lmap.add_traversed_staircase((0,0), (0, 1), (0,0), 'down')
        self.assertEqual(self.lmap.get_dungeon_glyph((0, 0)), downstair)
        staircase = self.lmap.staircases[(0,0)]
        self.assertEqual((0,0), staircase.start_location)

    def test_search_counter(self):
        self.assertEqual(self.lmap.searches_count_map[(0,0)], 0)
        self.assertEqual(self.lmap.searches_count_map[(1,0)], 0)
        self.assertEqual(self.lmap.searches_count_map[(0,1)], 0)
        self.assertEqual(self.lmap.searches_count_map[(1,1)], 0)
        self.lmap.update((0, 0), make_glyphs())
        self.lmap.log_search((0, 0))
        self.assertEqual(self.lmap.searches_count_map[(0,0)], 1)
        self.assertEqual(self.lmap.searches_count_map[(1,0)], 1)
        self.assertEqual(self.lmap.searches_count_map[(0,1)], 1)
        self.assertEqual(self.lmap.searches_count_map[(1,1)], 1)
        self.lmap.update((1, 1), make_glyphs())
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
        self.lmap.add_traversed_staircase((0,0), (map.Branches.DungeonsOfDoom.value, 1), (0,0), 'up')
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((1,1), (map.Branches.DungeonsOfDoom.value, 1), (0,0), 'down')
        self.assertEqual(self.lmap.need_egress(), False)

    def test_need_egress_at_mine_branch(self):
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((0,0), (map.Branches.DungeonsOfDoom.value, 1), (0,0), 'up')
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((1,1), (map.Branches.GnomishMines.value, 1), (0,0), 'down')
        self.assertEqual(self.lmap.need_egress(), True)
        self.lmap.add_traversed_staircase((2,2), (map.Branches.DungeonsOfDoom.value, 1), (0,0), 'down')
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
            self.assertEqual(v, gd.CMapGlyph.is_safely_walkable_check(np.array([gd.get_by_name(gd.CMapGlyph, k).offset])).all(), k)

        for k, v in true_labels.items():
            glyph = gd.GLYPH_NAME_LOOKUP[k]
            self.assertEqual(glyph.walkable(None), v, k)

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
            dmap.make_level_map(0, 1, glyphs, (0,0)),
            None,
            None,
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


class TestArmorProposals(unittest.TestCase):
    def test(self):
        pass

class TestWeaponPickup(unittest.TestCase):
    test_header = "Pick up what?\n\nWeapons\n"

    test_values = {
        "d - an uncursed dagger": "d",
        "a - a cursed dagger": None,
        "a - a blessed +5 club": None,
        "a - a scimitar": "a",
        "a - a blessed -2 scimitar": None,
        "a - a blessed +5 scimitar": "a",
        "a - a runed broadsword": None
    }

    def test(self):
        run_state = agents.custom_agent.RunState()

        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Tourist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral',
        )
        character.set_class_skills()

        inventory = inv.PlayerInventory([], [], [], [])
        inventory.wielded_weapon = inv.BareHands()
        run_state.character = character
        run_state.character.inventory = inventory

        for k,v in self.test_values.items():

            menu_text = string_to_tty_chars(self.test_header + k)
            interactive_menu = menuplan.InteractivePickupMenu(run_state, select_desirable=True)
            result = interactive_menu.search_through_rows(menu_text)
            print(result)

            if v is None:
                self.assertEqual(result, None)
            else:
                self.assertEqual(result.character, v)

class InteractiveMenu(unittest.TestCase):
    labeled_text = """Pick up what?

Armor
a - a +0 plumed helmet (being worn) (unpaid, 13 zorkmids)
b - a pair of leather gloves (for sale, 30 zorkmids)
c - a pair of buckled boots >> armor|desirable
Weapons
d - an uncursed dagger >> extra weapons|desirable
Comestibles
e - a food ration >> comestibles|desirable
Scrolls
f - a scroll labeled VE FORBRYDERNE >> desirable
g - 2 uncursed scrolls of teleportation >> teleport scrolls|desirable
Potions
h - a smoky potion
i - a blessed potion of full healing >> healing potions
Wands
j - an iron wand >> desirable
k - an uncursed wand of teleportation (0:6) >> teleport wands|desirable

(end)
"""

    def test_pickup(self):
        # use | between selectors for items picked by many selectors
        # TK `e - a lichen corpse >> comestibles`

        string, expected = labeled_string_to_raw_and_expected(self.labeled_text)
        text = string_to_tty_chars(string)

        for selector_name in menuplan.InteractivePickupMenu.selectors.keys():
            # enforce that every selector has a test written for it
            print(selector_name)
            self.assertTrue(selector_name in expected.keys())

            #import pdb; pdb.set_trace()
            interactive_menu = menuplan.InteractivePickupMenu(agents.custom_agent.RunState(), selector_name)
            result = interactive_menu.search_through_rows(text)
            print(result)

            # need to collate multiple results TK
            acutally_selected_letters = set([result.character])

            # check that selector correctly pulls the letters
            self.assertEqual(acutally_selected_letters, expected[selector_name])

    def test_pickup_desirable(self):
        character = agents.custom_agent.Character(
            base_class=constants.BaseRole.Tourist,
            base_race=constants.BaseRace.human,
            base_sex='male',
            base_alignment='neutral',
        )
        character.set_class_skills()
        run_state = agents.custom_agent.RunState()
        run_state.character = character

        character.inventory = inv.PlayerInventory([], [], [], [])
        character.inventory.armaments = inv.ArmamentSlots()
        character.inventory.wielded_weapon = inv.BareHands()

        string, expected = labeled_string_to_raw_and_expected(self.labeled_text)
        text = string_to_tty_chars(string)
        interactive_menu = menuplan.InteractivePickupMenu(run_state, select_desirable=True)
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
        self.assertEqual(len(expected['desirable']), len(results))


if __name__ == '__main__':
    unittest.main()
