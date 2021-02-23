import statistics, typing
import aiosqlite
from discord.ext import commands
import json

class DatabaseCog(commands.Cog):
    def __init__(self,db_path: str):
        self.db_path = db_path
        self.db = None

    async def load_db(self):
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row

    async def close_db(self):
        await self.db.close()

    # TWs:
    # (INTEGER 'manga', INTEGER 'user', TEXT 'warning')

    async def get_triggers(self, manga: typing.Union[str,int]):
        triggers = {}

        async with self.db.execute('SELECT * FROM tws WHERE manga = ?',[int(manga)]) as cursor:
            async for row in cursor:
                if row['warning'] not in triggers:
                    triggers[row['warning']] = 0

                triggers[row['warning']] += 1

        return triggers

    async def add_triggers(self, manga: typing.Union[str,int], user: int, warnings):
        for tw in warnings:
            exists = await self.db.execute('SELECT * FROM tws WHERE user = ? AND manga = ? AND warning = ?',[user,int(manga),tw])
            if not await exists.fetchone():
                await self.db.execute('INSERT INTO tws (manga,user,warning) VALUES (?,?,?)',[int(manga),user,tw])

        await self.db.commit()

    # Ratings:
    # (INTEGER 'manga', INTEGER 'user', REAL 'rating')

    async def get_rating(self,manga: typing.Union[str,int]):
        ratings = []

        async with self.db.execute('SELECT * FROM ratings WHERE manga = ?',[int(manga)]) as cursor:
            async for row in cursor:
                ratings.append(row['rating'])

        return statistics.fmean(ratings) if ratings else None

    async def set_rating(self, manga: typing.Union[str,int], rating: float, user: int):
        cursor = await self.db.execute('SELECT * FROM ratings WHERE user = ?',[user])

        if await cursor.fetchone():
            await self.db.execute('UPDATE ratings SET rating = ? WHERE user = ? AND manga = ?',[rating,user,manga])
        else:
            await self.db.execute('INSERT INTO ratings (manga,user,rating) VALUES (?,?,?)',[manga,user,rating])

        await self.db.commit()
        await cursor.close()

    # Notifications:
    # (INTEGER 'manga', INTEGER 'user', INTEGER 'guild')

    async def get_notifications(self):
        notifications = {}

        async with self.db.execute('SELECT * from notifications') as cursor:
            async for row in cursor:
                guild, manga, user = row['guild'], row['manga'], row['user']

                if manga not in notifications:
                    notifications[manga] = {}
                if guild not in notifications[manga]:
                    notifications[manga][guild] = []

                notifications[manga][guild].append(user)

        return notifications

    async def add_notification(self, user: int, manga: typing.Union[str,int], guild: int):
        cursor = await self.db.execute('SELECT * FROM notifications WHERE user = ? AND manga = ? AND guild = ?',[user,manga,guild])

        if not await cursor.fetchone():
            await self.db.execute('INSERT INTO notifications (manga,user,guild) VALUES (?,?,?)',[manga,user,guild])

        await self.db.commit()
        await cursor.close()

    # Latest Releases
    # (UNIQUE INTEGER 'manga', TEXT 'latest')
    async def get_latest(self,manga: int):
        cursor = await self.db.execute('SELECT * FROM latest_release WHERE manga = ? ',[manga])
        return await cursor.fetchone()

    async def set_latest(self,manga: int,latest: str):
        await self.db.execute('INSERT OR REPLACE into latest_release (manga,latest) VALUES (?,?)',[manga,latest])
        await self.db.commit()
    # Guilds
    # (UNIQUE INTEGER 'guild', BOOL 'notify', INTEGER 'notify_channel')
    async def get_guild(self,guildid: int):
        cursor = await self.db.execute('SELECT * FROM guilds WHERE guild = ? ',[guildid])
        guild = await cursor.fetchone()
        if guild:
            return {
                'id': guildid,
                'notify': guild['notify'],
                'notify_channel': guild['notify_channel']
            }
        else:
            return {
                'id': guildid,
                'notify': False,
                'notify_channel': None
            }

    async def set_notify(self,guildid: int,notify: bool):
        cursor = await self.db.execute('SELECT * FROM guilds WHERE guild = ?',[guildid])
        if await cursor.fetchone():
            await self.db.execute('UPDATE guilds SET notify = ? WHERE guild = ?',[notify,guildid])
        else:
            await self.db.execute('INSERT INTO guilds (guild,notify,notify_channel) VALUES (?,?,?)',[guildid,notify,0])
        await self.db.commit()

    async def set_notify_channel(self,guildid: int, notify_channel: int):
        cursor = await self.db.execute('SELECT * FROM guilds WHERE guild = ?',[guildid])
        if await cursor.fetchone():
            await self.db.execute('UPDATE guilds SET notify_channel = ? WHERE guild = ?',[notify_channel,guildid])
        else:
            await self.db.execute('INSERT INTO guilds (guild,notify,notify_channel) VALUES (?,?,?)',[guildid,False,notify_channel])
        await self.db.commit()


    # Lists:
    # (TEXT 'list', INTEGER 'user', BLOB 'items') # items is json encoded
    async def get_lists(self,user: int):
        lists = {}
        async with self.db.execute('SELECT * from lists WHERE user = ?',[user]) as cursor:
            async for row in cursor:
                lists[row['list']] = json.loads(row['items'].decode('utf-8'))
        return lists

    async def get_list(self, user: int, list: str):
        cursor = await self.db.execute('SELECT * FROM lists WHERE user = ? AND list = ?',[user,list])
        row = await cursor.fetchone()

        if row:
            return json.loads(row['items'].decode('utf-8'))
        else:
            return None

    async def add_to_list(self,user: int, listn: str, manga: typing.Union[int,str]):
        cursor = await self.db.execute('SELECT * FROM lists WHERE user = ? AND list = ?',[user,listn])
        row = await cursor.fetchone()

        if row:
            list = json.loads(row['items'].decode('utf-8'))
            if int(manga) not in list:
                list.append(int(manga))

            list = json.dumps(list).encode('utf-8')
            await self.db.execute('UPDATE lists SET items = ? WHERE user = ? AND list = ?',[list,user,listn])
        else:
            list = json.dumps([int(manga)]).encode('utf-8')
            await self.db.execute('INSERT INTO lists (list,user,items) VALUES (?,?,?)',[listn,user,list])

        await self.db.commit()
        await cursor.close()

def setup(bot):
    bot.add_cog(DatabaseCog(bot.config['internal']['db_path']))
