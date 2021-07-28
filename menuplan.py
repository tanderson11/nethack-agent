import pdb
import re

import environment
import glyphs as gd
import utilities
import inventory as inv
import physics

import nle.nethack as nethack

from utilities import ARS

class MenuResponse:
    def __init__(self, match_str):
        self.match_str = match_str

    def action_message(self, message_obj):
        if not self.match_str in message_obj.message:
            return None

        val = self.value(message_obj)
        return val

class EscapeMenuResponse(MenuResponse):
    def value(self, message_obj):
        return nethack.ACTIONS.index(nethack.actions.Command.ESC)

class YesMenuResponse(MenuResponse):
    def value(self, message_obj):
        if not message_obj.yn_question:
            # Decently common: Fast yn lingers on screen
            return None
        return utilities.keypress_action(ord('y'))

class NoMenuResponse(MenuResponse):
    def value(self, message_obj):
        if not message_obj.yn_question:
            # Decently common: Fast yn lingers on screen
            return None
        return utilities.keypress_action(ord('n'))

class CharacterMenuResponse(MenuResponse):
    def __init__(self, match_str, character):
        super().__init__(match_str)
        self.character = character

    def value(self, message_obj):
        return utilities.keypress_action(ord(self.character))

class FirstLetterChoiceMenuResponse(MenuResponse):
    pattern = re.compile('\[([a-zA-Z]).+\]')
    def value(self, message_obj):
        match = re.search(self.__class__.pattern, message_obj.message)
        if match:
            character = match[1]
            return utilities.keypress_action(ord(character))
        return nethack.ACTIONS.index(nethack.actions.Command.ESC)

class MoreMenuResponse(MenuResponse):
    def value(self, message_obj):
        if not message_obj.has_more and environment.env.debug:
            pdb.set_trace()
        return utilities.keypress_action(ord(' '))

class DirectionMenuResponse(MenuResponse):
    def __init__(self, match_str, direction):
        super().__init__(match_str)
        if not direction in physics.action_grid:
            raise Exception("Bad direction")
        self.direction = direction

    def value(self, message_obj):
        return utilities.ACTION_LOOKUP[self.direction]

class PhraseMenuResponse(MenuResponse):
    def __init__(self, match_str, phrase):
        super().__init__(match_str)
        self.phrase = phrase
        self.next_index = 0

    def value(self, message_obj):
        if not message_obj.getline and environment.env.debug:
            pdb.set_trace()
        if self.next_index == len(self.phrase):
            self.next_index = 0
            return utilities.keypress_action(ord('\r'))
        character = self.phrase[self.next_index]
        self.next_index += 1
        return utilities.keypress_action(ord(character))


class MenuPlan():
    def __init__(self, name, advisor, menu_responses, fallback=None, interactive_menu=None, listening_item=None):
        self.name = name
        self.advisor = advisor
        self.menu_responses = menu_responses
        self.fallback = fallback
        self.interactive_menu = interactive_menu
        self.in_interactive_menu = False
        self.listening_item = listening_item

    def interact(self, message_obj):
        if message_obj.message is None:
            raise Exception("That's not right")
        if self.interactive_menu and self.interactive_menu.trigger_phrase == message_obj.message:
            self.in_interactive_menu = True
        if self.in_interactive_menu:
            try:
                selected_item = self.interactive_menu.search_through_rows(message_obj.tty_chars)
            except EndOfMenu:
                self.in_interactive_menu = False
                return nethack.ACTIONS.index(nethack.actions.Command.ESC)
            except EndOfPage:
                self.interactive_menu.flip_page()
                return utilities.keypress_action(ord('>'))

            if selected_item is not None:
                if not self.interactive_menu.multi_select:
                    self.in_interactive_menu = False
                return utilities.keypress_action(ord(selected_item.character))

        for response in self.menu_responses:
            action = response.action_message(message_obj)
            if action is not None:
                if self.interactive_menu and self.interactive_menu.trigger_action == action:
                    self.in_interactive_menu = True
                return action

        return None

    def __repr__(self):
        return self.name

class EndOfPage(Exception):
    pass

class EndOfMenu(Exception):
    pass

