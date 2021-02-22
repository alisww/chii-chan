# small script to switch pickle-encoded dbs to json-encoded

import json
import pickle
import toml
import sqlite3
from sqlitedict import SqliteDict

def switch_encode(obj):
    def set_serialize(o):
        if isinstance(o,set):
            return list(o)
        return o

    return sqlite3.Binary(json.dumps(obj,default=set_serialize).encode('utf-8'))

config = {}
with open("chiichan.toml") as f:
    config = toml.load(f)

filtered_genres = set([g.lower() for g in config.get('filtering',{}).get('exclude_genres',[])])

internal = config.get('internal',{})

db = SqliteDict(internal.get('db_path','./chiichan.db'),encode=switch_encode,decode=pickle.loads)

cache = SqliteDict(internal.get('cache_path','./chiichan_cache.db'),tablename='cache',encode=switch_encode,decode=pickle.loads)
cache_by_name = SqliteDict(internal.get('cache_path','./chiichan_cache.db'),tablename='cache_by_name',encode=switch_encode,decode=pickle.loads)

for k,v in db.items():
    db[k] = v

db.commit()

for k,v in cache.items():
    cache[k] = v

cache.commit()

for k,v in cache_by_name.items():
    cache_by_name[k] = v

cache_by_name.commit()
