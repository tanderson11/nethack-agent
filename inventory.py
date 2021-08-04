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
                    self.slot = item.identity.slot

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


   
    def __init__(self, quantity, BUC, parenthetical_status, condition, enhancement, description=None):
        self.quantity = quantity
        self.BUC = BUC

        self._description = description

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
    def __init__(self, global_identity_map, glyph_numeral, quantity, BUC, parenthetical_status, condition, enhancement, inventory_letter=None, description=None):
        self.inventory_letter = inventory_letter
        self.glyph = gd.GLYPH_NUMERAL_LOOKUP[glyph_numeral]

        try:
            self.identity = global_identity_map.identity_by_numeral[glyph_numeral]
        except KeyError:
            print("No identity found for {}".format(glyph_numeral))

        super().__init__(quantity, BUC, parenthetical_status, condition, enhancement, description)

class Armor(Item):
    glyph_class = gd.ArmorGlyph

    def instance_desirability_to_wear(self, character):
        body_armor_penalty = 0
        if character.body_armor_penalty() and self.identity.slot == 'suit':
            body_armor_penalty = -25

        if self.enhancement is None:
            best_case_enhancement = 5
        else:
            best_case_enhancement = self.enhancement

        if self.BUC == 'blessed':
            buc_adjustment = 0.5
            raw_value = self.identity.converted_wear_value().max()
        elif self.BUC == 'uncursed' or (character.base_class == 'Priest' and self.BUC == None):
            buc_adjustment = 0
            raw_value = self.identity.converted_wear_value().max()
        # cursed or might be cursed
        else:
            buc_adjustment = -2 if self.BUC == 'cursed' else -0.5
            # assume we're the worst item we could be if we might be cursed -- cause you'll be stuck with us forever!
            raw_value = self.identity.converted_wear_value().min()

        desirability = raw_value + best_case_enhancement + body_armor_penalty
        #pdb.set_trace()
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

    def __init__(self, global_identity_map, glyph_class, possible_glyphs, appearance, quantity, BUC, parenthetical_status, condition, enhancement, description=None):
        self.identity = None
        self.glyph_numeral = None
        self.possible_glyphs = possible_glyphs
        super().__init__(quantity, BUC, parenthetical_status, condition, enhancement, description)

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

    defuzzing_unidentified_class_patterns = {
        gd.ArmorGlyph: re.compile('(?:pair of )?([a-zA-Z -]+)$'),
        gd.WandGlyph: re.compile('([a-zA-Z ]+) wand$'),
        gd.RingGlyph: re.compile('([a-zA-Z ]+) ring$'),
        gd.AmuletGlyph: re.compile('([a-zA-Z ]+) amulet$'),
        gd.PotionGlyph: re.compile('([a-zA-Z -]+) potions?$'),
        gd.ScrollGlyph: re.compile('scrolls? labeled ([a-zA-Z0-9 ]+)$'), #NR9, multi word scrolls. TK unlabeled scroll(s)
        gd.SpellbookGlyph: re.compile('([a-zA-Z ]+) spellbook$'),
    }
    defuzzing_identified_class_patterns = {
        gd.WandGlyph: re.compile('wand of ([a-zA-Z ]+)$'),
        gd.ArmorGlyph: re.compile('(?:pair of )?([a-zA-Z -]+)$'),
        gd.RingGlyph: re.compile('ring of ([a-zA-Z ]+)$'),
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

    glyph_class_by_category = {
        'Weapons': gd.WeaponGlyph,
        'Armor': gd.ArmorGlyph,
        'Rings': gd.RingGlyph,
        'Amulets': gd.AmuletGlyph,
        'Tools': gd.ToolGlyph,
        'Comestibles': [gd.FoodGlyph, gd.CorpseGlyph],
        'Potions': gd.PotionGlyph,
        'Scrolls': gd.ScrollGlyph,
        'Spellbooks': gd.SpellbookGlyph,
        'Wands': gd.WandGlyph,
        'Coins': gd.CoinGlyph,
        'Gems/Stones': gd.GemGlyph,
        'Boulders/Statues': gd.RockGlyph,
    }

    #glyph_class_by_item_class = {v:k for k,v in item_class_by_glyph_class.items()}

    @staticmethod
    def decode_inventory_item(raw_item_repr):
        decoded = bytes(raw_item_repr).decode('ascii').rstrip('\x00')
        return decoded

    @classmethod
    def match_name_from_class(cls, global_identity_map, glyph_class, description, numeral=None):
        possible_glyphs = []
        defuzzed_name = None # passed only if we identify the object by name
        key_error = False
        id_pattern = cls.defuzzing_identified_class_patterns.get(glyph_class, re.compile('([a-zA-Z -]+)'))
        id_class_pattern_match = re.search(id_pattern, description)

        if id_class_pattern_match:
            defuzzed_name = id_class_pattern_match[1]

            # we look to see if the name is in the class
            try:
                # should never have more than one match for name
                possible_glyphs = [global_identity_map.identity_by_name[(glyph_class, defuzzed_name)].glyph]
            except KeyError:
                # we couldn't find the name in the identities table, suggesting it doesn't belong to this class, unless ...
                # we're currently looking at a Japanese name
                key_error = True
                try:
                    possible_glyphs = [global_identity_map.identity_by_japanese_name[(glyph_class, defuzzed_name)].glyph]
                    key_error = False
                except KeyError:
                    pass

        if key_error and numeral:
            global_identity_map.try_name_correspondence(defuzzed_name, glyph_class, numeral)
            possible_glyphs += [global_identity_map.identity_by_name[(glyph_class, defuzzed_name)].glyph]
            pass

        #if len(possible_glyphs) == 0 and environment.env.debug: pdb.set_trace()
        return defuzzed_name, possible_glyphs

    @classmethod
    def attempt_to_match_to_glyph_class(cls, global_identity_map, glyph_class, description):
        defuzzed_appearance = None
        possible_glyphs = []

        unid_pattern = cls.defuzzing_unidentified_class_patterns.get(glyph_class, re.compile('([a-zA-Z -]+)'))
        unid_class_pattern_match = re.search(unid_pattern, description)

        if unid_class_pattern_match:
            defuzzed_appearance = unid_class_pattern_match[1]

            # we look to see if the appearance is in the class
            try:
                results = global_identity_map.glyph_by_appearance[(glyph_class, defuzzed_appearance)]
                try: 
                    possible_glyphs += results
                except TypeError:
                    possible_glyphs += [results]
                #pdb.set_trace()
                pass
            except KeyError:
                defuzzed_appearance = None

        # try next to match by name (AoY and plastic AoY share name / appearance respectively)
        defuzzed_name, possible_glyphs_by_name = cls.match_name_from_class(global_identity_map, glyph_class, description)
        assert defuzzed_name is None or defuzzed_appearance is None or defuzzed_name == defuzzed_appearance
        possible_glyphs += possible_glyphs_by_name

        #if len(possible_glyphs) == 0 and environment.env.debug: pdb.set_trace()
        return defuzzed_appearance, defuzzed_name, set(possible_glyphs) # set because sometimes both the name and unidentified appearance are the same, and we'll double match

    @classmethod
    def parse_inventory_item(cls, global_identity_map ,string, glyph_numeral=None, inventory_letter=None, category=None):
        match = re.match(cls.item_pattern, string)
        glyph_class = None
        defuzzed_name = None

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
            try:
                identity = global_identity_map.identity_by_numeral[glyph_numeral]
                if identity and identity.is_shuffled:
                    _, _, = cls.match_name_from_class(global_identity_map, glyph_class, description, numeral=glyph_numeral)
                    #print(defuzzed_name)
            except KeyError:
                print("Couldn't find identity for " + str(glyph_numeral))
        # if we don't have the numeral, we should still always be able to pull the glyph_class from the appearance somehow
        else:
            # for starters, if we are given the category, as we are in big stacks of items, we can use that to help
            if category:
                possible_glyph_classes = cls.glyph_class_by_category[category]
                if type(possible_glyph_classes) != list:
                    possible_glyph_classes = [possible_glyph_classes]

                for klass in possible_glyph_classes:
                    appearance, defuzzed_name, possible_glyphs = cls.attempt_to_match_to_glyph_class(global_identity_map, klass, description)

                    # the description resides in the glyph class
                    if len(possible_glyphs) > 0:
                        glyph_class = klass
                        break
                
                if len(possible_glyphs) == 0:
                    #if environment.env.debug: pdb.set_trace()
                    if environment.env.debug: print("WARNING: Failed to find possible glyphs for " + description)
                    #if environment.env.debug: pdb.set_trace()
                    return None

            # if we don't have the category, we have nothing better to do than try every class's defuzzing approach
            else:
                for klass in gd.ObjectSpoilers.OBJECT_GLYPH_CLASSES:
                    appearance, defuzzed_name, possible_glyphs = cls.attempt_to_match_to_glyph_class(global_identity_map, klass, description)

                    if len(possible_glyphs) > 0:
                        glyph_class = klass
                        break

                if len(possible_glyphs) == 0:
                    #if environment.env.debug: pdb.set_trace()
                    if environment.env.debug: print("WARNING: Failed to find possible glyphs for " + description)
                    #if environment.environment.debug: pdb.set_trace()
                    return None

        if not glyph_numeral and len(possible_glyphs) == 1:
            glyph_numeral = next(iter(possible_glyphs)).numeral # because possible_glyphs is a set


        # now we are in a state where we know glyph_class and we might know glyph_numeral
        # if we know glyph_numeral, we want to instantiate a real Item
        # if we don't know glyph_numeral, we want to make an AmbiguousItem
        if glyph_numeral:
            item_class = cls.item_class_by_glyph_class.get(glyph_class, Item)

            return item_class(global_identity_map, glyph_numeral, quantity, BUC, equipped_status, condition, enhancement, inventory_letter, description=description)
        else:
            print("Ambiguous Item found: " + description)
            #if environment.env.debug: pdb.set_trace()
            return AmbiguousItem(global_identity_map, glyph_class, possible_glyphs, appearance, quantity, BUC, equipped_status, condition, enhancement, description=description)

class Slot():
    blockers = []
    def __init__(self, name):
        self.name = name
        self.occupied = None
        self.occupant = None

    def add_occupant(self, occupant):
        self.occupied=True
        self.occupant=occupant

    def __repr__(self):
        prefix = "{}:".format(self.name)
        if self.occupant is None:
            return prefix + 'nothing'
        return prefix + chr(self.occupant)

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
                        slots[occ_slot].add_occupant(item)

        #pdb.set_trace()
        self.slots = slots

    def blocked_by_letters(self, slot, inventory):
        blockers = [self.slots[block_name].occupant for block_name in self.slots[slot.name].blockers if self.slots[block_name].occupied]

        if slot.occupied:
            blockers.append(self.slots[slot.name].occupant)
        
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

    def __init__(self, run_state, observation, am_hallu):
        self.am_hallu = am_hallu

        self.items_by_letter = {}
        self.items_by_class = {}

        self.slot_groups_by_name = {}

        self.inv_strs = observation['inv_strs'].copy()
        self.inv_letters = observation['inv_letters']
        self.inv_oclasses = observation['inv_oclasses']
        self.inv_glyphs = observation['inv_glyphs'].copy()

        self.observation = observation
        self.global_identity_map = run_state.global_identity_map

    def wants_glyph(self, character, glyph):
        pass

    @functools.cached_property
    def armaments(self):
        return self.get_slots('armaments')

    def wants_item(self, character, item):
        pass

    def proposed_attire_changes(self, character):
        armor = self.get_oclass(Armor)

        unequipped_by_slot = {}
        for item in armor:
            if item.equipped_status is None:
                slot = item.identity.slot
                try:
                    unequipped_by_slot[slot].append(item)
                except KeyError:
                    unequipped_by_slot[slot] = [item]

        if len(unequipped_by_slot.keys()) == 0:
            return [], []


        proposed_items = []
        proposal_blockers = []
        for slot in self.armaments.slot_type_mapping.keys(): # ordered dict by difficulty to access
            unequipped_in_slot = unequipped_by_slot.get(slot, [])

            if len(unequipped_in_slot) > 0:
                most_desirable = None
                max_desirability = None
                for item in unequipped_in_slot:
                    desirability = item.instance_desirability_to_wear(character)
                    if max_desirability is None or desirability > max_desirability:
                        max_desirability = desirability
                        most_desirable = item

                current_occupant = self.armaments.slots[slot].occupant
                if current_occupant is not None:
                    current_desirability = current_occupant.instance_desirability_to_wear(character)
                else:
                    current_occupant = None
                    current_desirability = 0

                if max_desirability > current_desirability:
                    slot = self.armaments.slots[slot]
                    blockers = self.armaments.blocked_by_letters(slot, self)

                    proposed_items.append(most_desirable)
                    proposal_blockers.append(blockers)

        return proposed_items, proposal_blockers


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
                    # if we're hallucinating, the glyph_numerals are garbage
                    if self.am_hallu:
                        item = ItemParser.parse_inventory_item(self.global_identity_map, item_str, glyph_numeral=None, inventory_letter=letter)
                    else:
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