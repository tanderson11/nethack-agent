import functools
import re
from typing import NamedTuple
from collections import OrderedDict
import pdb
import glyphs as gd
import environment
import numpy as np

from utilities import ARS


class ItemLike():
    class EquippedStatus():
        def __init__(self, item, parenthetical_status):
            self.status = None
            self.slot = None
            if parenthetical_status is not None:
                if "being worn" in parenthetical_status:
                    self.status = 'worn'
                    self.slot = item.identity.find_values('SLOT')

                elif "weapon in hand" in parenthetical_status:
                    self.status = 'wielded'

                    if parenthetical_status == "(weapon in hands)":
                        self.slot = ['hand', 'off_hand']
                    else:
                        self.slot = 'hand'

                elif "wielded in other hand" in parenthetical_status:
                    self.status = 'alt-wielded'
                    self.slot = 'off_hand'

                elif "on right hand" in parenthetical_status:
                    self.status = 'worn'
                    self.slot = 'right_ring'

                elif "on left hand" in parenthetical_status:
                    self.status = 'worn'
                    self.slot = 'left_ring'

                elif "in quiver" in parenthetical_status:
                    self.status = 'quivered'
                    self.slot = 'quiver'


   
    def __init__(self, quantity, BUC, parenthetical_status, condition, enhancement):
        self.quantity = quantity
        self.BUC = BUC

        self.parenthetical_status = parenthetical_status
        self.condition = condition
        self.enhancement = enhancement

        self.equipped_status = self.__class__.EquippedStatus(self, parenthetical_status)
        if self.equipped_status.slot is None and self.equipped_status.status is None:
            self.equipped_status = None

    def process_message(self, *args):
        self.identity.process_message(*args)

    def desirability(self, character):
        return None

class Item(ItemLike):
     #global_identity_map, glyph_numeral, quantity, BUC, equipped_status, condition, enhancement, inventory_letter
    def __init__(self, global_identity_map, glyph_numeral, quantity, BUC, parenthetical_status, condition, enhancement, inventory_letter=None):
        self.inventory_letter = inventory_letter
        self.glyph = gd.GLYPH_NUMERAL_LOOKUP[glyph_numeral]

        try:
            self.identity = global_identity_map.identity_by_numeral[glyph_numeral]
        except KeyError:
            print("No identity found for {}".format(glyph_numeral))

        super().__init__(quantity, BUC, parenthetical_status, condition, enhancement)

class Armor(Item):
    glyph_class = gd.ArmorGlyph

    def desirability(self, character):
        if character.character.body_armor_penalty() and self.identity.find_values('SLOT') == 'suit':
            return -10

        if self.enhancement is None:
            best_case_enhancement = 5
        else:
            best_case_enhancement = self.enhancement

        desirability = self.identity.find_values('AC').max() + best_case_enhancement
        return desirability

class Wand(Item):
    glyph_class = gd.WandGlyph

class Food(Item):
    glyph_class = gd.FoodGlyph

class Scroll(Item):
    glyph_class = gd.ScrollGlyph

class Potion(Item):
    glyph_class = gd.PotionGlyph

class Weapon(Item):
    glyph_class = gd.WeaponGlyph

class AmbiguousItem(ItemLike):
    '''An item found (by string) outside our inventory that we are not able to uniquely pin to a glyph/numeral, but still need to make decisions about.'''

    def __init__(self, global_identity_map, glyph_class, possible_glyphs, appearance, quantity, BUC, equipped_status, condition, enhancement):
        self.identity = None
        self.glyph_numeral = None
        self.possible_glyphs = possible_glyphs
        super().__init__(appearance, quantity, BUC, parenthetical_status, condition, enhancement)

class UnimplementedItemClassException(Exception):
    pass

