import functools
import re
from typing import NamedTuple
import pdb
import glyphs as gd
import environment
import numpy as np

from utilities import ARS

class Item():
    def __init__(self, object_class, appearance, quantity, BUC, equipped_status, condition, glyph_numeral=None):
        self.object_class = object_class
        self.quantity = quantity
        self.BUC = BUC
        self.equipped_status = equipped_status
        self.condition = condition

        self.appearance = appearance
        self.glyph_numeral = glyph_numeral # not always present. example: seeing item in a stack

        #pdb.set_trace()

        # this is the easy case, we pull the identity directly
        if self.glyph_numeral is not None:
            self.identity_obj = gd.GLYPH_NUMERAL_LOOKUP[self.glyph_numeral].identity
            self.identity_objs = [self.identity_obj] # possible distinct identity OBJECTS, each one can have an idx of possible real spoilers. this matters for classes like gems, where appearances aren't unique
        # this is the hard case, we look up the appearance in the relevant object class
        else:
            class_data = gd.OBJECT_METADATA.OBJECT_DATA_BY_CLASS[self.object_class]
            matches = np.where(class_data['APPEARANCE'] == self.appearance)[0]

            # if appearance uniquely determines the NUMERAL (note: it still won't have a unique identity if it's shuffled)
            if len(matches) == 1:
                self.identity_obj = gd.GLYPH_NUMERAL_LOOKUP[matches[0]].identity
                self.identity_objs = [self.identity_obj]
                self.glyph_numeral = self.identity.numeral
            # otherwise
            elif len(matches) > 1:
                self.identity_obj = None
                self.identity_objs = [gd.GLYPH_NUMERAL_LOOKUP[x].identity for x in matches]
            else:
                raise Exception("no matches for appearance in class")

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

    @staticmethod
    def decode_inventory_item(raw_item_repr):
        decoded = bytes(raw_item_repr).decode('ascii').rstrip('\x00')
        return decoded

    @classmethod
    @functools.lru_cache(maxsize=128)
    def parse_inventory_item(cls, string, glyph_numeral=None, passed_object_class=None):
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

            description = match[8]
            
            appearance = None
            object_class = None

            #pdb.set_trace()
            # scrolls, wands, etc. have wonky descriptions vs appearances. e.g. scroll labeled FOO versus FOO
            for klass, pattern in cls.unidentified_class_patterns.items():
                class_pattern_match = re.search(pattern, description)
                if class_pattern_match:
                    appearance = class_pattern_match[1]
                    object_class = klass
                    print(klass)
                    pdb.set_trace()
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
                            object_class = gd.OBJECT_METADATA.OBJECT_CLASS_BY_NAME[appearance]

            equipped_status = match[9]

            if passed_object_class is not None and passed_object_class != object_class:
                raise Exception("Passed object class and found object class don't match")

        else:
            if environment.env.debug: pdb.set_trace()
            return None

        item = Item(object_class, appearance, quantity, BUC, equipped_status, condition, glyph_numeral=glyph_numeral)
        return item # if caching, garbage collection will keep this object around

class Inventory():
    class Slots(NamedTuple):
        gloves: bool
        shirt: bool
        suit: bool
        cloak: bool
        helmet: bool
        boots: bool
        amulet: bool
        left_ring: bool
        right_ring: bool
        hand: bool
        off_hand: bool

    def __init__(self, observation):
        self.items_by_letter = {}
        self.items_by_class = {}

        self.inv_strs = observation['inv_strs']
        self.inv_letters = observation['inv_letters']
        self.inv_oclasses = observation['inv_oclasses']
        self.inv_glyphs = observation['inv_glyphs']

    def get_oclass(self, object_class_name):
        object_class_num = gd.ObjectGlyph.OBJECT_CLASSES.index(object_class_name) # TK make better with mapping

        try:
            items = self.items_by_class[object_class_name]
            return items
        except KeyError:
            class_contents = []
            oclass_idx = np.where(self.inv_oclasses == object_class_num)[0]
            for numeral, letter, raw_string in zip(self.inv_glyphs[oclass_idx], self.inv_letters[oclass_idx], self.inv_strs[oclass_idx]):
                item_str = ItemParser.decode_inventory_item(raw_string)

                if item_str:
                    item = ItemParser.parse_inventory_item(item_str, glyph_numeral=numeral, passed_object_class=object_class_name)
                    self.items_by_letter[letter] = item
                    class_contents.append(item)

            self.items_by_class[object_class_name] = class_contents
            #pdb.set_trace()
            return class_contents
        #self.armor_worn = False


