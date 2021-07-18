import functools
import re
from typing import NamedTuple
import pdb
import glyphs as gd
import environment

class Item():
    def __init__(self, description, quantity, BUC, equipped_status, condition, glyph_numeral=None):
        self.description = description
        self.quantity = quantity
        self.BUC = BUC
        self.equipped_status = equipped_status
        self.condition = condition

        self.glyph_numeral = glyph_numeral # not always present, example: seeing item in a stack

        try:
            if self.glyph_numeral is not None:
                self.identity = gd.OBJECT_IDENTITIES_BY_GLYPH[glyph_numeral]
            else:
                self.identity = gd.OBJECT_IDENTITIES_BY_NAME[self.description]
                self.glyph_numeral = self.identity.numeral
        except KeyError:
            try:
                self.identity = gd.UNSHUFFLED_OBJECT_IDENTITIES_BY_APPEARNCE[self.description]
            except KeyError:
                self.identity = None

class ItemParser():
    item_pattern = re.compile("^(a|an|[0-9]+) (blessed|uncursed|cursed)? ?( ?(very|thoroughly)? ?(burnt|rusty|corroded|rustproof|rotted|poisoned))* ?((\+|\-)[0-9]+)? ?([a-zA-Z9 -]+[a-zA-Z9]) ?(\(.+\))?$")

    @staticmethod
    def decode_inventory_item(raw_item_repr):
        decoded = bytes(raw_item_repr).decode('ascii').rstrip('\x00')
        return decoded

    @classmethod
    @functools.lru_cache(maxsize=156)
    def parse_inventory_item(cls, string):
        match = re.match(cls.item_pattern, string)
        if match:
            quantity_match = match[1]
            BUC = match[2]
            condition_intensifier = match[3]
            condition = match[4]
            enhancement = match[6]
            description = match[8]
            equipped_status = match[9]

            if quantity_match == "a" or quantity_match == "an":
                quantity = 1
            else:
                quantity = int(match[1])

            if condition_intensifier is not None and condition is not None:
                condition = condition_intensifier + ' ' + condition

        else:
            if environment.env.debug: pdb.set_trace()
            return None

        item_init_args = (description, quantity, BUC, equipped_status, condition)
        return item_init_args # should we actually be making and caching the object??

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

    def __init__(self, observation):
        contents = []
        for raw, glyph_num in zip(observation['inv_strs'], observation['inv_glyphs']):
            item_str = ItemParser.decode_inventory_item(raw)

            if item_str:
                item_args = ItemParser.parse_inventory_item(item_str)
                if item_args is not None:
                    item = Item(*item_args, glyph_numeral=glyph_num)

                contents.append(item)

        self.contents = contents
        #self.armor_worn = False


