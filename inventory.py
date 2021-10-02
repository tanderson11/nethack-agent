import functools
import re
from typing import NamedTuple
from collections import OrderedDict
import pdb
import glyphs as gd
import environment
import numpy as np
import constants
import pandas as pd

from utilities import ARS

class Item():
    try_to_price_id = True
    price_pattern = re.compile("\((for sale|unpaid), ([0-9]+) zorkmids?\)")
    class NameAction(NamedTuple):
        letter: str
        name: str

    def __init__(self, identity, instance_attributes, inventory_letter=None, seen_as=None):
        # copy fields
        self.identity = identity
        self.quantity = instance_attributes.quantity
        self.enhancement = instance_attributes.enhancement
        self.BUC = instance_attributes.BUC
        self.condition = instance_attributes.condition
        self.instance_name = instance_attributes.instance_name

        self.parenthetical_status = instance_attributes.parenthetical_status_str
        self.price = None
        if instance_attributes.parenthetical_status_str is not None:
            self.equipped_status = EquippedStatus(self, instance_attributes.parenthetical_status_str)
            self.shop_owned = self.parenthetical_status is not None and ("for sale" in self.parenthetical_status or "unpaid" in self.parenthetical_status)
            
            if self.shop_owned:
                price_match = re.search(self.price_pattern, self.parenthetical_status)
                if price_match is not None:
                    self.price = int(price_match[2])
                    self.unit_price = self.price / self.quantity
                else:
                    if environment.env.debug: import pdb; pdb.set_trace()
                    pass
        else:
            self.equipped_status = None
            self.shop_owned = False
            self.price = None

        # optional arguments
        self.inventory_letter = inventory_letter

        self._seen_as = seen_as

    def price_id_from_sell(self, character, sell_price):
        if self.identity is None:
            return None
        if self.identity.is_identified():
            return None
        if self.try_to_price_id == False:
            return None

        base_prices = character.find_base_price_from_sell(self, sell_price)
        self.identity.restrict_by_base_prices(base_prices, method='sell')

    def price_id(self, character):
        if self.identity is None:
            return None
        if self.identity.is_identified():
            return None
        if self.try_to_price_id == False:
            return None
        if self.price is None:
            return None
        #import pdb; pdb.set_trace()
        #old_idx_len = len(self.identity.idx)
        base_prices = character.find_base_price_from_listed(self, self.unit_price)
        self.identity.restrict_by_base_prices(base_prices)
        #new_idx_len = len(self.identity.idx)

        #print(f"Attempted to price ID. Old possibilites={old_idx_len}. New={new_idx_len}")

    def process_message(self, *args):
        name = self.identity.process_message(*args)
        if name is not None:
            return self.NameAction(self.inventory_letter, name)

    def can_afford(self, character):
        can_afford = True
        if self.shop_owned:
            if self.price is not None:
                can_afford = character.gold >= (self.price + character.inventory.get_current_balance())
            else:
                if environment.env.debug: import pdb; pdb.set_trace()
                can_afford = True

        return can_afford

    def find_equivalents(self, inventory):
        if self.__class__ == Item:
            import pdb; pdb.set_trace()
        same_items = inventory.get_items(self.__class__, name=self.identity.name())
        return same_items

    def better_than_equivalent(self, y, character):
        # in general, don't drop Y to pick up X if they have the same identity
        return False

    def less_cursed_than(self, y):
        return y.BUC == constants.BUC.cursed and self.BUC != constants.BUC.cursed

    def desirable(self, character, consider_funds=True):
        if self.identity is None:
            return False

        identity_desirability = self.identity.desirable_identity(character)
        if identity_desirability == constants.IdentityDesirability.desire_none:
            return False

        if consider_funds is True and not self.can_afford(character):
            return False

        if identity_desirability == constants.IdentityDesirability.desire_all:
            return True

        if identity_desirability == constants.IdentityDesirability.desire_all_uncursed:
            return self.BUC != constants.BUC.cursed

        if identity_desirability == constants.IdentityDesirability.desire_one:
            assert self.identity.is_identified(), "shouldn't desire exactly 1 copy of unidentified item"
            same_items = self.find_equivalents(character.inventory)
            equal_or_better_versions = [i for i in same_items if self != i and not self.better_than_equivalent(i, character)]

            if len(equal_or_better_versions) > 0:
                return False

            return True

        # now we are in the logic where we want exactly 1 (or exactly 7) of this item
        # these have to get handled differently in different object classes

        #return self.can_afford(character) and desirable_identity

