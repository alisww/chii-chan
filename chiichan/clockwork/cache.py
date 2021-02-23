import json, typing
import pymanga
import aiosqlite
from discord.ext import commands

class CacheCog(commands.Cog, name='cache'):
    def __init__(self,db_path: str):
        self.db_path = db_path
        self.db = None

    async def load_db(self):
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row

    async def close_db(self):
        await self.db.close()

    async def register(self,manga):
        await self.db.execute('INSERT INTO cache (manga,data) VALUES (?,?)',[int(manga['id']),json.dumps(manga).encode('utf-8')])
        await self.db.executemany('INSERT INTO name_cache (manga,id) VALUES (?,?)',[(name,int(manga['id'])) for name in manga['associated_names']])
        await self.db.commit()

    # cache (INTEGER 'manga', BLOB data) # data is json encoded!
    # name_cache (TEXT 'manga', INTEGER 'id')
    async def fetch_cached(self,id: typing.Union[int,str]):
        cursor = await self.db.execute('SELECT * FROM cache WHERE manga = ?',[id])
        cached = await cursor.fetchone()
        manga = None

        if cached:
            await cursor.close()
            return json.loads(cached[1].decode('utf-8'))
        else:
            manga = pymanga.series(id)
            if manga:
                manga['id'] = id
                await self.register(manga)

                await cursor.close()
                return manga
            else:
                await cursor.close()
                return None

    async def fetch_by_name(self,name):
        cursor = await self.db.execute('SELECT * FROM name_cache WHERE manga = ?',[name])
        cached = await cursor.fetchone()

        if cached:
            return await self.fetch_cached(cached[1])
        else:
            id = pymanga.search(name)['series'][0]['id']
            manga = pymanga.series(id)
            if manga:
                manga['id'] = id
                manga['associated_names'].append(name)

                await self.register(manga)

                return manga
            else:
                await cursor.close()
                return None

# a fake implementation of cache that just goes to pymanga directly
class FakeCache(commands.Cog,name='cache'):
    def __init__(self):
        pass

    async def load_db(self):
        pass

    async def close_db(self):
        pass

    async def cog_before_invoke(self,ctx):
        ctx.cache = self

    async def fetch_by_name(self,name: str):
        id = pymanga.search(name)['series'][0]['id']
        manga = pymanga.series(id)
        if manga:
            manga['id'] = id
            return manga
        else:
            return None

    async def fetch_cached(self,id: typing.Union[int,str]):
        manga = pymanga.series(id)
        if manga:
            manga['id'] = id
            return manga
        else:
            return None

def get_cache(bot):
    if bot.config['internal'].get('caching',False):
        return CacheCog(bot.config['internal'].get('cache_path','chiichan_cache.db'))
    else:
        FakeCache()
def setup(bot):
    bot.add_cog(get_cache(bot))
