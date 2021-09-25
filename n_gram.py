import sys
import os
import json
from typing import Counter
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer

if __name__ == '__main__':
    log_directory = sys.argv[1]

with open(os.path.join(log_directory, 'log.csv'), 'r') as f:
    log_df = pd.read_csv(f)

with open(os.path.join(log_directory, "message_counter.json"), 'r') as f:
    message_counter = json.load(f)


vectorizer = CountVectorizer(ngram_range=(4,5))
analyzer = vectorizer.build_analyzer()

categorical = {}
incremental = {}

for replay_number,counter in message_counter.items():
    log_line = log_df.iloc[int(replay_number)]
    message_counter = Counter(counter)
    for message, occurences in message_counter.items():
        x = analyzer(message)
        for n_gram in x:
            categorical[(n_gram, replay_number)] = True
            incremental_current = incremental.get((n_gram, replay_number), 0)
            incremental[(n_gram, replay_number)] = occurences + incremental_current
    
    import pdb; pdb.set_trace()
    #print(analyzer(message_counter))