class Amulet(Item):
    glyph_class = gd.AmuletGlyph

class Armor(Item):
    glyph_class = gd.ArmorGlyph

    def instance_desirability_to_wear(self, character):
        body_armor_penalty = 0
        if character.body_armor_penalty() and self.identity.slot == 'suit':
            body_armor_penalty = -20
            return -20 # to enforce for the moment that we never wear body armor as a monk

        if self.enhancement is None:
            if self.BUC == constants.BUC.cursed:
                return -10
            elif self.BUC is constants.BUC.unknown:
                best_case_enhancement = 0
            else:
                best_case_enhancement = 5
        else:
            best_case_enhancement = self.enhancement

        if self.BUC == constants.BUC.blessed:
            buc_adjustment = 0.5
            raw_value = self.identity.converted_wear_value().max()
        elif self.BUC == constants.BUC.uncursed:
            buc_adjustment = 0
            raw_value = self.identity.converted_wear_value().max()
        # cursed or might be cursed
        else:
            buc_adjustment = -0.5
            # assume we're the worst item we could be if we might be cursed -- cause you'll be stuck with us forever!
            raw_value = self.identity.converted_wear_value().min()

        desirability = raw_value + best_case_enhancement + body_armor_penalty + buc_adjustment
        return desirability

    def find_equivalents(self, inventory):
        if self.identity is None:
            return []
        same_slot = inventory.get_items(Armor, identity_selector=lambda i: i.slot == self.identity.slot)
        return same_slot

    def better_than_equivalent(self, y, character):
        return self.instance_desirability_to_wear(character) > y.instance_desirability_to_wear(character)

    def desirable(self, character, consider_funds=True):
        return super().desirable(character, consider_funds=consider_funds)

class Wand(Item):
    glyph_class = gd.WandGlyph
    charge_pattern = re.compile("\(([0-9]+):([0-9]+)\)")
    def __init__(self, identity, instance_attributes, inventory_letter=None, seen_as=None):
        super().__init__(identity, instance_attributes, inventory_letter=inventory_letter, seen_as=seen_as)
        self.charges = None

        if self.instance_name == "NO_CHARGE":
            self.charges = 0

        p_status = instance_attributes.parenthetical_status_str
        if p_status is not None:
            charge_match = re.match(self.charge_pattern, p_status)

            if charge_match:
                self.recharges = int(charge_match[1])
                self.charges = int(charge_match[2])

        if self.BUC == constants.BUC.unknown and self.charges is not None:
            self.BUC = constants.BUC.uncursed

    def desirable(self, character):
        des = super().desirable(character)

        # keep even a 0 charge wand of wishing
        if self.identity.name() == 'wishing':
            return True

        # keep even a 0 charge wand of death
        if self.identity.name() == 'death':
            return True

        if self.charges == 0:
            return False

        return des

class Food(Item):
    glyph_class = gd.FoodGlyph

    def better_than_equivalent(self, y, character):
        # prefer a not-cursed lizard corpse to a cursed lizard corpse
        return self.less_cursed_than(y)

class Coin(Item):
    glyph_class = gd.CoinGlyph

    def __init__(self, identity, instance_attributes, inventory_letter=None, seen_as=None):
        super().__init__(identity, instance_attributes, inventory_letter=inventory_letter, seen_as=seen_as)
        self.BUC = constants.BUC.uncursed

class Scroll(Item):
    glyph_class = gd.ScrollGlyph

    def safe_to_read(self, character):
        if self.BUC == constants.BUC.cursed or self.BUC == constants.BUC.unknown:
            return False

        if self.identity.could_be(self.identity.bad_scrolls_any_buc):
            return False

        if self.BUC != constants.BUC.blessed and self.identity.could_be(self.identity.bad_scrolls_worse_than_blessed):
            return False

        return True

