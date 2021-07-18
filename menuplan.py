import pdb
import re

import environment
import glyphs as gd
import utilities
import inventory as inv

import nle.nethack as nethack

from utilities import ARS

class MenuPlan():
    def __init__(self, name, advisor, match_to_keypress, interactive_menu_header_rows=None, menu_item_selector=None, expects_strange_messages=False, fallback=None):
        self.name = name
        self.advisor = advisor
        self.match_to_keypress = match_to_keypress
        self.keypress_count = 0

        self.menu_item_selector = menu_item_selector
        self.interactive_menu_header_rows = interactive_menu_header_rows
        self.expects_strange_messages = expects_strange_messages
        self.fallback = fallback

    def interact(self, message_obj, live_interactive_menu):
        if message_obj.interactive_menu_class is not None:
            #if environment.env.debug: pdb.set_trace()
            if self.menu_item_selector:
                selected_item = live_interactive_menu.add_rows(message_obj.tty_chars, self.interactive_menu_header_rows, self.menu_item_selector)
                if selected_item is not None:
                    return utilities.keypress_action(ord(selected_item.character))

            return nethack.ACTIONS.index(nethack.actions.Command.ESC)
            #return utilities.keypress_action(ord('\r')) # carriage return to see more if no matches
        for k, v in self.match_to_keypress.items():
            if k in message_obj.message:
                self.keypress_count += 1
                return v

        if self.keypress_count == 0:
            pass

        return None

    def __repr__(self):
        return self.name

class InteractiveMenu():
    menu_item_pattern = re.compile("([a-zA-z]) (-|\+) (.+)$")
    def __init__(self):
        #if environment.env.debug: pdb.set_trace()

        self.rendered_rows = []
        self.category_count = 0
        self.active_category = None
        self.offset = None

    def add_rows(self, tty_chars, menu_header_rows, item_selector=None):
        text_rows = [bytes(row).decode('ascii') for row in tty_chars]
        if not self.offset:
            self.offset = re.search("[^ ]", text_rows[0]).start()
            #if text_rows[1].rstrip(' '): if environment.env.debug: pdb.set_trace()
        # Skip 2 header rows plus ones already parsed
        for row in text_rows[(len(self.rendered_rows) + menu_header_rows + self.category_count):]:
            potential_menu = row[self.offset:].rstrip(' ')
            if potential_menu == '(end)': # Probably need to handle 1 of 2 pages and such
                break

            if isinstance(self,InteractiveEnhanceSkillsMenu):
                pass #pdb.set_trace()

            item_match = re.match(self.menu_item_pattern, potential_menu)
            if item_match:
                if not self.active_category:
                    if environment.env.debug: pdb.set_trace()
                next_item = self.MenuItem(self.active_category, item_match[1], item_match[2] == "+", item_match[3])
                self.rendered_rows.append(next_item)
                if not next_item.selected and item_selector and item_selector(next_item):
                    return next_item
            else:
                self.active_category = potential_menu
                self.category_count += 1

class InteractiveEnhanceSkillsMenu(InteractiveMenu):
    
    class MenuItem:
        pattern = re.compile("")

        def __init__(self, category, character, selected, line_text):
            self.category = category
            self.character = character
            self.selected = selected
            self.line_text = line_text

class InteractiveInventoryMenu(InteractiveMenu):
    class MenuItem:
        #quantity BUC erosion_status enhancement class appearance (wielded/quivered_status / for sale price)
        # 'a rusty corroded +1 long sword (weapon in hand)'
        # 'an uncursed very rusty +0 ring mail (being worn)'

        def __init__(self, category, character, selected, item_text):
            #print(item_text)
            self.category = category
            self.character = character
            self.selected = selected
            self.item_name = None
            self.item_appearance = None
            self.item_equipped_status = ''

            match = re.match(inv.ItemParser.item_pattern, item_text)
            if match:
                if match[1] == "a" or match[1] == "an":
                    self.quantity = 1
                else:
                    self.quantity = int(match[1])

                item_description = match[8]
                if match[9] is not None:
                    self.item_equipped_status = match[9]
            else:
                if environment.env.debug: pdb.set_trace()

            if item_description in gd.ALL_OBJECT_NAMES:
                self.item_name = item_description
                self.item_appearance = item_description # choosing to trample appearance with identified appearance
            else:

                # doesn't always work: item description is like "blessed +1 orcish dagger (weapon in hand)"
                if not item_description in gd.ALL_OBJECT_APPEARANCES:
                    #if environment.env.debug: pdb.set_trace()
                    pass

                self.item_appearance = item_description
                self.item_name = '' # slightly questionable but it lets us check `in` on item names that aren't defined
                #if environment.env.debug: pdb.set_trace()

            #print(self.item_name, self.item_appearance)