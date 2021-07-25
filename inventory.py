import functools
import re
from typing import NamedTuple
from collections import OrderedDict
import pdb
import glyphs as gd
import environment
import numpy as np

from utilities import ARS

class Item():
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


    #identity, appearance, quantity, BUC, parenthetical_status, condition, enhancement, glyph_numeral=glyph_numeral, inventory_letter=inventory_letter
    def __init__(self, identity, appearance, quantity, BUC, parenthetical_status, condition, enhancement, inventory_letter=None):
        self.identity = identity
        self.appearance = appearance
        self.quantity = quantity
        self.BUC = BUC

        self.parenthetical_status = parenthetical_status
        self.condition = condition
        self.enhancement = enhancement

        self.inventory_letter = inventory_letter

        self.equipped_status = self.__class__.EquippedStatus(self, parenthetical_status)
        if self.equipped_status.slot is None and self.equipped_status.status is None:
            self.equipped_status = None

    def process_message(self, *args):
        self.identity.process_message(*args)

    def desirability(self, character):
        return None

class Armor(Item):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #self.occupies_slot = self.identity.find_values('SLOT')

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
    pass

class ItemParser():
    item_pattern = re.compile("^(a|an|[0-9]+) (blessed|uncursed|cursed)? ?( ?(very|thoroughly)? ?(burnt|rusty|corroded|rustproof|rotted|poisoned))* ?((\+|\-)[0-9]+)? ?([a-zA-Z9 -]+[a-zA-Z9]) ?(\(.+\))?$")
    unidentified_class_patterns = {
        'ARMOR_CLASS': re.compile('pair of ([a-zA-Z ]+)$'),
        'WAND_CLASS': re.compile('([a-zA-Z])+ wand$'),
        'RING_CLASS': re.compile('([a-zA-Z]+) ring$'),
        'AMULET_CLASS': re.compile('([a-zA-Z]+) amulet$'),
        'POTION_CLASS': re.compile('([a-zA-Z]+) potions?$'),
        'SCROLL_CLASS': re.compile('scroll?s labeled ([a-zA-Z0-9 ]+)$'), #NR9, multi word scrolls
        'SPBOOK_CLASS': re.compile('([a-zA-Z])+ spellbook$'),
    }
    identified_class_patterns = {
        'WAND_CLASS': re.compile('wand of ([a-zA-Z ]+)$'),
        'ARMOR_CLASS': re.compile('pair of ([a-zA-Z ]+)$'),
        'RING_CLASS': re.compile('([a-zA-Z]+) ring$'),
        'AMULET_CLASS': re.compile('amulet of ([a-zA-Z ]+)$'),
        'POTION_CLASS': re.compile('potions? of ([a-zA-Z ]+)$'),
        'SCROLL_CLASS': re.compile('scroll?s of ([a-zA-Z0-9 ]+)$'), #NR9, multi word scrolls
        'SPBOOK_CLASS': re.compile('spellbook of ([a-zA-Z ]+)$'),
    }

    class_strings_to_classes = {
        'ARMOR_CLASS': Armor,
        'WAND_CLASS': Wand,
        'RING_CLASS': Item,
        'AMULET_CLASS': Item,
        'POTION_CLASS': Item,
        'SCROLL_CLASS': Item,
        'SPBOOK_CLASS': Item,
        'FOOD_CLASS': Item,
    }

    @classmethod
    def make_item_of_class(cls, object_class_name, appearance, quantity, BUC, parenthetical_status, condition, enhancement, glyph_numeral=None, inventory_letter=None):
        oclass = cls.class_strings_to_classes.get(object_class_name, Item)

        # this is the easy case, we pull the identity directly
        if glyph_numeral is not None:
            identity = gd.GLYPH_NUMERAL_LOOKUP[glyph_numeral].identity
            identity_objs = [identity] # possible distinct identity OBJECTS, each one can have an idx of possible real spoilers. this matters for classes like gems, where appearances aren't unique
        # this is the hard case, we look up the appearance in the relevant object class
        else:
            class_data = gd.OBJECT_METADATA.OBJECT_DATA_BY_CLASS[object_class_name]
            matches = np.where(class_data['APPEARANCE'] == appearance)[0]

            # if appearance uniquely determines the NUMERAL (note: it still won't have a unique identity if it's shuffled)
            if len(matches) == 1:
                identity = gd.GLYPH_NUMERAL_LOOKUP[matches[0]].identity
                identity_objs = [identity]
                glyph_numeral = identity.numeral
            # otherwise
            elif len(matches) > 1:
                identity = None
                identity_objs = [gd.GLYPH_NUMERAL_LOOKUP[x].identity for x in matches]
            else:
                raise Exception("no matches for appearance in class")

        if identity is None:
            if environment.env.debug: pdb.set_trace() # are we hallucinating?

        item = oclass(identity, appearance, quantity, BUC, parenthetical_status, condition, enhancement, inventory_letter=inventory_letter)
        return item

    @staticmethod
    def decode_inventory_item(raw_item_repr):
        decoded = bytes(raw_item_repr).decode('ascii').rstrip('\x00')
        return decoded

    @classmethod
    @functools.lru_cache(maxsize=128)
    def parse_inventory_item(cls, string, glyph_numeral=None, passed_object_class=None, inventory_letter=None):
        match = re.match(cls.item_pattern, string)

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
            object_class = None

            # scrolls, wands, etc. have wonky descriptions vs appearances. e.g. scroll labeled FOO versus FOO
            for klass, pattern in cls.unidentified_class_patterns.items():
                class_pattern_match = re.search(pattern, description)
                if class_pattern_match:
                    appearance = class_pattern_match[1]
                    object_class = klass
                    print('UNIDENTIFIED', klass)
                    #pdb.set_trace()
                    break

            if appearance is None and object_class is None:
                # try to match against identified patterns like scrolls of identify
                for klass, pattern in cls.identified_class_patterns.items():
                    class_pattern_match = re.search(pattern, description)
                    if class_pattern_match:
                        appearance = class_pattern_match[1]
                        object_class = klass
                        break

                    if appearance is None and object_class is None:
                        appearance = description
                        try:
                            object_class = gd.OBJECT_METADATA.OBJECT_CLASS_BY_APPEARANCE[appearance]
                        except KeyError:
                            try:
                                object_class = gd.OBJECT_METADATA.OBJECT_CLASS_BY_NAME[appearance]
                            except KeyError:
                                if environment.env.debug: pdb.set_trace()

            equipped_status = match[9]

            if passed_object_class is not None and passed_object_class != object_class:
                raise Exception("Passed object class and found object class don't match")

        else:
            if environment.env.debug: pdb.set_trace()
            return None

        item = cls.make_item_of_class(object_class, appearance, quantity, BUC, equipped_status, condition, enhancement, glyph_numeral=glyph_numeral, inventory_letter=inventory_letter)
        return item # if caching, garbage collection will keep this object around I think


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
    involved_classes = ['ARMOR_CLASS'] # until I add weapons TK TK
    #involved_classes = ['ARMOR_CLASS', 'WEAPON_CLASS'] # while anything can be in your hands, only these objects will weld and hence only they are meaningful

