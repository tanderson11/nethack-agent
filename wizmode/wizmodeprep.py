from re import L
from nle import nethack

import advice.advisors as advisors
import advice.menuplan as menuplan

class WizmodePrepAdvisor(advisors.Advisor): # dummy advisor to hold background menu plans
    def advice(self, rng, run_state, character, oracle):
        pass

class WizmodePrep():
    wishlist = [
        'blessed +10 silver dragon scale mail',
        'blessed fireproof +10 cloak of magic resistance',
        'blessed fireproof +10 boots of speed',
        'blessed rustproof +10 gauntlets of power',
        'blessed rustproof +10 helm of brilliance',
        'blessed +10 Grayswandir',
    ]

    def __init__(self):
        self.prepped = False
        self.advisor = WizmodePrepAdvisor()
        self.wishlist_index = 0
        self.post_wish_identify = False

    def wish(self, phrase):
        action = nethack.actions.Command.EXTCMD
        menu_plan = menuplan.MenuPlan(
            "wizmode_wish",
            self.advisor,
            [
                menuplan.ExtendedCommandResponse("wizwish"),
                menuplan.PhraseMenuResponse("For what do you wish?", phrase),
            ]
        )
        return action, menu_plan

    def identify_all(self):
        action = nethack.actions.Command.EXTCMD
        menu_plan = menuplan.MenuPlan(
            "wizmode_identify",
            self.advisor,
            [
                menuplan.ExtendedCommandResponse("wizidentify"),
            ],
            interactive_menu=menuplan.WizmodeIdentifyMenu(),
        )
        return action, menu_plan


    def next_action(self):
        if self.wishlist_index < len(self.wishlist):
            action, menu_plan = self.wish(self.wishlist[self.wishlist_index])
            self.wishlist_index += 1
        elif not self.post_wish_identify:
            action, menu_plan = self.identify_all()
            self.prepped = True
        return action, menu_plan

