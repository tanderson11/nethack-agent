import os
import re
import tqdm
import bz2

import pandas as pd

# problem if the lines get cut off onto a new line
score_line_pattern = re.compile("You ((?:were |turned to )?([a-zA-Z]+)) in ([a-zA-Z ]+) on dungeon level ([0-9]+) with ([0-9]+) points")
gold_moves_line_pattern = re.compile("and ([0-9]+) pieces of gold, after ([0-9]+) moves")
exp_level_line_pattern = re.compile("You were level ([0-9]+) with a maximum of ([0-9]+) hit points when you")
vanquished_line_pattern = re.compile("([0-9]+) creatures vanquished.")
role_pattern = re.compile('role: ([a-zA-Z]+)')
race_pattern = re.compile('race: ([a-zA-Z]+)')
gender_pattern = re.compile('gender: ([a-zA-Z]+)')
alignment_pattern = re.compile('alignment: ([a-zA-Z]+)')
killer_pattern = re.compile('killed by (.+) [0-9]{4}') # looking for 4 digit date to end
headstone_pattern = re.compile('\/     PEACE([\s\S]+)\*  \*  \*')
spaces_pattern = re.compile('\s\s+')
coda_pattern1 = re.compile(b'Final Attributes:')
coda_pattern2 = re.compile(b'Final Status:')
status_match = re.compile('Final resting place for.+, while ([a-zA-Z ]+).')
#re.search('Final resting place for.+, while ([a-zA-Z ]+).',

def ttyrec_parse(f, path):
    d = {}
    d['path'] = path
    d['frames'] = 0
    d['kills'] = 0
    
    preamble_flag = True
    coda_flag = False
    for raw_line in f:
        d['frames'] += 1
        
        
        if preamble_flag: # our first frame contains necessary information
            line = str(raw_line)
            role_match = re.search(role_pattern, line)
            if role_match:
                role = role_match[1]
                if role == "Priest" or role == "Priestess":
                    d['role'] = "Priest/Priestess"
                elif role == "Cavewoman" or role == "Caveman":
                    d['role'] = "Caveperson"
                else:
                    d['role'] = role

            race_match = re.search(race_pattern, line)
            if race_match:
                d['race'] = race_match[1]

            gender_match = re.search(gender_pattern, line)
            if gender_match:
                d['gender'] = gender_match[1]

            alignment_match = re.search(alignment_pattern, line)
            if alignment_match:
                d['alignment'] = alignment_match[1]
            
            if role_match:
                preamble_flag = False
        
        
        coda_match1 = re.search(coda_pattern1, raw_line)
        coda_match2 = re.search(coda_pattern2, raw_line)
        if coda_match1 and coda_match2: # look for a known quantity that only appears after death to
            #(1) avoid bad matches from weird named items in game
            #(2) speed up parsing by only looking for matches in the tail of the file
            coda_flag = True
            
        if coda_flag:
            line = str(raw_line)
            score_match = re.search(score_line_pattern, line)

            if score_match:
                #print(score_match)
                d['death_type'] = str(score_match[2])
                d['branch'] = str(score_match[3])
                d['depth'] = int(score_match[4])
                d['score'] = int(score_match[5])

                # this only happens in the same frame with the score line
                #there are just nasty unprintables separating them
                gold_moves_match = re.search(gold_moves_line_pattern, line)

                if gold_moves_match:
                    d['gold'] = int(gold_moves_match[1])
                    d['steps'] = int(gold_moves_match[2])
                else:
                    #print(raw_line)
                    pass
                    #assert False, "Expected gold+moves line on same frame as score line."

                exp_level_line_match = re.search(exp_level_line_pattern, line)

                if exp_level_line_match:
                    d['explevel'] = int(exp_level_line_match[1])
                    d['maxhp'] = int(exp_level_line_match[2])
                else:
                    #print(raw_line)
                    pass
                    #assert False, "Expected exp level line on same frame as score line."

                death_status_match = re.search(status_match, line)
                if death_status_match:
                    d['status'] = death_status_match[1]
                    #print("status found")
                else:
                    d['status'] = None
                    
            if "pieces of gold, after" in line and not score_match:
                import pdb; pdb.set_trace() # looks like we're on the score screen, but we failed to match score

            if "Vanquished creatures:" in line:
                d['kills'] = 1  # when only one line in kills, it doesn't show total separately
                # 0 kills and it doesn't show at all, hence our default of 0

            vanquished_match = re.search(vanquished_line_pattern, line) # but if many kills, we'll find a match
            if vanquished_match:
                d['kills'] = int(vanquished_match[1])

            headstone_match = re.search(headstone_pattern, line)
            if headstone_match:
                cleaner_headstone = re.sub(spaces_pattern, ' ', re.sub(r'[^\x00-\x7F]|\s|\\r|\\x1b|\[B|\[K|\|', ' ', headstone_match[1]))
                killer_match = re.search(killer_pattern, cleaner_headstone)
                if killer_match:
                    d['killer'] = killer_match[1]
                    #import pdb; pdb.set_trace()
                else:
                    #import pdb; pdb.set_trace()
                    pass
    return d

def parse_dir(dr, outpath=None):
    #os.chdir(dr)

    files = [os.path.join(dr,f) for f in sorted(os.listdir(dr)) if os.path.isfile(os.path.join(dr,f)) and f.endswith('.ttyrec.bz2')]

    rows = []
    for file in tqdm.tqdm(files):
        path = os.path.join(dr, file)

        with bz2.BZ2File(path) as f:
            row = ttyrec_parse(f, path)
            replay_number = int(re.search('([0-9]+)\.ttyrec\.bz2$', file)[1])
            row['replay_number'] = replay_number
            rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values('replay_number')
    #import pdb; pdb.set_trace()

    print('Killers')
    print(df.groupby("killer").count().sort_values("score", ascending=False))
    print('Status when dead')
    print(df.groupby("status").count().sort_values("score", ascending=False))

    if outpath is not None:
        with open(outpath, 'wb') as f:
            df.to_csv(f)

    return df