class Potion(Item):
    glyph_class = gd.PotionGlyph

    def __init__(self, identity, instance_attributes, inventory_letter=None, seen_as=None):
        super().__init__(identity, instance_attributes, inventory_letter=inventory_letter, seen_as=seen_as)
        if identity.name() == 'water':
            if 'unholy' in instance_attributes.full_str:
                self.BUC = constants.BUC.cursed
            # carefully now: elif because holy is in 'unholy'
            elif 'holy' in instance_attributes.full_str:
                self.BUC = constants.BUC.blessed
                #import pdb; pdb.set_trace()

    healing_dice_by_BUC = {
        constants.BUC.uncursed: 6,
        constants.BUC.cursed: 4,
        constants.BUC.blessed: 8,
    }
    def expected_healing(self, character):
        name = self.identity.name()
        if name is None or 'healing' not in name:
            return 0

        if name == 'full healing':
            return character.max_hp

        BUC = self.BUC if self.BUC != constants.BUC.unknown else constants.BUC.uncursed
        n_dice = self.healing_dice_by_BUC[BUC]
        if name == 'healing':
            return n_dice * 4
            #return min(n_dice * 4, character.max_hp)

        if name == 'extra healing':
            return n_dice * 8
            #return min(n_dice * 8, character.max_hp)

class Weapon(Item):
    glyph_class = gd.WeaponGlyph

    def __init__(self, identity, instance_attributes, inventory_letter=None, seen_as=None):
        super().__init__(identity, instance_attributes, inventory_letter=inventory_letter, seen_as=seen_as)

        if self.BUC == constants.BUC.unknown and self.enhancement is not None:
            self.BUC = constants.BUC.uncursed

    def melee_damage(self, character, monster):
        weapon_damage = self.identity.avg_melee_damage(monster)
        enhancement = self.enhancement if self.enhancement is not None else 0
        #import pdb; pdb.set_trace()
        weapon_damage += 0 or enhancement

        # TK know about silver damage etc
        return weapon_damage

    def uses_relevant_skill(self, character):
        return character.relevant_skills.loc[self.identity.skill]

    def melee_desirability(self, character, desperate=False):
        if self.identity.is_ammunition or self.identity.is_ranged or self.identity.slot == 'quiver':
            return -1
        relevant_skill = self.uses_relevant_skill(character)

        if not desperate:
            if relevant_skill == False:
                return -1

            if self.BUC == constants.BUC.cursed or self.BUC == constants.BUC.unknown:
                return -1

        if desperate:
            # restricted weapons not worth it even if desperate
            skill_rank = constants.skill_abbrev_to_rank[character.class_skills.loc[self.identity.skill]]
            if pd.isna(constants.SkillRank(skill_rank)):
                return -1

        enhancement = self.enhancement
        if enhancement is None:
            enhancement = 0

        melee_damage = self.identity.avg_melee_damage(None)
        if isinstance(melee_damage, np.ndarray):
            melee_damage = melee_damage.max()

        return enhancement + melee_damage

    def find_equivalents(self, inventory):
        if self.identity is None:
            return []
        return inventory.get_items(Weapon)

    def better_than_equivalent(self, y, character):
        is_better = self.melee_desirability(character) > y.melee_desirability(character)
        if is_better and (self.equipped_status is None or self.equipped_status.status != 'wielded') and (y.equipped_status is not None and y.equipped_status.status == 'wielded'):
            #import pdb; pdb.set_trace()
            print(f"Found better weapon: {self.identity.name()}")
        return is_better

    def desirable(self, character, consider_funds=True):
        if self.enhancement is not None and (self.identity.is_ranged or self.identity.is_ammunition):
            return True

        des = super().desirable(character, consider_funds=consider_funds)
        return des

class BareHands(Weapon):
    def __init__(self):
        self.enhancement = 0
        self.inventory_letter = '-'
        self.BUC = constants.BUC.uncursed
        self.identity = None

    def which_skill(self, character):
        bare_hands_rank = constants.skill_abbrev_to_rank[character.class_skills.loc['bare hands']]
        martial_arts_rank = constants.skill_abbrev_to_rank[character.class_skills.loc['martial arts']]

        if bare_hands_rank > martial_arts_rank:
            bare_hands_skill = 'bare hands'
        elif martial_arts_rank > bare_hands_rank:
            bare_hands_skill = 'martial arts'

        return bare_hands_skill

    def uses_relevant_skill(self, character):
        return character.relevant_skills.loc[self.which_skill(character)]

    def melee_desirability(self, character, desperate=None):
        return self.melee_damage(character, None)

    def melee_damage(self, character, monster):
        bare_hands_skill = self.which_skill(character)
        # TK use the actual skill -> damage table
        if bare_hands_skill == 'bare hands':
            damage = 1.5
        else:
            damage = 2.5
        return damage

