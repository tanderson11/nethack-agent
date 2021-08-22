import unittest
from unittest.mock import MagicMock

import enum
from typing import NamedTuple
import numpy as np

import constants
import map
import menuplan
import inventory as inv
import glyphs as gd
import agents.custom_agent

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
    glyphs = np.full((21, 79), 2359)
    for k, v in vals.items():
        glyphs[k] = v
    return glyphs

class TestDLevelMap(unittest.TestCase):
    def setUp(self):
        self.lmap = map.DLevelMap(0, 1, make_glyphs())

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

if __name__ == '__main__':
    unittest.main()
