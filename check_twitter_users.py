import json
import os
import os.path as osp
import pprint
import torch
from m3inference import M3Twitter

data_dir = "F:\\data\\ScientificReport2021"

path_user_name2id = osp.join(data_dir, "user_name2id.json")

user_name2id = json.load(open(path_user_name2id, 'r', encoding='utf-8'))
user_id2name = {v: k for k, v in user_name2id.items()}

m3twitter = M3Twitter(data_dir, id2name=user_id2name)

from keys import keys

# initialize twitter api


idx_auth = 2

m3twitter.twitter_init(api_key=keys[idx_auth]['API_KEY'],
                       api_secret=keys[idx_auth]['API_KEY_SECRET'],
                       access_token=keys[idx_auth]['ACCESS_TOKEN'],
                       access_secret=keys[idx_auth]['ACCESS_TOKEN_SECRET'])
# alternatively, you may do
# m3twitter.twitter_init_from_file('auth.txt')

user_features_li = []


if osp.exists("user_features_li.pt"):
    user_features_li = torch.load("user_features_li.pt")

else:
    for i, path in enumerate(
            tqdm(os.listdir(osp.join(data_dir, "downloaded_final_user_attributes")), desc="Load Users")):
        if path.endswith('.json'):

            try:
                user = json.load(
                    open(osp.join(data_dir, "downloaded_final_user_attributes", path), 'r', encoding='utf-8'))
                user_features_li.append(user)
            except:
                pass

output = m3twitter.process_twitter_batch(user_features_li)

