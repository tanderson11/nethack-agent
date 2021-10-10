import inventory
import constants
from typing import NamedTuple

def want_charging(wand, character):
    if wand is None:
        return False
    if wand.recharges == 1:
        return None

    charging = character.inventory.get_item(inventory.Scroll, name="charging", sort_key=lambda s: s.BUC)
    if charging is None:
        return True
    if charging.BUC != constants.BUC.blessed:
        needed_holy_water = 1 if charging.BUC == constants.BUC.uncursed else 2
        holy_water = character.inventory.get_item(inventory.Potion, name="water", instance_selector=lambda i: i.BUC==constants.BUC.blessed)
        if holy_water is None:
            return True

        if holy_water.quantity < needed_holy_water:
            return True

    return False

class ItemName(NamedTuple):
    type: type
    name: str

class WishlistItem(NamedTuple):
    item: ItemName
    alternate: ItemName = None
    modifier: str = None
    pure_addition: bool = False

    def wish_string(self):
        return f'{self.modifier} {self.item.name}'

charging = WishlistItem(ItemName(inventory.Scroll, 'charging'), modifier='2 blessed')
basic_wishlist = (
    WishlistItem(ItemName(inventory.Armor, 'gray dragon scale mail'), modifier='blessed +2'),
    WishlistItem(ItemName(inventory.Armor, 'boots of speed'), modifier='blessed +2 fireproof'),
    WishlistItem(ItemName(inventory.Armor, 'shield of reflection'), alternate=ItemName(inventory.Amulet, 'amulet of reflection'), modifier='blessed +2'),
    WishlistItem(ItemName(inventory.Armor, 'gauntlets of power'), modifier='blessed +2 rustproof'),
    WishlistItem(ItemName(inventory.Armor, 'cloak of protection'), modifier='blessed +2 rotproof'),
    WishlistItem(ItemName(inventory.Tool, 'magic marker'), modifier='blessed', pure_addition=True),
)

def get_wish(character, wand=None):
    if want_charging(wand, character):
        return charging, charging.wish_string()
    
    for wishlist_line in basic_wishlist:
        if wishlist_line.pure_addition is True:
            return wishlist_line.wish_string()

        item_in_inventory = character.inventory.get_item(wishlist_line.item.type, name=wishlist_line.item.name)
        if item_in_inventory is not None:
            continue
        
        if wishlist_line.alternate is not None:
            alternate_item_in_inventory = character.inventory.get_item(wishlist_line.alternate.type, wishlist_line.alternate.name)
            if alternate_item_in_inventory is not None:
                continue

        return wishlist_line, wishlist_line.wish_string()


# Special roles:
# Monk? at least early game[late game you want SoR and GDSM anyway though ...]
# Barbarian? two handed weapon?
# 

# Charging
# GDSM / SDSM
# Boots of speed
# missing [MR / Reflection]
# Cloak of protection
# Gauntlets of power

# Artifact weapon [non-Excalibur classes] [+2 blessed rustproof Grayswandir; +2 blessed rustproof Frost Brand; +2 blessed rustproof Excalibur]

# basic kit / competitive slots
# SoR
# AoLS / AoMB
# GDSM
# Dwarvish iron helm
# Cloak of protection
# Boots of speed
# Hawaiian shirt
# gaunlets of power

# Artifacts?

# Shared misc / purely additional
# magic marker
# wand of death
# stethoscope
# luckstone
# ring of levitation
# ring of conflict
# ring of free action
# ring of slow digestion
# bag of holding
# wand of teleportation
# unicorn horn
# lembas wafer