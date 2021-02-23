[discord]
prefix = '$'
token = ''

[filtering]
exclude_genres = ['Hentai','Smut','Lolicon','Shotacon'] # results that have one or more of these genres will be discarded.

[internal]
db_path = './db/chiichan.db'
cache_path = './db/chiichan_cache.db'
caching = true # caches manga entries
cache_refresh = 6 # every [n] hours, the cache of manga entries will be refreshed
