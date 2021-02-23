from .db import *
from .cache import *
from chiichan import Manga
from discord.ext import commands, tasks
import asyncio
import discord

class NotifierCog(commands.Cog):
    def __init__(self, bot,db,cache): # db = reference to a DatabaseCog; cache = reference to a CacheCog
        self.bot = bot
        self.db = db
        self.cache = cache
        self.batch = None

        self.lock = asyncio.Lock()

        self.loader.start()
        self.notifier.start()

    @commands.command()
    async def subscribe(self,ctx,*,manga: Manga):
        if not manga:
            return

        if not (await ctx.db.get_guild(ctx.guild.id))['notify']:
            await ctx.send("This server doesn't allow for manga release notifications.")
            return

        id = manga['id']

        if not await ctx.db.get_latest(id):
            releases = pymanga.releases(id)
            latest = "no chapters yet" if len(releases) < 1 else releases[0]['chapter']
            await ctx.db.set_latest(id,latest)

        await ctx.db.add_notification(ctx.author.id,id,ctx.guild.id)
        await ctx.send(f"You'll now be pinged for new releases of {manga['title']} ^~^")

        # (INTEGER 'manga', INTEGER 'user', INTEGER 'guild')

    @tasks.loop(minutes=15.0)
    async def loader(self):
        async with self.lock:
            await self.db.load_db()
            await self.cache.load_db()
            self.batch = iter((await self.db.get_notifications()).items())
            self.notifier.restart()

    @tasks.loop(seconds=5.0)
    async def notifier(self):
        async with self.lock:
            id,guilds = next(self.batch,(None,None))
            #                notifications[manga][guild].append(user)
            if id:
                releases = pymanga.releases(id)
                release = releases[0]
                latest = "no chapters yet" if len(releases) < 1 else releases[0]['chapter']
                cached_latest = ""

                cached_latest = await self.db.get_latest(id)
                if latest != cached_latest: # new chapter!
                    await self.db.set_latest(int(id),latest)

                    for guild,users in guilds.items():
                        guild_settings = await self.db.get_guild(guild)
                        if guild_settings['notify']:
                            manga = await self.cache.fetch_cached(id)
                            embed = discord.Embed(
                                title=f"**{manga['title']} - Chapter {latest}**",
                                description=f"Hey {', '.join([f'<@!{user}>' for user in users])}! There's a new chapter of {manga['title']} out.",
                                color=0xf77665)
                            embed.set_thumbnail(url=manga['image'])
                            embed.add_field(name="Scanlation Group", value=f"[{release['group']['name']}](https://www.mangaupdates.com/groups.html?id={release['group']['id']})" if 'id' in release['group'] else release['group']['name'], inline=False)

                            channel = await self.bot.fetch_channel(guild_settings['notify_channel'])
                            await channel.send(embed=embed)
            else:
                await self.db.close_db()
                await self.cache.close_db()
                self.notifier.stop()

def setup(bot):
    database = DatabaseCog(bot.config['internal']['db_path'])
    cache = get_cache(bot)
    bot.add_cog(NotifierCog(bot,database,cache))
