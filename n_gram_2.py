import sys
import os
import json
from typing import Counter
import pandas as pd
import nltk
from sklearn.feature_extraction.text import CountVectorizer

if __name__ == '__main__':
    log_directory = sys.argv[1]

with open(os.path.join(log_directory, 'log.csv'), 'r') as f:
    log_df = pd.read_csv(f)

with open(os.path.join(log_directory, "message_by_score.csv"), 'r') as f:
    message_score_df = pd.read_csv(f)
    message_score_df.columns = ['score', 'message', 'replay']
    message_score_df = message_score_df.set_index('score')

vectorizer = CountVectorizer(ngram_range=(4,4))
analyzer = vectorizer.build_analyzer()
aggregate_dict = {}
occurence_dict = {}
categorical_dict = {}
def tally_n_gram_additional_score(replay, final_score, message, message_score):
    #ngrams = nltk.ngrams(message.split(), 4)
    #print(message)
    if pd.isna(message):
        return None

    ngrams = analyzer(message)
    for gram in ngrams:
        try:
            categorical_dict[gram].add(replay)
            aggregate_dict[gram] += final_score - message_score
            occurence_dict[gram] += 1
        except KeyError:
            categorical_dict[gram] = set([replay])
            aggregate_dict[gram] = final_score - message_score
            occurence_dict[gram] = 1
    
    return None

for replay, data in message_score_df.groupby('replay'):
    final_score = log_df.iloc[replay].score

    for score, row in data.iterrows():
        tally_n_gram_additional_score(replay, final_score, row.message, score)

categorical_count_dict = {}
for ngram, replay_set in categorical_dict.items():
    categorical_count_dict[ngram] = len(replay_set)

aggregate_df = pd.DataFrame.from_dict(aggregate_dict, orient='index', columns=['additional score'])
categorical_df = pd.DataFrame.from_dict(categorical_count_dict, orient='index', columns=['n distinct replays'])
occurence_df = pd.DataFrame.from_dict(occurence_dict, orient='index', columns=['occurences'])
df = aggregate_df.join(occurence_df)
df = df.join(categorical_df)
df['average additional'] = df['additional score'] / df['occurences']