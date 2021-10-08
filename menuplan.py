import pdb
import re
import numpy as np

from collections import OrderedDict

import environment
import glyphs as gd
import utilities
import inventory as inv
import physics
import wish

import nle.nethack as nethack

from utilities import ARS

class MenuResponse:
    follow_with = None
    def __init__(self, match_str):
        if not isinstance(match_str, str) and not isinstance(match_str, re.Pattern):
            raise TypeError()

        if isinstance(match_str, str):
            self.match_str = match_str
        elif isinstance(match_str, re.Pattern):
            self.match_pattern = match_str
            self.match_str = None

    def action_message(self, message_obj):
        if self.match_str is not None:
            if not self.match_str in message_obj.message:
                return None
        else:
            match = re.search(self.match_pattern, message_obj.message)
            if match is None:
                return None

        val = self.value(message_obj)
        return val

    def __repr__(self):
        if self.match_str is not None:
            return self.match_str
        else:
            return str(self.match_pattern)

class EscapeMenuResponse(MenuResponse):
    def value(self, message_obj):
        return nethack.actions.Command.ESC

class YesMenuResponse(MenuResponse):
    def value(self, message_obj):
        if not message_obj.yn_question:
            # Decently common: Fast yn lingers on screen
            return None
        return ord('y')

class NoMenuResponse(MenuResponse):
    def value(self, message_obj):
        if not message_obj.yn_question:
            # Decently common: Fast yn lingers on screen
            return None
        return ord('n')

class CharacterMenuResponse(MenuResponse):
    def __init__(self, match_str, character, follow_with=None):
        super().__init__(match_str)
        self.character = character
        self.follow_with = follow_with

    def value(self, message_obj):
        return ord(self.character)

class FirstLetterChoiceMenuResponse(MenuResponse):
    pattern = re.compile('\[([a-zA-Z]).+\]')
    def value(self, message_obj):
        match = re.search(self.__class__.pattern, message_obj.message)
        if match:
            character = match[1]
            return ord(character)
        return nethack.actions.Command.ESC

class MoreMenuResponse(MenuResponse):
    def __init__(self, match_str, always_necessary=True):
        super().__init__(match_str)
        self.always_necessary = always_necessary # will this message always require a more?

    def value(self, message_obj):
        if self.always_necessary and not message_obj.has_more and environment.env.debug:
            pdb.set_trace()

        if not message_obj.has_more:
            return None
        else:
            return ord(' ')

class DirectionMenuResponse(MenuResponse):
    def __init__(self, match_str, direction):
        super().__init__(match_str)
        if not direction in physics.action_grid:
            raise Exception("Bad direction")
        self.direction = direction

    def value(self, message_obj):
        return self.direction

class EndOfSequence(Exception):
    pass

class TravelNavigationMenuResponse(MenuResponse):
    @staticmethod
    def action_generator(tty_cursor, target_square):
        while True:
            current_square = physics.Square(*tty_cursor) + physics.Square(-1, 0) # offset because cursor row 0 = top line

            if current_square != target_square:
                offset = physics.Square(*np.sign(np.array(target_square - current_square)))
                yield physics.delta_to_action[offset]
            else:
                return

    def __init__(self, match_str, tty_cursor, target_square):
        super().__init__(match_str)

        self.target_square = target_square
        self.action_generator = self.action_generator(tty_cursor, target_square)

    def value(self, message_obj):
        try:
            next_action = next(self.action_generator)
            #import pdb; pdb.set_trace()
            return next_action
        except StopIteration:
            if "(no travel path)" in message_obj.message or "a boulder" in message_obj.message:
                #import pdb; pdb.set_trace()
                return nethack.actions.Command.ESC
            else:
                raise EndOfSequence()

class ConnectedSequenceMenuResponse(MenuResponse):
    def __init__(self, match_str, sequence):
        super().__init__(match_str)
        self.sequence = (c for c in sequence)

    def value(self, message_obj, expect_getline=True):
        try:
            next_chr = next(self.sequence)
            return ord(next_chr)
        except StopIteration:
            return ord('\r')

class PhraseMenuResponse(MenuResponse):
    def __init__(self, match_str, phrase):
        super().__init__(match_str)
        self.phrase = (c for c in phrase)

    def value(self, message_obj, expect_getline=True):
        if expect_getline and not message_obj.getline and environment.env.debug:
            pdb.set_trace()

        try:
            next_chr = next(self.phrase)
            return ord(next_chr)
        except StopIteration:
            return ord('\r')