class PlayerInventory():
    slot_cluster_mapping = {
        'armaments': ArmamentSlots,
    }

    def __init__(self, observation):
        self.items_by_letter = {}
        self.items_by_class = {}

        self.slot_groups_by_name = {}

        self.inv_strs = observation['inv_strs'].copy()
        self.inv_letters = observation['inv_letters']
        self.inv_oclasses = observation['inv_oclasses']
        self.inv_glyphs = observation['inv_glyphs']

        self.observation = observation

    def have_item_oclass(self, object_class_name):
        object_class_num = gd.ObjectGlyph.OBJECT_CLASSES.index(object_class_name) # TK make better with a mapping
        return object_class_num in self.inv_oclasses

    def get_oclass(self, object_class_name):
        object_class_num = gd.ObjectGlyph.OBJECT_CLASSES.index(object_class_name) # TK make better with a mapping

        try:
            items = self.items_by_class[object_class_name]
            return items
        except KeyError:
            class_contents = []
            oclass_idx = np.where(self.inv_oclasses == object_class_num)[0]
            for numeral, letter, raw_string in zip(self.inv_glyphs[oclass_idx], self.inv_letters[oclass_idx], self.inv_strs[oclass_idx]):
                item_str = ItemParser.decode_inventory_item(raw_string)

                if item_str:
                    item = ItemParser.parse_inventory_item(item_str, glyph_numeral=numeral, passed_object_class=object_class_name, inventory_letter=letter)
                    self.items_by_letter[letter] = item
                    class_contents.append(item)

            self.items_by_class[object_class_name] = class_contents
            #pdb.set_trace()
            return class_contents
        #self.armor_worn = False

    def get_slots(self, slot_cluster_name):
        try:
            return self.slot_groups_by_name[slot_cluster_name] # if we've already baked the slots
        except KeyError:
            slots = self.__class__.slot_cluster_mapping[slot_cluster_name](self)
            self.slot_groups_by_name[slot_cluster_name] = slots
            return slots