class Spellbook(Item):
    glyph_class = gd.SpellbookGlyph

class Tool(Item):
    glyph_class = gd.ToolGlyph
    charge_pattern = re.compile("\(([0-9]+):([0-9]+)\)")
    def __init__(self, identity, instance_attributes, inventory_letter=None, seen_as=None):
        super().__init__(identity, instance_attributes, inventory_letter=inventory_letter, seen_as=seen_as)
        self.charges = None

        if self.instance_name == "NO_CHARGE":
            self.charges = 0

        p_status = instance_attributes.parenthetical_status_str
        if p_status is not None:
            charge_match = re.match(self.charge_pattern, p_status)

            if charge_match:
                self.recharges = int(charge_match[1])
                self.charges = int(charge_match[2])

        if self.BUC == constants.BUC.unknown and self.charges is not None:
            self.BUC = constants.BUC.uncursed

    def uses_relevant_skill(self, character):
        return False

    def melee_damage(self, character, monster_spoiler=None):
        # TK know about pick-axe and unicorn horn
        return 1

    def melee_desirability(self, character):
        return self.melee_damage(character)

    def find_equivalents(self, inventory):
        if self.identity is None:
            return []
        if self.identity.name() == 'unicorn horn' or self.identity.name() == 'pick-axe':
            return super().find_equivalents(inventory)

        same_type = inventory.get_items(Tool, identity_selector=lambda i: i.type == self.identity.type)
        return same_type

    def better_than_equivalent(self, y, character):
        if self.identity is None:
            return False

        if self.identity.name() == 'unicorn horn' or self.identity.name() == 'pick-axe':
            return self.less_cursed_than(y)

        if self.identity.type == 'container':
            # TK decide which bag to keep (need to know about which has your items in it)
            if self.identity.name() == 'bag of holding':
                return True
            return False

        return self.identity.weight() < y.identity.weight()

    def desirable(self, character, consider_funds=True):
        identity_desirability = self.identity.desirable_identity(character)

        if identity_desirability == constants.IdentityDesirability.desire_seven:
            candles = character.inventory.get_items(Tool, identity_selector=lambda i: i.type == 'candles')
            seven_stacks = [c for c in candles if c.quantity >= 7]

            if len(seven_stacks) == 0:
                return True
            return self == seven_stacks[0]

        return super().desirable(character, consider_funds=consider_funds)

class Gem(Item):
    try_to_price_id = False
    glyph_class = gd.GemGlyph

class Rock(Item):
    glyph_class = gd.RockGlyph

class Ring(Item):
    glyph_class = gd.RingGlyph

class UnimplementedItemClassException(Exception):
    pass

ALL_ITEM_CLASSES = [
    Coin,
    Amulet,
    Armor,
    Food,
    Gem,
    Potion,
    Ring,
    Rock,
    Scroll,
    Spellbook,
    Tool,
    Wand,
    Weapon,
]

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

            elif "in quiver" in parenthetical_status or "at the ready" in parenthetical_status:
                self.status = 'quivered'
                self.slot = 'quiver'