class WishMenuResponse(MenuResponse):
    def __init__(self, match_str, character, wand=None):
        super().__init__(match_str)
        self.character = character
        self.wand = wand
        self.phrase = None
    
    def value(self, message_obj, expect_getline=True):
        if expect_getline and not message_obj.getline and environment.env.debug:
            pdb.set_trace()
        import pdb; pdb.set_trace()
        if self.phrase is None:
            self.phrase = (c for c in wish.get_wish(self.character, wand=self.wand))
        try:
            next_chr = next(self.phrase)
            return ord(next_chr)
        except StopIteration:
            self.phrase = None
            return ord('\r')

class ExtendedCommandResponse(PhraseMenuResponse):
        def __init__(self, phrase):
            super().__init__("#", phrase)

        def value(self, message_obj):
            if not message_obj.message.startswith('# ') and environment.env.debug:
                pdb.set_trace()
            return super().value(message_obj, expect_getline=False)

class MenuPlan():
    def __init__(self, name, advisor, menu_responses, fallback=None, interactive_menu=None, listening_item=None):
        self.name = name
        self.advisor = advisor
        self.menu_responses = menu_responses
        self.fallback = fallback # carried out in custom_agent after our first failure to match
        self.interactive_menu = interactive_menu
        self.current_interactive_menu = None
        self.in_interactive_menu = False
        self.listening_item = listening_item

    def interact(self, message_obj):
        if message_obj.message is None:
            raise Exception("That's not right")

        if isinstance(self.interactive_menu, list):
            for interactive_menu in self.interactive_menu:
                if interactive_menu.trigger_phrase in message_obj.message:
                    self.in_interactive_menu = True
                    self.current_interactive_menu = interactive_menu
        elif self.interactive_menu and self.interactive_menu.trigger_phrase in message_obj.message:
            self.in_interactive_menu = True
            self.current_interactive_menu = self.interactive_menu

        if self.in_interactive_menu:
            try:
                selected_item = self.current_interactive_menu.search_through_rows(message_obj.tty_chars)
            except EndOfMenu:
                self.in_interactive_menu = False
                self.current_interactive_menu = None
                return ord('\r')
            except EndOfPage:
                self.current_interactive_menu.flip_page()
                return ord('>')
            except MadeSelection:
                self.in_interactive_menu = False
                self.current_interactive_menu = None
                return nethack.actions.TextCharacters.SPACE

            if selected_item is not None:
                if not self.current_interactive_menu.multi_select and not self.current_interactive_menu.confirm_choice:
                    self.in_interactive_menu = False
                    self.current_interactive_menu = None
                return ord(selected_item.character)

        for response in self.menu_responses:
            try:
                action = response.action_message(message_obj)
            except EndOfSequence as e:
                return None

            if action is not None:
                if response.follow_with is not None:
                    self.fallback = response.follow_with

                if isinstance(self.interactive_menu, list):
                    for interactive_menu in self.interactive_menu:
                        if interactive_menu.trigger_action == action:
                            self.interactive_menu = True
                            self.current_interactive_menu = interactive_menu
                elif self.interactive_menu and self.interactive_menu.trigger_action == action:
                    self.in_interactive_menu = True
                    self.current_interactive_menu = self.interactive_menu
                return action

        return None

    def add_responses(self, responses):
        self.menu_responses = self.menu_responses + responses

    def __repr__(self):
        return self.name

class EndOfPage(Exception):
    pass

class EndOfMenu(Exception):
    def __init__(self, last_item):
        self.last_item = last_item

class MadeSelection(Exception):
    pass