class ItemParser():
    item_pattern = re.compile("^(a|an|[0-9]+) (blessed|uncursed|cursed)? ?( ?(very|thoroughly)? ?(burnt|rusty|corroded|rustproof|rotted|poisoned))* ?((\+|\-)[0-9]+)? ?([a-zA-Z9 -]+[a-zA-Z9]) ?(\(.+\))?$")
    
    ############## TODO ##################
    # These patterns are currently a bit #
    # overloaded because they are doing  #
    # things both with added words like  #
    # `ring` and with pluralization.     #
    ############## TODO ##################
    # \/ \/ \/ \/ \/ \/ \/ \/ \/ \/ \/ \/

    unidentified_class_patterns = {
        gd.ArmorGlyph: re.compile('pair of ([a-zA-Z ]+)$'),
        gd.WandGlyph: re.compile('([a-zA-Z])+ wand$'),
        gd.RingGlyph: re.compile('([a-zA-Z]+) ring$'),
        gd.AmuletGlyph: re.compile('([a-zA-Z]+) amulet$'),
        gd.PotionGlyph: re.compile('([a-zA-Z]+) potions?$'),
        gd.ScrollGlyph: re.compile('scrolls? labeled ([a-zA-Z0-9 ]+)$'), #NR9, multi word scrolls. TK unlabeled scroll(s)
        gd.SpellbookGlyph: re.compile('([a-zA-Z]+) spellbook$'),
    }
    identified_class_patterns = {
        gd.WandGlyph: re.compile('wand of ([a-zA-Z ]+)$'),
        gd.ArmorGlyph: re.compile('pair of ([a-zA-Z ]+)$'),
        gd.RingGlyph: re.compile('([a-zA-Z]+) ring$'),
        gd.AmuletGlyph: re.compile('amulet of ([a-zA-Z ]+)$'),
        gd.PotionGlyph: re.compile('potions? of ([a-zA-Z ]+)$'),
        gd.ScrollGlyph: re.compile('scrolls? of ([a-zA-Z0-9 ]+)$'), #NR9, multi word scrolls
        gd.SpellbookGlyph: re.compile('spellbook of ([a-zA-Z ]+)$'),
    }

    item_class_by_glyph_class = {
        gd.WandGlyph: Wand,
        gd.ArmorGlyph: Armor,
        gd.FoodGlyph: Food,
        gd.ScrollGlyph: Scroll,
        gd.PotionGlyph: Potion,
        gd.WeaponGlyph: Weapon,
    }

    #glyph_class_by_item_class = {v:k for k,v in item_class_by_glyph_class.items()}

    @staticmethod
    def decode_inventory_item(raw_item_repr):
        decoded = bytes(raw_item_repr).decode('ascii').rstrip('\x00')
        return decoded

    @classmethod
    def parse_inventory_item(cls, global_identity_map ,string, glyph_numeral=None, inventory_letter=None, category=None):
        match = re.match(cls.item_pattern, string)
        glyph_class = None

        if match:
            quantity_match = match[1]
            if quantity_match == "a" or quantity_match == "an":
                quantity = 1
            else:
                quantity = int(match[1])

            BUC = match[2]
            condition_intensifier = match[3]
            condition = match[4]
            if condition_intensifier is not None and condition is not None:
                condition = condition_intensifier + ' ' + condition

            enhancement = match[6]
            if enhancement is not None:
                enhancement = int(enhancement)

            description = match[8]
            
            appearance = None

            equipped_status = match[9]
        else: # our governing regex failed to find
            if environment.env.debug: pdb.set_trace()
            return None

        if glyph_numeral:
            glyph_class = type(gd.GLYPH_NUMERAL_LOOKUP[glyph_numeral])

        # if we don't have the numeral, we should still always be able to pull the glyph_class from the appearance somehow
        else:
            # we should first try just looking up the appearance to see if it's a raw match for an item
            # should we though? maybe only in classes that don't need futzing
            # TK TK TK
            # TK TK TK

            # next we imagine the object is unidentified, and we see if we can locate its appearance after applying our class specific regex
            # that extract the true (NLE) appearance from a looser string e.g. 'scroll labeled NR9' -> 'NR9'
            # we're searching as if unidentified first to not get goofed by plastic imitations of AoY,
            # which when NOT identified look like identified AoY
            for klass, pattern in cls.unidentified_class_patterns.items():
                class_pattern_match = re.search(pattern, description)
                if class_pattern_match:
                    appearance = class_pattern_match[1] # we've successfully defuzzed the appearance!
                    glyph_class = klass
                    print('UNIDENTIFIED', klass)

                    # if we find an appearance, we should then look it up to see if it unambiguously identifies the glyph, appearance-wise
                    possible_glyphs = global_identity_map.glyph_by_appearance[(glyph_class, appearance)]
                    # just because we think we're dealing with an unidentified object does not necessarily make it so (plastic AoY)
                    # so we treat our appearance match as if it were a name and try to grab glyphs with that name
                    possible_glyphs += global_identity_map.glyph_by_name.get((glyph_class, appearance), [])
                    if len(possible_glyphs) == 1:
                        glyph_numeral = possible_glyphs[0].numeral

                    break

            # if we didn't find a match after trying to treat it like an unidentified glyph, we should assume it's identified
            # things like 'scroll of fire' -> 'fire'
            if not glyph_class:
                for klass, pattern in cls.identified_class_patterns.items():
                    class_pattern_match = re.search(pattern, description)
                    if class_pattern_match:
                        name = class_pattern_match[1]
                        glyph_numeral = global_identity_map.identity_by_name[(klass, name)].numeral
                        break

            # if we still haven't found the class, then we are screwed
            # can happen when we are blind and so on, so at some point we need to fail gracefully
            if not glyph_class:
                if environment.env.debug: pdb.set_trace()
                return None

        # now we are in a state where we know glyph_class and we might know glyph_numeral
        # if we know glyph_numeral, we want to instantiate a real Item
        # if we don't know glyph_numeral, we want to make an AmbiguousItem

        if glyph_numeral:
            item_class = cls.item_class_by_glyph_class.get(glyph_class, Item)
            print(item_class)
            return item_class(global_identity_map, glyph_numeral, quantity, BUC, equipped_status, condition, enhancement, inventory_letter)
        else:
            return AmbiguousItem(global_identity_map, glyph_class, possible_glyphs, appearance, quantity, BUC, equipped_status, condition, enhancement)