class InteractiveMenu():
    menu_item_pattern = re.compile("([a-zA-Z]) (-|\+) (.+)$")
    terminator_pattern = re.compile("\(([0-9]+) of ([0-9]+)\)")
    header_rows = 0
    # We define selectors here so that their implementation is close to the MenuItem implementation
    selectors = {}
    # How should the menu plan know that we're now in the interactive menu.
    # Either because we just pressed * (which is default)
    trigger_action = utilities.keypress_action(ord('*'))
    # or because we see a particular prompt on the screen, which is helpful for the pickup situation where it could go either way
    trigger_phrase = None
    # Is this an interactive menu where we can select many items?
    multi_select = False

    class MenuItem():
        def __init__(self, run_state, category, character, selected, item_text):
            self.category = category
            self.character = character
            self.selected = selected
            self.item_text = item_text

    def __init__(self, run_state, selector_name=None):
        #if environment.env.debug: pdb.set_trace()
        self.run_state = run_state
        self.rendered_rows = []
        self.vertical_offset = 0
        self.active_category = None
        self.offset = None
        if selector_name:
            self.item_selector = self.selectors[selector_name]
        else:
            self.item_selector = lambda x: True

    def flip_page(self):
        self.vertical_offset = 0

    def search_through_rows(self, tty_chars):
        text_rows = [bytes(row).decode('ascii') for row in tty_chars]
        if not self.offset:
            self.offset = re.search("[^ ]", text_rows[0]).start()
        # Skip header rows plus ones already parsed
        for row in text_rows[(self.header_rows + self.vertical_offset):]:
            potential_menu = row[self.offset:].rstrip(' ')
            terminator = re.match(self.terminator_pattern, potential_menu)
            if terminator:
                if terminator[1] == terminator[2]:
                    raise EndOfMenu()
                else:
                    raise EndOfPage()

            if potential_menu == '(end)':
                raise EndOfMenu()

            item_match = re.match(self.menu_item_pattern, potential_menu)
            if item_match:
                if not self.active_category:
                    if environment.env.debug: pdb.set_trace()
                next_item = self.MenuItem(
                    self.run_state,
                    self.active_category,
                    item_match[1],
                    item_match[2] == "+",
                    item_match[3]
                )
                self.rendered_rows.append(next_item)

                if not next_item.selected and self.item_selector(next_item):
                    return next_item

            else:
                self.active_category = potential_menu
            
            self.vertical_offset += 1

        if environment.env.debug:
            pdb.set_trace()
            # We should not fall through the menu

class InteractiveEnhanceSkillsMenu(InteractiveMenu):
    header_rows = 2
    trigger_action = None
    trigger_phrase = 'Pick a skill to advance:'

class InteractiveInventoryMenu(InteractiveMenu):
    selectors = {
        'teleport scrolls': lambda x: (isinstance(x, inv.Scroll)) and (x.item.identity is not None and x.item.identity.name() == 'teleport'),
        'teleport wands': lambda x: (isinstance(x, inv.Wand)) and (x.item.identity is not None and x.item.identity.name() == 'teleporation'),
        'healing potions': lambda x: (isinstance(x, inv.Potion)) and (x.item.identity is not None and "healing" in x.item.identity.name()),
        'extra weapons': lambda x: (isinstance(x, inv.Weapon)) and (x.item.identity is not None and x.item.equipped_status is not None and x.item.equipped_status.status != 'wielded'),

        'comestibles': lambda x: isinstance(x, inv.Food) and x.item.parenthetical_status is not None and "for sale" not in x.item.parenthetical_status, # comestibles = food and corpses
        'armor': lambda x: x and isinstance(x, inv.Armor) and x.item.parenthetical_status is not None and "for sale" not in x.item.parenthetical_status,
    }

    class MenuItem:
        #quantity BUC erosion_status enhancement class appearance (wielded/quivered_status / for sale price)
        # 'a rusty corroded +1 long sword (weapon in hand)'
        # 'an uncursed very rusty +0 ring mail (being worn)'

        def __init__(self, run_state, category, character, selected, item_text):
            self.category = category
            self.character = character
            self.selected = selected
            #cls, string, glyph_numeral=None, passed_object_class=None, inventory_letter=None
            self.item = inv.ItemParser.parse_inventory_item(run_state.global_identity_map, item_text, category=category)

class InteractivePickupMenu(InteractiveInventoryMenu):
    header_rows = 2
    trigger_action = None
    trigger_phrase = "Pick up what?"