class ItemParser():
    item_pattern = re.compile("^(the|a|an|your|[0-9]+) (blessed|uncursed|cursed)? ?( ?(very|thoroughly)? ?(burnt|rusty|corroded|rustproof|rotted|poisoned|fireproof))* ?((\+|\-)[0-9]+)? ?([a-zA-Z9 -]+?[a-zA-Z9])( containing [0-9]+ items?)?( named ([a-zA-Z!' _]+))? ?(\(.+\))?$")
    
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
        gd.PotionGlyph: re.compile('potions? of (holy |unholy )?([a-zA-Z ]+)$'),
        gd.ScrollGlyph: re.compile('scrolls? of ([a-zA-Z0-9 ]+)$'), #NR9, multi word scrolls
        gd.SpellbookGlyph: re.compile('spellbook of ([a-zA-Z ]+)$'),
    }

    item_class_by_glyph_class = {
        gd.CoinGlyph: Coin,
        gd.AmuletGlyph: Amulet,
        gd.ArmorGlyph: Armor,
        gd.FoodGlyph: Food,
        gd.GemGlyph: Gem,
        gd.PotionGlyph: Potion,
        gd.RingGlyph: Ring,
        gd.RockGlyph: Rock,
        gd.ScrollGlyph: Scroll,
        gd.SpellbookGlyph: Spellbook,
        gd.ToolGlyph: Tool,
        gd.WandGlyph: Wand,
        gd.WeaponGlyph: Weapon,
        gd.CorpseGlyph: Food,
    }

    glyph_class_by_category = {
        'Coins': gd.CoinGlyph,
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
        'Chains': gd.ChainGlyph,
    }

    category_by_glyph_class = {v:k for k,v in glyph_class_by_category.items() if isinstance(v, type)}
    category_by_glyph_class[gd.FoodGlyph] = 'Comestibles'
    category_by_glyph_class[gd.CorpseGlyph] = 'Comestibles'

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
            if glyph_class == gd.PotionGlyph:
                #holiness = match[1]
                # handled using full match string in potion init
                defuzzed_name = match[2]
            else:
                defuzzed_name = match[1]

            identity_class = global_identity_map.identity_by_glyph_class[glyph_class]
            class_names    = identity_class.names()

            if defuzzed_name in class_names.unique():
                return defuzzed_name

            plural_names = identity_class.stacked_names()
            if defuzzed_name in plural_names.unique():
                return identity_class.stacked_name_to_singular(defuzzed_name)

            japanese_names = identity_class.japanese_names()
            if defuzzed_name in japanese_names.unique():
                return identity_class.japanese_name_to_english(defuzzed_name)

            return None

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
        identity = None
        match_components = cls.parse_inventory_item_string(global_identity_map, item_string)
        # First line of defense: figure out if this is a ___ named {ARTIFACT NAME}
        # instance name exists for artifacts that aren't identified (hence why we look at appearance_name)
        if match_components.instance_name is not None:
            identity = global_identity_map.artifact_identity_by_appearance_name.get(match_components.instance_name, None)
            if identity is not None:
                base_identity = global_identity_map.identity_by_numeral[item_glyph]
                global_identity_map.associate_identity_and_name(base_identity, identity.name())

        # Second line of defense: figure out if this is the {ARTIFACT NAME}
        if identity is None:
            identity = global_identity_map.artifact_identity_by_name.get(match_components.description, None)

        # Third line of defense: this isn't an artifact, get its identity from the numeral
        if identity is None:
            try:
                identity = global_identity_map.identity_by_numeral[item_glyph]
            except KeyError:
                #print(f"UNIMPLEMENTED ITEM {item_glyph}")
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
        match_components = cls.parse_inventory_item_string(global_identity_map, item_str)
        description = match_components.description

        if match_components.instance_name is not None:
            identity = global_identity_map.artifact_identity_by_appearance_name.get(match_components.instance_name, None)

            if identity is not None:
                # we've found an artifact
                item_class = cls.item_class_by_glyph_class[identity.associated_glyph_class]
                return item_class(identity, match_components, inventory_letter=inventory_letter)

        #import pdb; pdb.set_trace()
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
            name = None
            if glyph_class != gd.CorpseGlyph:
                appearance_match = cls.appearance_from_description_given_glyph_class(global_identity_map, description, glyph_class)

                if appearance_match is not None:
                    seen_as = appearance_match.appearance
                    possible_glyphs.extend(list(appearance_match.possible_glyphs))

                # try to extract as an artifact
                artifact_identity = global_identity_map.identity_by_name.get((glyph_class, match_components.description), None)
                if artifact_identity is not None and artifact_identity.is_artifact:
                    item_class = cls.item_class_by_glyph_class[artifact_identity.associated_glyph_class]
                    return item_class(artifact_identity, match_components, inventory_letter=inventory_letter)

                name = cls.extract_name_from_description_given_glyph_class(global_identity_map, description, glyph_class)
                #import pdb; pdb.set_trace()
                # try to name the item as a non artifact
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
        container_str: str
        instance_name: str
        full_str: str

    @classmethod
    def parse_inventory_item_string(cls, global_identity_map, item_string):
        match = re.match(cls.item_pattern, item_string)

        if match:
            quantity_match = match[1]
            if quantity_match == "a" or quantity_match == "an" or quantity_match == "the" or quantity_match == "your":
                quantity = 1
            else:
                quantity = int(match[1])

            BUC = global_identity_map.buc_from_string(match[2])
            condition_intensifier = match[3]
            condition = match[4]
            if condition_intensifier is not None and condition is not None:
                condition = condition_intensifier + ' ' + condition

            enhancement = match[6]
            if enhancement is not None:
                enhancement = int(enhancement)

            description = match[8]

            container_str = match[10]

            instance_name = match[11]
            
            equipped_status = match[12]

            return cls.MatchComponents(description, quantity, enhancement, equipped_status, BUC, condition, container_str, instance_name, match[0])

        else:
            if environment.env.debug: import pdb; pdb.set_trace()
            raise Exception(f"couldn't match item string {item_string}")

    item_on_square_pattern = re.compile("You see here (.+?)\.")
    @classmethod
    def listen_for_item_on_square(cls, global_identity_map, character, message, glyph=None):
        item_match = re.search(cls.item_on_square_pattern, message)
        if item_match:
            item_string = item_match[1]
            if glyph is None:
                item = cls.make_item_with_string(global_identity_map, item_string)
            else:
                item = cls.make_item_with_glyph(global_identity_map, glyph.numeral, item_string)
            if item is not None:
                item.price_id(character)
            #import pdb; pdb.set_trace()
            return item

    item_sell_pattern = re.compile("offers ([0-9]+) gold pieces for (.+?)\.")
    @classmethod
    def listen_for_price_offer(cls, global_identity_map, character, message, last_dropped):
        item_match = re.search(cls.item_sell_pattern, message)
        if item_match:
            price = int(item_match[1])
            #item_string = item_match[2]

            #item = cls.make_item_with_string(global_identity_map, item_string)
            #if item is None:
            #    if environment.env.debug: import pdb; pdb.set_trace()
            #    return None
            if last_dropped is None:
                if environment.env.debug: import pdb; pdb.set_trace()
                return

            last_dropped.price_id_from_sell(character, price / last_dropped.quantity)
            #import pdb; pdb.set_trace()

        if "uninterested" in message and last_dropped is not None and last_dropped.identity is not None:
            last_dropped.identity.listened_price_id_methods['sell'] = True

    item_drop_pattern = re.compile("You drop (.+?)\.")
    @classmethod
    def listen_for_dropped_item(cls, global_identity_map, character, message):
        item_match = re.search(cls.item_drop_pattern, message)
        if item_match:
            item_string = item_match[1]

            item = cls.make_item_with_string(global_identity_map, item_string)
            return item

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
        return prefix + str(self.occupant)

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

                        if occ_slot is not None:
                            slots[occ_slot].add_occupant(item)

        #import pdb; pdb.set_trace()
        self.slots = slots

    def blocked_by_letters(self, slot, inventory):
        blockers = [self.slots[block_name].occupant for block_name in self.slots[slot.name].blockers if self.slots[block_name].occupied]

        if slot.occupied:
            blockers.append(self.slots[slot.name].occupant)
        
        return blockers

