import unittest

import menuplan
import agents.custom_agent

class TestItemRegex(unittest.TestCase):
    test_values = {
        "a +0 dagger (alternate weapon; not wielded)": "dagger",
        "a blessed +1 quarterstaff (weapon in hands)": "quarterstaff",
        "a puce potion": "puce potion",
        "a scroll labeled README": "scroll labeled README",
        "a scroll labeled NR 9": "scroll labeled NR 9",
        "a +0 pick-axe (alternate weapon; not wielded)": "pick-axe",
        "a corroded +1 long sword (weapon in hand)": "long sword",
        "a thoroughly rusty +0 battle-axe (weapon in hands)": "battle-axe",
        "a rusty corroded +1 long sword (weapon in hand)": "long sword",
    }
    def test_all_test_values(self):
        for key, value in self.test_values.items():
            self.assertEqual(value, menuplan.InteractiveInventoryMenu.MenuItem("foo", "a", False, key).item_appearance)

class TestMonsterKill(unittest.TestCase):
    test_values = {
        "You kill the lichen!": "lichen",
    }

    def test_all_test_values(self):
        for key, value in self.test_values.items():
            self.assertEqual(value, agents.custom_agent.RecordedMonsterDeath.generate_from_message(None, None, key).monster_name)

class TestAttributeScreen(unittest.TestCase):
    def test_easy_case(self):
        screen_content = """
                          You are a Plunderess, a level 1 female human Barbarian.
                          You are neutral, on a mission for Crom                 
                          who is opposed by Mitra (lawful) and Set (chaotic).    """
        run_state = agents.custom_agent.RunState()
        run_state.reading_base_attributes = True
        run_state.update_base_attributes(screen_content)
        self.assertEqual("human", run_state.base_race)
        self.assertEqual("female", run_state.base_sex)

    def test_gendered_class(self):
        screen_content = """
                          You are a Troglodyte, a level 1 dwarven Cavewoman.      
                          You are lawful, on a mission for Anu                    
                          who is opposed by Ishtar (neutral) and Anshar (chaotic)."""
        run_state = agents.custom_agent.RunState()
        run_state.reading_base_attributes = True
        run_state.update_base_attributes(screen_content)
        self.assertEqual("dwarf", run_state.base_race)
        self.assertEqual("female", run_state.base_sex)

if __name__ == '__main__':
    unittest.main()
