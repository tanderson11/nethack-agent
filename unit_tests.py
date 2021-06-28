import unittest

import menuplan

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
    }
    def test_all_test_values(self):
        for key, value in self.test_values.items():
            self.assertEqual(value, menuplan.InteractiveInventoryMenu.MenuItem("foo", "a", False, key).item_appearance)

if __name__ == '__main__':
    unittest.main()
