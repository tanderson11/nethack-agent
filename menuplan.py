import pdb
import re

import environment
import glyphs as gd
import utilities

class MenuPlan():
    def __init__(self, name, match_to_keypress, menu_item_selector=None, expects_strange_messages=False, fallback=None):
        self.name = name
        self.match_to_keypress = match_to_keypress
        self.keypress_count = 0

        self.menu_item_selector = None
        self.expects_strange_messages = expects_strange_messages
        self.fallback = fallback

    def interact(self, message_obj, live_interactive_menu):
        if message_obj.has_interactive_menu:
            if self.menu_item_selector:
                selected_item = live_interactive_menu.add_rows(message_obj.tty_chars, self.menu_item_selector)
                if selected_item is not None:
                    return utilities.keypress_action(ord(selected_item.character))
            return utilities.keypress_action(ord('\r'))
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
    class MenuItem:
        singular_pattern = re.compile("(a|an) (.+)$")
        plural_pattern = re.compile("([0-9]+) (.+)s$")
        def __init__(self, category, character, selected, item_text):
            print(item_text)
            self.category = category
            self.character = character
            self.selected = selected
            self.item_name = None
            self.item_apperance = None
            match = re.match(self.singular_pattern, item_text)
            if match:
                self.quantity = 1
                item_description = match[2]
            else:
                match = re.match(self.plural_pattern, item_text)
                self.quantity = int(match[1])
                item_description = match[2]

            if item_description in gd.ALL_OBJECT_NAMES:
                self.item_name = item_description
            else:
                if not item_description in gd.ALL_OBJECT_APPEARANCES:
                    if environment.env.debug: pdb.set_trace()
                self.item_apperance = item_description

    menu_item_pattern = re.compile("([a-zA-z]) (-|\+) (.+)$")

    def __init__(self):
        self.rendered_rows = []
        self.category_count = 0
        self.active_category = None
        self.offset = None

    def add_rows(self, tty_chars, item_selector=None):
        text_rows = [bytes(row).decode('ascii') for row in tty_chars]
        if not self.offset:
            self.offset = re.search("[^ ]", text_rows[0]).start()
            if text_rows[1].rstrip(' '):
                if environment.env.debug: pdb.set_trace()
        # Skip 2 header rows plus ones already parsed
        for row in text_rows[(len(self.rendered_rows) + 2 + self.category_count):]:
            potential_menu = row[self.offset:].rstrip(' ')
            if potential_menu == '(end)':
                break
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
