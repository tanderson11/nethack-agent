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
    def __init__(self, identity, instance_attributes, inventory_letter=None, seen_as=None):
        # copy fields
        self.identity = identity
        self.quantity = instance_attributes.quantity
        self.enhancement = instance_attributes.enhancement
        self.BUC = instance_attributes.BUC
        self.condition = instance_attributes.condition

        if instance_attributes.parenthetical_status_str is not None:
            self.equipped_status = EquippedStatus(self, instance_attributes.parenthetical_status_str)
            if self.equipped_status is None:
                self.parenthetical_status = instance_attributes.parenthetical_status_str
        else:
            self.parenthetical_status = None
            self.equipped_status = None
        # optional arguments
        self.inventory_letter = inventory_letter

        self._seen_as = seen_as

    def process_message(self, *args):
        self.identity.process_message(*args)

    def desirability(self, character):
        return None

class Item(ItemLike):
    pass

class Armor(Item):
    glyph_class = gd.ArmorGlyph

    def instance_desirability_to_wear(self, character):
        body_armor_penalty = 0
        if character.body_armor_penalty() and self.identity.slot == 'suit':
            body_armor_penalty = -20
            return -20 # to enforce for the moment that we never wear body armor as a monk

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

    def melee_damage(self, monster):
        weapon_damage = self.identity.avg_melee_damage(monster)
        weapon_damage += 0 or self.enhancement

        # TK know about silver damage etc
        return weapon_damage

class Tool(Item):
    glyph_class = gd.ToolGlyph

class Gem(Item):
    glyph_class = gd.GemGlyph

class Rock(Item):
    glyph_class = gd.RockGlyph

class UnimplementedItemClassException(Exception):
    pass

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