class InteractiveMenu():
    menu_item_pattern = re.compile("([a-zA-Z\$]) (-|\+) (.+)$")
    terminator_pattern = re.compile("\(([0-9]+) of ([0-9]+)\)")
    first_page_header_rows = 0
    # We define selectors here so that their implementation is close to the MenuItem implementation
    selectors = {}
    # How should the menu plan know that we're now in the interactive menu.
    # Either because we just pressed * (which is default)
    trigger_action = ord('*')
    # or because we see a particular prompt on the screen, which is helpful for the pickup situation where it could go either way
    trigger_phrase = None
    # Is this an interactive menu where we can select many items?
    multi_select = False
    confirm_choice = False

    class MenuItem():
        def __init__(self, ambient_menu, category, character, selected, item_text):
            self.category = category
            self.character = character
            self.selected = selected
            self.item_text = item_text

    def __init__(self, selector_name=None, pick_last=False):
        self.rendered_rows = []
        self.header_rows = self.first_page_header_rows
        self.vertical_offset = 0
        self.active_category = None
        self.offset = None
        if selector_name:
            self.item_selector = self.selectors[selector_name]
        else:
            self.item_selector = lambda x: True

        self.pick_last = pick_last

    def flip_page(self):
        self.vertical_offset = 0
        self.header_rows = 0

    def search_through_rows(self, tty_chars):
        text_rows = [bytes(row).decode('ascii') for row in tty_chars]
        if not self.offset:
            self.offset = re.search("[^ ]", text_rows[0]).start()
        # Skip header rows plus ones already parsed
        try:
            for row in text_rows[(self.header_rows + self.vertical_offset):]:
                potential_menu = row[self.offset:].rstrip(' ')
                terminator = re.match(self.terminator_pattern, potential_menu)
                if terminator:
                    if terminator[1] == terminator[2]:
                        try:
                            raise EndOfMenu(next_item)
                        except UnboundLocalError:
                            import pdb; pdb.set_trace()
                    else:
                        raise EndOfPage()

                if potential_menu == '(end)':
                    try:
                        raise EndOfMenu(next_item)
                    except UnboundLocalError:
                        import pdb; pdb.set_trace()

                item_match = re.match(self.menu_item_pattern, potential_menu)
                if item_match:
                    if not self.active_category:
                        #if environment.env.debug: import pdb; pdb.set_trace()
                        pass
                    #import pdb; pdb.set_trace()
                    next_item = self.MenuItem(
                        self,
                        self.active_category,
                        item_match[1],
                        item_match[2] == "+",
                        item_match[3]
                    )

                    self.rendered_rows.append(next_item)

                    if next_item.selected:
                        if self.confirm_choice:
                            raise MadeSelection()

                        if not self.multi_select:
                            if environment.env.debug: import pdb; pdb.set_trace()
                            raise Exception("already made selection but not multi_select")

                    #print(next_item.item)
                    if not next_item.selected and self.item_selector(next_item):
                        return next_item
                else:
                    self.active_category = potential_menu
                
                self.vertical_offset += 1
        except EndOfMenu as e:
            if self.pick_last:
                return next_item
            else:
                raise EndOfMenu(None)

        if environment.env.debug:
            import pdb; pdb.set_trace()
            # We should not fall through the menu

class InteractiveLocationPickerMenu(InteractiveMenu):
    pass

class InteractiveValidPlacementMenu(InteractiveLocationPickerMenu):
    header_rows = 2
    trigger_action = None
    trigger_phrase = 'Pick a valid location'
    pick_last = True

class InteractiveEnhanceSkillsMenu(InteractiveMenu):
    first_page_header_rows = 2
    trigger_action = None
    trigger_phrase = 'Pick a skill to advance:'

class ParsingInventoryMenu(InteractiveMenu):
    selectors = {
        'teleport scrolls': lambda x: (isinstance(x.item, inv.Scroll)) and (x.item.identity.name() == 'teleportation'),
        'teleport wands': lambda x: (isinstance(x.item, inv.Wand)) and (x.item.identity is not None and x.item.identity.name() == 'teleportation'),
        'healing potions': lambda x: (isinstance(x.item, inv.Potion)) and (x.item.identity is not None and x.item.identity.name() and "healing" in x.item.identity.name()),
        'extra weapons': lambda x: (isinstance(x.item, inv.Weapon)) and (x.item.identity is not None and (x.item.equipped_status is None or x.item.equipped_status.status != 'wielded')),
        'comestibles': lambda x: isinstance(x.item, inv.Food) and (x.item.parenthetical_status is None or ("for sale" not in x.item.parenthetical_status and "unpaid" not in x.item.parenthetical_status)), # comestibles = food and corpses
        'armor': lambda x: isinstance(x.item, inv.Armor) and (x.item.parenthetical_status is None or ("for sale" not in x.item.parenthetical_status and "unpaid" not in x.item.parenthetical_status)),
    }

    def __init__(self, run_state, selector_name=None, select_desirable=None):
        self.run_state = run_state
        if selector_name and select_desirable:
            raise Exception("Please only specify one of these")
        super().__init__(selector_name=selector_name)

        if select_desirable is not None:
            assert select_desirable in ['undesirable', 'desirable']
            def select_desirable_func(menu_item):
                if menu_item.item is None:
                    if environment.env.debug:
                        if menu_item.item_text[0] in '123456789':
                            # Known thing that we can't count yet
                            pass
                        elif 'corpse' in menu_item.item_text:
                            pass
                        elif 'spellbook' in menu_item.item_text:
                            pass
                        elif 'small glob' in menu_item.item_text:
                            pass
                        elif 'statue' in menu_item.item_text:
                            pass
                        elif 'figurine' in menu_item.item_text:
                            pass
                        elif 'partly used candle' in menu_item.item_text:
                          pass
                        elif 'pair of lenses' in menu_item.item_text:
                          pass
                        else:
                            import pdb; pdb.set_trace()
                        return False
                    else:
                        return False
                else:
                    if menu_item.item.desirable(run_state.global_identity_map, run_state.character): print(menu_item.item_text)
                    menu_item.item.price_id(run_state.character)
                    return menu_item.item.desirable(run_state.global_identity_map, run_state.character)
            if select_desirable == 'desirable':
                self.item_selector = lambda x: select_desirable_func(x)
            else:
                self.item_selector = lambda x: not select_desirable_func(x)

    class MenuItem:
        def __init__(self, ambient_menu, category, character, selected, item_text):
            run_state = ambient_menu.run_state
            self.category = category
            self.character = character
            self.selected = selected
            self.item_text = item_text
            self.item = inv.ItemParser.make_item_with_string(run_state.global_identity_map, item_text, category=category)