class Slot():
    blockers = []
    def __init__(self, name):
        self.name = name
        self.occupied = None
        self.occupant_letter = None

    def add_occupant(self, occupant_letter):
        self.occupied=True
        self.occupant_letter=occupant_letter

    def __repr__(self):
        prefix = "{}:".format(self.name)
        if self.occupant_letter is None:
            return prefix + 'nothing'
        return prefix + chr(self.occupant_letter)

class SuitSlot(Slot):
    blockers = ['cloak']

class ShirtSlot(Slot):
    blockers = ['suit', 'cloak']

class SlotCluster():
    def __init__(self, inventory):
        slots = {slot_name:slot_type(slot_name) for slot_name, slot_type in self.__class__.slot_type_mapping.items()}

        for oclass in self.__class__.involved_classes:
            class_contents = inventory.get_oclass(oclass)

            for item in class_contents:
                if item.equipped_status is not None:
                    occ_slot = item.equipped_status.slot
                    #print(occ_slot)
                    #print(occ_slot is not None)
                    if occ_slot is not None:
                        slots[occ_slot].add_occupant(item.inventory_letter)

        #pdb.set_trace()
        self.slots = slots

    def blocked_by_letters(self, slot, inventory):
        blockers = [self.slots[block_name].occupant_letter for block_name in self.slots[slot.name].blockers if self.slots[block_name].occupied]

        if slot.occupied:
            blockers.append(self.slots[slot.name].occupant_letter)
        
        return blockers

class ArmamentSlots(SlotCluster):
    slot_type_mapping = OrderedDict({
        "shirt": ShirtSlot,
        "suit": SuitSlot,
        "cloak": Slot,
        "off-hand": Slot,
        "hand": Slot,
        "gloves": Slot,
        "helmet": Slot,
        "boots": Slot,
    })
    involved_classes = [Armor] # until I add weapons TK TK
    #involved_classes = ['ARMOR_CLASS', 'WEAPON_CLASS'] # while anything can be in your hands, only these objects will weld and hence only they are meaningful

class PlayerInventory():
    slot_cluster_mapping = {
        'armaments': ArmamentSlots,
    }

    def __init__(self, run_state, observation):
        self.items_by_letter = {}
        self.items_by_class = {}

        self.slot_groups_by_name = {}

        self.inv_strs = observation['inv_strs'].copy()
        self.inv_letters = observation['inv_letters']
        self.inv_oclasses = observation['inv_oclasses']
        self.inv_glyphs = observation['inv_glyphs']

        self.observation = observation
        self.global_identity_map = run_state.global_identity_map

    def have_item_oclass(self, object_class):
        object_class_num = object_class.glyph_class.class_number
        return object_class_num in self.inv_oclasses

    def get_oclass(self, object_class):
        object_class_num = object_class.glyph_class.class_number

        try:
            items = self.items_by_class[object_class]
            return items
        except KeyError:
            class_contents = []
            oclass_idx = np.where(self.inv_oclasses == object_class_num)[0]
            for numeral, letter, raw_string in zip(self.inv_glyphs[oclass_idx], self.inv_letters[oclass_idx], self.inv_strs[oclass_idx]):
                item_str = ItemParser.decode_inventory_item(raw_string)

                if item_str:
                    item = ItemParser.parse_inventory_item(self.global_identity_map, item_str, glyph_numeral=numeral, inventory_letter=letter)
                    self.items_by_letter[letter] = item
                    class_contents.append(item)

            self.items_by_class[object_class] = class_contents
            return class_contents

    def get_slots(self, slot_cluster_name):
        try:
            return self.slot_groups_by_name[slot_cluster_name] # if we've already baked the slots
        except KeyError:
            slots = self.__class__.slot_cluster_mapping[slot_cluster_name](self)
            self.slot_groups_by_name[slot_cluster_name] = slots
            return slots