class ItemParser():
    item_pattern = re.compile("^(the|a|an|[0-9]+) (blessed|uncursed|cursed)? ?( ?(very|thoroughly)? ?(burnt|rusty|corroded|rustproof|rotted|poisoned|fireproof))* ?((\+|\-)[0-9]+)? ?([a-zA-Z9 -]+[a-zA-Z9]) ?(\(.+\))?$")
    
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
        gd.GemGlyph: re.compile('([a-zA-Z ]+) (?:gem|stone)s?')
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
        gd.ToolGlyph: Tool,
        gd.GemGlyph: Gem,
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
        'Iron balls': gd.BallGlyph,
    }

    category_by_glyph_class = {v:k for k,v in glyph_class_by_category.items() if isinstance(v, type)}
    category_by_glyph_class[gd.FoodGlyph] = 'Comestibles'
    category_by_glyph_class[gd.CorpseGlyph] = 'Comestibles'

    #glyph_class_by_item_class = {v:k for k,v in item_class_by_glyph_class.items()}

    @staticmethod
    def decode_inventory_item(raw_item_repr):
        decoded = bytes(raw_item_repr).decode('ascii').rstrip('\x00')
        return decoded

    @classmethod
    def extract_name_from_description_given_glyph_class(cls, global_identity_map, description, glyph_class):
        pattern = cls.defuzzing_identified_class_patterns.get(glyph_class, re.compile('([a-zA-Z -]+)'))
        match = re.search(pattern, description)
        if match:
            # we defuzz using the appropriate pattern
            defuzzed_name = match[1]

            identity_class = global_identity_map.identity_by_glyph_class[glyph_class]
            class_names    = identity_class.names()

            if defuzzed_name not in class_names.unique():
                japanese_names = identity_class.japanese_names()
                if defuzzed_name not in japanese_names.unique():
                    return None
                else:
                    return identity_class.japanese_name_to_english(defuzzed_name)
            else:
                return defuzzed_name

    @classmethod
    def extract_name_from_description_given_numeral(cls, global_identity_map, description, numeral):
        glyph_class = type(gd.GLYPH_NUMERAL_LOOKUP[numeral])
        return cls.extract_name_from_description_given_glyph_class(global_identity_map, description, glyph_class)

    class AppearanceMatch(NamedTuple):
        appearance: str
        possible_glyphs: list

    @classmethod
    def appearance_from_description_given_glyph_class(cls, global_identity_map, description, glyph_class):
        pattern = cls.defuzzing_unidentified_class_patterns.get(glyph_class, re.compile('([a-zA-Z -]+)'))
        match = re.search(pattern, description)

        possible_glyphs = []
        if match:
            defuzzed_appearance = match[1]

            identity_class = global_identity_map.identity_by_glyph_class[glyph_class]

            class_appearances = identity_class.appearances()

            if defuzzed_appearance not in class_appearances.unique():
                return None
            else:
                #import pdb; pdb.set_trace()
                possible_glyphs = class_appearances[class_appearances == defuzzed_appearance].index
                return cls.AppearanceMatch(defuzzed_appearance, possible_glyphs)

    @classmethod
    def make_item_with_glyph(cls, global_identity_map, item_glyph, item_string, inventory_letter=None):
        match_components = cls.parse_inventory_item_string(item_string)
        try:
            identity = global_identity_map.identity_by_numeral[item_glyph]
        except KeyError:
            print(f"UNIMPLEMENTED ITEM {item_glyph}")
            identity = None

        glyph = gd.GLYPH_NUMERAL_LOOKUP[item_glyph]
        glyph_class = type(glyph)

        if identity is not None and identity.name() is None:
            name = cls.extract_name_from_description_given_numeral(global_identity_map, match_components.description, item_glyph)
            if name is not None:
                global_identity_map.associate_identity_and_name(identity, name)

        item_class = cls.item_class_by_glyph_class.get(glyph_class, Item)
        return item_class(identity, match_components, inventory_letter=inventory_letter)

    @classmethod
    def make_item_with_string(cls, global_identity_map, item_str, category=None, inventory_letter=None):
        match_components = cls.parse_inventory_item_string(item_str)
        description = match_components.description

        # if we are given the category (Ex. pickup from large stack) we can narrow down class
        if category:
            possible_glyph_classes = cls.glyph_class_by_category[category]
            if type(possible_glyph_classes) != list:
                possible_glyph_classes = [possible_glyph_classes]
        # otherwise we'll have to comb through every class
        else:
            # these are the classes we've implemented with data, so they're the only ones
            # that we should check
            possible_glyph_classes = gd.GlobalIdentityMap.identity_by_glyph_class.keys()

        possible_glyphs = []
        identity = None
        for glyph_class in possible_glyph_classes:
            if glyph_class != gd.CorpseGlyph:
                appearance_match = cls.appearance_from_description_given_glyph_class(global_identity_map, description, glyph_class)

                if appearance_match is not None:
                    seen_as = appearance_match.appearance
                    possible_glyphs.extend(list(appearance_match.possible_glyphs))

                name = cls.extract_name_from_description_given_glyph_class(global_identity_map, description, glyph_class)
                #import pdb; pdb.set_trace()
                if name is not None:
                    seen_as = name
                    # add the possibilities found by name
                    # name-finding function should return None if this name doesn't belong to glyph_class
                    try:
                        glyph_for_name = global_identity_map.identity_by_name[(glyph_class, name)].idx
                        possible_glyphs.extend(glyph_for_name)
                    except KeyError:
                        # we've seen an identified item that we haven't entered into our state about discoveries
                        # we generate an identity object to pass to our item to capture this extra information
                        identity_class = gd.GlobalIdentityMap.identity_by_glyph_class[glyph_class]
                        identity = identity_class.identity_from_name(name)
                        break

                if len(possible_glyphs) > 0:
                    break # we can only ever match in one class by nethack logic, so break if any matches found
            
        # we add glyphs both when we match by name and when we match by appearance
        # so we want to remove duplicates
        possible_glyphs = set(possible_glyphs)

        if len(possible_glyphs) != 0 or identity is not None:
            item_class = cls.item_class_by_glyph_class.get(glyph_class, Item)
            if identity is not None:
                pass
            else:
                if len(possible_glyphs) == 1:
                    glyph_numeral = next(iter(possible_glyphs)) # since it's a set
                    identity = global_identity_map.identity_by_numeral[glyph_numeral]
                else:
                    identity_class = gd.GlobalIdentityMap.identity_by_glyph_class[glyph_class]
                    identity = identity_class(possible_glyphs)

            return item_class(identity, match_components, inventory_letter=inventory_letter, seen_as=seen_as)
        elif len(possible_glyphs) == 0:
            if environment.env.debug: print("WARNING: Failed to find possible glyphs for " + description)
            return None

    class MatchComponents(NamedTuple):
        description: str
        quantity: int
        enhancement: int
        parenthetical_status_str: str
        BUC: str
        condition: str

    @classmethod
    def parse_inventory_item_string(cls, item_string):
        match = re.match(cls.item_pattern, item_string)

        if match:
            quantity_match = match[1]
            if quantity_match == "a" or quantity_match == "an" or quantity_match == "the":
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
            
            equipped_status = match[9]

            return cls.MatchComponents(description, quantity, enhancement, equipped_status, BUC, condition)

        else:
            raise Exception("couldn't match item string")

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
                if item is None:
                    if environment.env.debug: import pdb; pdb.set_trace()
                else:
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
                        item = ItemParser.make_item_with_string(self.global_identity_map, item_str, inventory_letter=letter)
                    else:
                        item = ItemParser.make_item_with_glyph(self.global_identity_map, numeral, item_str, inventory_letter=letter)
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

    def wielded_weapon(self):
        armaments = self.get_slots('armaments')
        hand_occupant = armaments.slots['hand'].occupant

        if not hand_occupant:
            return None

        if hand_occupant.equipped_status.status == 'wielded':
            return hand_occupant
        else:
            if environment.env.debug: pdb.set_trace()

    def to_hit_modifiers(self, character, monster):
        weapon = self.wielded_weapon()
        if weapon:
            to_hit = 0 or weapon.enhancement
        else:
            to_hit = 0
        # TK rings of increased accuracy
        # TK monks and body armor
        # TK monks and no weapon
        # TK blessed against undead etc
        # TK weapon skills adjustments

        return to_hit

