from sqlitedict import SqliteDict
import toml
import json

config = {}
with open("chiichan.toml") as f:
    config = toml.load(f)
internal = config.get('internal',{})

db = SqliteDict(internal.get('db_path','./chiichan.db'),encode=json.dumps,decode=json.loads)
triggers = SqliteDict(internal.get('tws_db_path','./chiichan_tws.db'),tablename='triggers',encode=json.dumps,decode=json.loads)
ratings = SqliteDict(internal.get('ratings_db_path','./chiichan_ratings.db'),tablename='ratings',encode=json.dumps,decode=json.loads)

for key,val in db.items():
    if 'trigger' in key:
        triggers[key.split('.')[1]] = val
    elif 'rating' in key:
        ratings[key.split('.')[1]] = val

triggers.commit()
ratings.commit()