class SlotFactory():
    @staticmethod
    def make_from_inventory(slot_class, inventory):
        worn_by_slot = {}

        for oclass in slot_class.involved_classes:
            class_contents = inventory.get_oclass(oclass)

            for item in class_contents:

                if item is not None and item.equipped_status is not None:
                    slot = item.equipped_status.slot

                    if slot is not None: # alternatively wielded and other weird things can have none slot
                        if isinstance(slot, list):
                            for s in slot:
                                worn_by_slot[s] = item
                        else:
                            worn_by_slot[slot] = item

        return slot_class(**worn_by_slot)

class ArmamentSlots(NamedTuple):
    shirt:    Armor = None
    suit:     Armor = None
    cloak:    Armor = None
    off_hand: Item  = None
    hand:     Item  = None
    gloves:   Armor = None
    helmet:   Armor = None
    boots:    Armor = None
    quiver:   Item  = None

    blockers_by_name = {
        "shirt": ['suit', 'cloak'],
        "suit" : ['cloak'],
    }

    involved_classes = [Armor, Weapon, Tool]

    def get_blockers(self, slot_name):
        blockers = [getattr(self, b) for b in self.blockers_by_name.get(slot_name, [])]
        blockers.append(getattr(self, slot_name)) # a slot blocks itself
        blockers = [b for b in blockers if b is not None]

        return blockers