class InteractiveDropTypeChooseTypeMenu(InteractiveMenu):
    first_page_header_rows = 2
    trigger_phrase = "Drop what type of items?"
    trigger_action = None
    confirm_choice = True

    selectors = {
        'all types': lambda x: x.item_text == 'All types',
        'unknown BUC': lambda x: x.item_text == 'Items of unknown Bless/Curse status'
    }

class InteractivePickupMenu(ParsingInventoryMenu):
    first_page_header_rows = 2
    trigger_action = None
    trigger_phrase = "Pick up what?"
    multi_select = True

class InteractivePlayerInventoryMenu(ParsingInventoryMenu):
    def __init__(self, run_state, inventory, selector_name=None, desired_letter=None):
        super().__init__(run_state, selector_name=selector_name)
        self.inventory = inventory

        if desired_letter is not None:
            self.desired_letter = desired_letter

            if isinstance(desired_letter, list):
                #desired_letters = [l for l in desired_letter]
                self.item_selector = lambda menu_item: menu_item.item and menu_item.item.inventory_letter in self.desired_letter
            else:
                self.item_selector = lambda menu_item: menu_item.item and menu_item.item.inventory_letter == ord(self.desired_letter)

    class MenuItem:
        def __init__(self, interactive_menu, category, character, selected, item_text):
            self.interactive_menu = interactive_menu
            self.category = category
            self.character = character
            self.selected = selected
            #cls, string, glyph_numeral=None, passed_object_class=None, inventory_letter=None

            try:
                self.item = self.interactive_menu.inventory.items_by_letter[ord(self.character)]
            except KeyError:
                if environment.env.debug:
                    import pdb; pdb.set_trace()
                print("In interactive player inventory menu and haven't loaded class that letter {} belongs to".format(self.character))
                self.item = None

class InteractiveDropTypeMenu(InteractivePlayerInventoryMenu):
    first_page_header_rows = 2
    trigger_action = None
    trigger_phrase = "What would you like to drop?"
    multi_select = True

class InteractiveIdentifyMenu(InteractivePlayerInventoryMenu):
    trigger_phrase = "What would you like to identify first?"
    first_page_header_rows = 2
    trigger_action = None
    confirm_choice = True

    ranked_selectors = OrderedDict({
        'unidentified_potentially_magic_armor': lambda x: (isinstance(x, inv.Armor)) and (x.item.identity is not None and x.item.identity.name() is None and x.item.identity.magic().any()),
        'unidentified_scrolls': lambda x: (isinstance(x, inv.Scroll)) and (x.item.identity is not None and x.item.identity.name() is None),
        'unidentified_potions': lambda x: (isinstance(x, inv.Potion)) and (x.item.identity is not None and x.item.identity.name() is None),
        'unidentified_amulets': lambda x: (isinstance(x, inv.Amulet)) and (x.item.identity is not None and x.item.identity.name() is None),
        'unidentified_wands': lambda x: (isinstance(x, inv.Wand)) and (x.item.identity is not None and x.item.identity.name() is None),
    })

class WizmodeIdentifyMenu(InteractiveMenu):
    first_page_header_rows = 2
    trigger_action = None
    trigger_phrase = "Debug Identify -- unidentified or partially identified items"
    multi_select = True
