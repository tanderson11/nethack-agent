class MenuPlan():
    def __init__(self, name, match_to_keypress, expects_strange_messages=False, fallback=None):
        self.name = name
        self.match_to_keypress = match_to_keypress
        self.keypress_count = 0

        self.expects_strange_messages = expects_strange_messages
        self.fallback = fallback

    def interact(self, message_obj):
        for k, v in self.match_to_keypress.items():
            if k in message_obj.message:
                self.keypress_count += 1
                return v

        if self.keypress_count == 0:
            pass

        return None

    def __repr__(self):
        return self.name