class PlayerInventory():
    slot_cluster_mapping = {
        'armaments': ArmamentSlots,
    }

    def __init__(self, global_identity_map, inv_letters, inv_oclasses, inv_strs, inv_glyphs=None):
        self.items_by_class = {}
        self.items_by_letter = {}
        self.slot_groups_by_name = {}

        self.global_identity_map = global_identity_map

        self.inv_strs = inv_strs
        self.inv_letters = inv_letters
        self.inv_oclasses = inv_oclasses
        self.inv_glyphs = inv_glyphs

    @functools.cached_property
    def armaments(self):
        return self.get_slots('armaments')

    class AttireProposal(NamedTuple):
        proposed_items: list = []
        proposal_blockers: list = []

    def proposed_weapon_changes(self, character):
        current_weapon = self.wielded_weapon
        desperate = not current_weapon.uses_relevant_skill(character)

        current_desirability = current_weapon.melee_desirability(character, desperate=desperate)

        most_desirable = current_weapon
        max_desirability = current_desirability

        extra_weapons = self.get_items(Weapon, instance_selector=lambda i: i.equipped_status is None or i.equipped_status.status != 'wielded')
        if len(extra_weapons) == 0:
            return None

        #import pdb; pdb.set_trace()

        for weapon in extra_weapons:
            desirability = weapon.melee_desirability(character, desperate=desperate)
            if desirability > max_desirability:
                # if two hands insist we don't have a shield
                if isinstance(weapon.identity.slot, list) and isinstance(self.armaments.off_hand, Armor):
                    continue
                most_desirable = weapon
                max_desirability = desirability

        if most_desirable != current_weapon:
            #import pdb; pdb.set_trace()
            return most_desirable
        else:
            return None

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
            return self.AttireProposal()

        proposed_items = []
        proposal_blockers = []
        for slot_name, current_occupant in zip(self.armaments._fields, self.armaments):
            unequipped_in_slot = unequipped_by_slot.get(slot_name, [])

            if len(unequipped_in_slot) > 0:
                most_desirable = None
                max_desirability = None
                for item in unequipped_in_slot:
                    if isinstance(item, Armor):
                        desirability = item.instance_desirability_to_wear(character)
                    else:
                        desirability = 0
                    if max_desirability is None or desirability > max_desirability:
                        max_desirability = desirability
                        most_desirable = item

                if current_occupant is not None and isinstance(current_occupant, Armor):
                    current_desirability = current_occupant.instance_desirability_to_wear(character)
                else:
                    current_desirability = 0

                if max_desirability > current_desirability:
                    blockers = self.armaments.get_blockers(slot_name)

                    if len(blockers) == 0:
                        proposed_items.append(most_desirable)
                        proposal_blockers.append(blockers)
                    else:
                        for b in blockers:
                            if isinstance(b, Weapon) or b.BUC == constants.BUC.cursed:
                                pass
                            else:
                                proposed_items.append(most_desirable)
                                proposal_blockers.append(blockers)

        return self.AttireProposal(proposed_items, proposal_blockers)

    def have_item_oclass(self, object_class):
        object_class_num = object_class.glyph_class.class_number
        return object_class_num in self.inv_oclasses

    def get_items(self, oclass=None, name=None, identity_selector=lambda i: True, instance_selector=lambda i: True):
        if oclass is None:
            items = self.all_items()
        else:
            if isinstance(oclass, list):
                classes = [self.get_oclass(kls) for kls in oclass]
                items = [item for kls in classes for item in kls]
            else:
                items = self.get_oclass(oclass)
        matches = []

        for item in items:
            if item and item.identity and (name is None or item.identity.name() == name) and identity_selector(item.identity) and instance_selector(item):
                matches.append(item)

        return matches

    def get_item(self, *args, **kwargs):
        items = self.get_items(*args, **kwargs)
        if len(items) > 0:
            return items[0]
        else:
            return None

    def get_nutrition(self, character):
        food = self.get_items(oclass=Food, identity_selector=lambda i: i.safe_non_perishable(character))
        return sum(map(lambda x: x.quantity * x.identity.nutrition, food))

    def all_undesirable_items(self, character):
        all_items = self.all_items()
        #import pdb; pdb.set_trace()
        undesirable_items = [item for item in all_items if item is not None and not item.desirable(character)]

        # BAND AID FOR WEAPON DROPPING
        undesirable_items = [i for i in undesirable_items if i != self.wielded_weapon]
        return undesirable_items

    def all_unidentified_items(self):
        all_items = self.all_items()
        return [item for item in all_items if item is not None and item.identity is not None and not item.identity.is_identified()]

    def all_items(self):
        all = []

        for oclass in ALL_ITEM_CLASSES:
            oclass_contents = self.get_oclass(oclass)
            all.extend(oclass_contents)

        #if None in all:
        #    import pdb; pdb.set_trace()
        return all

    def get_oclass(self, object_class):
        object_class_num = object_class.glyph_class.class_number

        try:
            items = self.items_by_class[object_class]
            return items
        except KeyError:
            class_contents = []
            oclass_idx = np.where(self.inv_oclasses == object_class_num)[0]

            for i in range(len(self.inv_strs[oclass_idx])):
                letter, raw_string = self.inv_letters[oclass_idx][i], self.inv_strs[oclass_idx][i]
                if self.inv_glyphs is not None:
                    numeral = self.inv_glyphs[oclass_idx][i]
                else:
                    numeral = None

                item_str = ItemParser.decode_inventory_item(raw_string)

                if item_str:
                    # if we're hallucinating, the glyph_numerals are garbage
                    if numeral is None:
                        item = ItemParser.make_item_with_string(self.global_identity_map, item_str, inventory_letter=letter)
                    else:
                        item = ItemParser.make_item_with_glyph(self.global_identity_map, numeral, item_str, inventory_letter=letter)
                    class_contents.append(item)
                    self.items_by_letter[letter] = item
                else:
                    import pdb; pdb.set_trace() # why did we ever check this? why are we here?

            self.items_by_class[object_class] = class_contents
            return class_contents

    def get_slots(self, group_name):
        try:
            return self.slot_groups_by_name[group_name] # if we've already baked the slots
        except KeyError:
            slots = SlotFactory.make_from_inventory(self.slot_cluster_mapping[group_name], self)
            self.slot_groups_by_name[group_name] = slots
            return slots

    def get_current_balance(self):
        all = self.all_items()
        unpaid = [i.price for i in all if (i.shop_owned and i.price is not None)]

        balance = sum(unpaid)
        if balance > 0 and environment.env.debug:
            import pdb; pdb.set_trace()
        return balance

    @functools.cached_property
    def wielded_weapon(self):
        armaments = self.get_slots('armaments')
        hand_occupant = armaments.hand

        if hand_occupant is None:
            return BareHands()

        if hand_occupant.equipped_status.status == 'wielded':
            return hand_occupant
        else:
            if environment.env.debug: pdb.set_trace()

    @functools.cached_property
    def quivered(self):
        quivered_item = self.get_item([Weapon, Gem, Rock], instance_selector=lambda i: i.equipped_status is not None and i.equipped_status.status == 'quivered')
        return quivered_item

    def prepared_for_ranged(self):
        if self.quivered is None:
            return False

        if self.quivered.identity.is_thrown:
            return True

        if self.quivered.identity.is_ammo:
            if isinstance(self.wielded_weapon, BareHands):
                return False
            return self.wielded_weapon.identity.ammo_type_used == self.quivered.identity.ammo_type

        return False


    def to_hit_modifiers(self, character, monster):
        weapon = self.wielded_weapon
        if weapon.enhancement is not None:
            to_hit = weapon.enhancement
        else:
            to_hit = 0
        # TK rings of increased accuracy
        # TK monks and body armor
        # TK monks and no weapon
        # TK blessed against undead etc
        # TK weapon skills adjustments

        return to_hit

