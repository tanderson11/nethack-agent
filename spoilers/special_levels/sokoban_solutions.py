from typing import NamedTuple
import nle.nethack as nethack
import enum
# offsets relative to sokoban region (0,0) -> top left corner of region
# tuple = boulder starting position for the manuever
sokoban_operations = {
    ("Sokoban 1", "a"): [
        ((2,5), 'd'),
        ((2,6), 'rrrr'),
        ((5,9), 'dd'),
        ((8,8), 'u'),
        ((8,7), '*l'),
        ((8,10), 'u'),
        ((8,9), 'lll*l'),
        ((7,10), 'dlll ll*l'),
        ((7,9), 'dlll lll*'),
        ((7,8), 'dlll llll *u'),
        ((3,10), 'r'),
        ((2,10), 'ddld dddl llll lllu *u'),
        ((3,12), 'dlll dddd llll llll uu*u'),
        ((3,11), 'lldd dddl llll lllu uu*u'),
        ((2,11), 'ddll dddd llll llll uuuu *u'),
        ((3,7), 'urrr ddld dddl llll lllu uuuu *u')
    ],
    ("Sokoban 1", "b"): [
        ((2,2), 'r'),
        ((3,2), 'u'),
        ((3,9), 'rlll llll'),
        ((4,10), 'ddd'),
        ((9,9), 'l'), # H l
        ((10,8), '*l'), # I l*
        ((10,10), 'lll*l'), # J llll*
        ((7,10), 'dddl lll*l'),
        ((8,9), 'ddll ll*l'),
        ((9,8), 'dlll lll*u'),
        ((7,8), 'dddl llll lu*u'),
        ((2, 10), 'dddd dddd llll llll uuuu *r'), #B dddd dddd llll llll uuuu r*
        ((3,3), 'rrrr rrrd dddd ddll llll lluu uur*r'),
        ((2,2), 'drrr rrrr rddd dddd llll llll uuuu rr*r'),
    ],
    ("Sokoban 2", "a"): [
        ((3,8), 'dd'),
        ((4,9), 'l'),
        ((11,3), 'rrru'),
        ((10,10), 'r*r'),
        ((10, 7), 'd'),
        ((9,10), 'l'),
        ((4,9), 'u'), #F u
        ((4,8), 'll'),
        ((8,7), 'd'),
        ((9,9), 'rdrr *r'), #M rdrr r*
        ((11,7), 'llll lrrr rrrr uu'),
        ((9,7), 'dd'), #K dd
        ((9,9), 'rdrr r*r'),
        ((9,5), 'dd'),
        ((10,6), 'r'),
        ((11,7), 'rruu rdrr rr*r'), #K rruu rdrr rrr*
        ((10,7), 'drru urdr rrrr r*r'),
        ((11,5), 'lllr rrrr rruu rdrr rrr*r'),
        ((7,6), 'drdd drru urdr rrrr rr*r'),
        ((8,3), 'rrrr dddr ruur drrr rrrr r*r'),
        ((3,2), 'u'), #A u
        ((6,2), 'r'),
        ((5,2), 'u'),
        ((5,4), 'r'),
        ((5,6), 'dddr dddr ruur drrr rrrr rr*r'), #finish B
        ((5,5), 'rddd rddd rruu rdrr rrrr rrrr *r'),
        ((6,5), 'rrdd dddr ruur drrr rrrr rrrr *r'),
        ((6,3), 'rrrr dddd drru urdr rrrr rrrr rrr*r'),
        ((2,2), 'u'), # clear blockage
    ],
    ("Sokoban 2", "b"): [
        ((3,6), 'lllr rrrr u'),
        ((7,2), 'uuuu u'),
        ((9,2), 'uuuu uur'),
        ((8,3), 'rrrr r'),
        ((9,9), 'r'), #R r
        ((10,10), 'r*r'),
        ((10,8), 'rrrr *r'),
        ((8,9), 'ddrr rr*r'),
        ((9,10), 'drrr r*r'),
        ((7,10), 'dddr rrrr *r'),
        ((8,8), 'rrdd rrrr rr*r'),
        ((7,8), 'dddr rrrr rrrr *r'),
        ((9,3), 'urrr rrrr ddrr rrrr rr*r'), #finish O
        ((9,4), 'urrr rrrd drrr rrrr rr*r'),
        ((7,3), 'ldrr rrrr rrdd rrrr rrrr rrr*'),
        ((2,2), 'dddd ddrr rrrr rrdd rrrr rrrr rrr*r'), #finish G
        ((3,3), 'lddd ddrr rrrr rrdd rrrr rrrr rrrr *r'),
        ((2,3), 'ddld dddr rrrr rrrd drrr rrrr rrrr rrr*'),
        ((9,6), 'ulll rrrr rrrd drrr rrrr rrrr rrr*r'),
        ((7,6), 'dlll rrrr rrrd drrr rrrr rrrr rrrr *r'),
    ]

}

import physics
chr_to_offset = {
    'd': physics.Square(1,0),
    'u': physics.Square(-1,0),
    'l': physics.Square(0,-1),
    'r': physics.Square(0,1),
}

chr_to_dir = {
    'd': nethack.actions.CompassDirection.S,
    'u': nethack.actions.CompassDirection.N,
    'l': nethack.actions.CompassDirection.W,
    'r': nethack.actions.CompassDirection.E,
}

class SokobanMove(NamedTuple):
    start_square: physics.Square
    end_square: physics.Square
    action: enum.IntEnum
    expect_plug: bool = False

class SokobanSolution():
    def __init__(self) -> None:
        self.spoiler_by_level = {}
        for level_info, operations in sokoban_operations.items():
            level_name, variant = level_info
            moves = []
            for operation in operations:
                op_moves = self.make_operation(*operation)
                #print(op_moves)
                moves.extend(op_moves)

            self.spoiler_by_level[level_info] = moves

    @staticmethod
    def make_operation(boulder_start, op_string):
        op_string = op_string.replace(' ', '')
        boulder_current = physics.Square(*boulder_start)
        expect_plug = False
        moves = []
        for c in op_string:
            if c == '*':
                expect_plug = True
                continue
            step_offset = chr_to_offset[c]
            player_location_needed = boulder_current - step_offset
            move = SokobanMove(start_square=player_location_needed, end_square=boulder_current, action=chr_to_dir[c], expect_plug=expect_plug)
            moves.append(move)

            #print(f"{tuple(player_location_needed)}, {chr_to_dir[c]}") 
            boulder_current += step_offset
            expect_plug = False

        return moves

SOKOBAN_SOLUTIONS = SokobanSolution().spoiler_by_level