import re
import representation.glyphs as gd
from utilities import ARS

MONSTER_REGEX = '( )*((T|t)he )?(poor )?(invisible )?(saddled )?([a-zA-Z -]+?)( of .+?)?'

class RecordedMonsterEvent():
    def __init__(self, time, monster_name):
        self.time = time
        self.monster_name = monster_name

        self.monster_glyph = gd.get_by_name(gd.MonsterAlikeGlyph, self.monster_name)

    @classmethod
    def involved_monster(cls, message):
        match = re.search(cls.pattern, message)
        if match is None:
            return None
        monster_name = match[cls.name_field]
        # Blind and don't know what's going on
        if monster_name == 'it':
            return None
        
        #import pdb; pdb.set_trace()
        return monster_name

class RecordedMonsterFlight(RecordedMonsterEvent):
    pattern = re.compile(f"{MONSTER_REGEX} turns to flee.")
    name_field = 7

class RecordedMonsterDeath(RecordedMonsterEvent):
    pattern = re.compile(f"You kill {MONSTER_REGEX}!")
    name_field = 7

    def __init__(self, square, time, monster_name):
        self.square = square # doesn't know about dungeon levels
        super().__init__(time, monster_name)
        self.can_corpse = bool(self.monster_glyph.corpse_spoiler)

class RecordedSeaMonsterGrab(RecordedMonsterEvent):
    pattern = re.compile(f"{MONSTER_REGEX} swings itself around you!")
    name_field = 7

class RecordedMonsterGrab(RecordedMonsterEvent):
    pattern = re.compile(f"{MONSTER_REGEX} grabs you!")
    name_field = 7

class RecordedCannotEscape(RecordedMonsterEvent):
    pattern = re.compile(f"You cannot escape from {MONSTER_REGEX}!")
    name_field = 7

class RecordedRelease(RecordedMonsterEvent):
    pattern = re.compile(f"{MONSTER_REGEX} releases you.")
    name_field = 7

class RecordedPullFree(RecordedMonsterEvent):
    pattern = re.compile(f"You pull free from {MONSTER_REGEX}.")
    name_field = 7

