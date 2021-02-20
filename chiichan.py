from discord.ext import commands, tasks
import discord
import asyncio
import re
import pymanga
import requests
import io
import toml
import typing
from sqlitedict import SqliteDict

config = {}
with open("chiichan.toml") as f:
    config = toml.load(f)

filtered_genres = set([g.lower() for g in config.get('filtering',{}).get('exclude_genres',[])])

db = SqliteDict(config.get('internal',{}).get('db_path','./chiichan.db'))

# first init stuff
if 'manga' not in db:
    db['manga'] = {}
    db.commit()

#
bot = commands.Bot(command_prefix=config['discord'].get('prefix','$'))
bot.remove_command("help")

@bot.command()
async def search(ctx, *, querystring):
    params = {}
    for arg in re.finditer(r"""(.+?):(?:(?:['"](?P<quotedarg>.+?)['"])|(?P<arg>[^\s]+?(?:\s|$){1}))""",querystring):
        groups = arg.groupdict()
        field = arg.group(1).strip()

        param = groups['quotedarg'] if groups['quotedarg'] else groups['arg']
        param = [a.strip() for a in param.split(',')]

        if field == 'genre' or field == 'category' or field == 'exclude_genre':
            if field not in params:
                params[field] = []
            if field == 'genre':
                params[field] = params[field] + [genre for genre in param if not set([genre.strip().lower()]) & filtered_genres]
            else:
                params[field] = params[field] + param
        else:
            params[field] = param[0]

    def result_to_embed(res):
        embed = discord.Embed(
            title=res['name'],
            url=f"https://www.mangaupdates.com/series.html?id={res['id']}",
            description=res['summary'],
            color=0xff7474
        )

        if res.get('thumbnail',False):
            embed.set_thumbnail(url=res['thumbnail'])

        if res.get('year',False):
            embed.add_field(name="Year", value=res['year'], inline=True)

        if res.get('rating',False):
            embed.add_field(name="Rating", value=res['rating'], inline=True)

        embed.add_field(name="Genres", value=', '.join(res['genres']), inline=False)

        return embed

    none_embed = discord.Embed(title='no results ):')

    idx = 0

    results_iter = pymanga.advanced_search_iter(params)
    results = []

    def consume():
        r = next(results_iter,None)
        while r:
            if not filtered_genres & set([a.strip().lower() for a in r['genres']]):
                results.append(result_to_embed(r))
                break
            else:
                r = next(results_iter,None)
        if r:
            return 1
        else:
            return 0

    consume()

    message = await ctx.send(embed=results[0])
    # getting the message object for editing and reacting

    await message.add_reaction("◀️")
    await message.add_reaction("▶️")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"]
        # This makes sure nobody except the command sender can interact with the "menu"


    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60, check=check)
            # waiting for a reaction to be added - times out after x seconds, 60 in this
            # example

            if str(reaction.emoji) == "▶️":
                if idx+1 > len(results)-1:
                    idx += consume()
                else:
                    idx += 1

                await message.edit(embed=results[idx])
                await message.remove_reaction(reaction, user)

            elif str(reaction.emoji) == "◀️" and idx > 0:
                idx -= 1
                await message.edit(embed=results[idx])
                await message.remove_reaction(reaction, user)

            else:
                await message.remove_reaction(reaction, user)
        except asyncio.TimeoutError:
            break
            # ending the loop if user doesn't react after x seconds

@bot.command()
async def series(ctx, *, querystring):
    res = pymanga.search(querystring)['series']
    if len(res) > 0:
        manga = pymanga.series(res[0]['id'])
        embed = discord.Embed(title=manga['title'], url=f"https://www.mangaupdates.com/series.html?id={res[0]['id']}", description=manga['description'].split("[**M**ore...]")[0], color=0xf77665)

        embed.set_author(name=', '.join([a['name'] for a in manga['authors']]))
        embed.set_image(url=manga['image'])

        embed.add_field(name="Genres", value=', '.join(manga['genres']), inline=False)

        embed.add_field(name="Type", value=manga['type'], inline=True)
        embed.add_field(name="Year", value=manga['year'], inline=True)
        embed.add_field(name="Status", value=manga['status'], inline=True)

        if manga['average']:
            embed.add_field(name="Rating", value=manga['average']['average'], inline=True)

        if manga['associated_names']:
            embed.add_field(name="Also known as",value='\n'.join(manga['associated_names']))
        if manga['related_series']:
            embed.add_field(name="Related series",value='\n'.join(manga['related_series']))

        await ctx.send(embed=embed)
    else:
        await ctx.send(embed=discord.Embed(title='no results ):'))

@bot.command()
async def subscribe(ctx,*,mangaid):
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"]

    if not db[ctx.guild.id]['notify']:
        await ctx.send("This server doesn't allow for manga release notifications.")
        return

    id = ''

    if mangaid.isdecimal():
        id = mangaid
    else:
        link_regex = re.compile(r"""mangaupdates\.com\/series\.html\?id=(\d+)""")
        m = link_regex.search(mangaid)
        id = m.group(1) if m else pymanga.search(mangaid)['series'][0]['id']

    manga = pymanga.series(id)
    if series:
        if not filtered_genres & set([a.strip().lower() for a in manga['genres']]):
            desc = f"""
            **{manga['title']}**

            {manga['description'].split(chr(10),1)[0] }

            *✅ to confirm*
            *❌ to reject*
            """
            embed = discord.Embed(title="Is this the manga you want to subscribe to?", url=f"https://www.mangaupdates.com/series.html?id={id}",description=desc, color=0xf77665)
            embed.set_image(url=manga['image'])

            confirm_msg = await ctx.send(embed=embed)

            await confirm_msg.add_reaction("✅")
            await confirm_msg.add_reaction("❌")

            try:
                reaction, user = await bot.wait_for("reaction_add", timeout=60, check=check)
                if reaction.emoji == "✅":
                    await ctx.send(f"You'll now be pinged for new releases of {manga['title']} ^~^")

                    manga_list = db['manga']

                    if id not in manga_list:
                        releases = pymanga.releases(id)
                        latest = "no chapters yet" if len(releases) < 1 else releases[0]['chapter']
                        manga_list[id] = {'title': manga['title'],'description': manga['description'],'image': manga['image'], 'latest': latest,'guilds':{}}


                    if ctx.guild.id not in manga_list[id]['guilds']:
                        manga_list[id]['guilds'][ctx.guild.id] = []

                    manga_list[id]['guilds'][ctx.guild.id].append(ctx.author.id)

                    db['manga'] = manga_list
                    db.commit()

                    await confirm_msg.delete()

                elif reaction.emoji == "❌":
                    await ctx.send("Aw ): Please try subscribing using the mangaupdates' link or id instead of title.")

                    await confirm_msg.delete()
                else:
                    await confirm_msg.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await confirm_msg.delete()
        else:
            await ctx.send('This manga is part of a genre that is blocked in this server :/')
    else:
        await ctx.send('Manga not found ):')


@bot.command(name='admin:notify->toggle')
async def toggle_notify(ctx,on: typing.Optional[bool] = None):
    if ctx.author.permissions_in(ctx.message.channel).administrator:
        if ctx.guild.id not in db:
            db[ctx.guild.id] = {'notify': False,'channel':0,'manga':[]}

        guild = db[ctx.guild.id]

        if on != None:
            guild['notify'] = on
        else:
            guild['notify'] = not guild['notify']

        db[ctx.guild.id] = guild
        db.commit()

        await ctx.send(f"set manga release notifications for this server {'on' if db[ctx.guild.id]['notify'] else 'off'} ^^")
    else:
        await ctx.send('only admins may use this command >.>')

@bot.command(name='admin:notify->channel')
async def set_channel(ctx,channel: discord.TextChannel):
    if ctx.author.permissions_in(ctx.message.channel).administrator:
        if ctx.guild.id not in db:
            db[ctx.guild.id] = {'notify': False,'channel':0}

        guild = db[ctx.guild.id]
        guild['channel'] = channel.id

        db[ctx.guild.id] = guild
        db.commit()

        await ctx.send(f'manga notifications for this server will now appear in {channel}!')
    else:
        await ctx.send('only admins may use this command >.>')

@bot.command(name='admin:help')
async def adm_help(ctx,*args):
    if ctx.author.permissions_in(ctx.message.channel).administrator:
        h = f"""
**Available Commands**
```make
{ctx.prefix}admin:notify->toggle [on|off]
    -> disables or enables manga release notifications in this server

{ctx.prefix}admin:notify->channel [#channel]
    -> sets channel where release notifications will apear

{ctx.prefix}admin:help
    -> this command!
```
*if you need any help or have any issues, dm allie at sapphicfettucine#6248!*
"""

        await ctx.send(h)
    else:
        await ctx.send('only admins may use this command >.>')

@bot.command()
async def help(ctx,*args):
    h = ""
    if len(args) < 1:
        h = f"""
        **Available Commands**

📚 |        **{ctx.prefix}series [manga name]**
                -> get details for manga series in a neat embed

🔎 |        **{ctx.prefix}search [query]**
                -> searches manga by the specified attributes and returns a scrollable results list.

🗞️ |        **{ctx.prefix}subscribe [manga]**
                -> get pinged whenever a new chapter of a manga series comes out!

ℹ️ |        **{ctx.prefix}help [command]**
                -> shows how to use a command

🚫 |        **{ctx.prefix}admin:help**
                -> this command, but for our dear mods

        *made by allie (at sapphicfettucine#6248 or on [cat-girl.gay](https://cat-girl.gay))*
        *using [mangaupdates.com](https://mangaupdates.com)*
        *source code on [github.com/alisww/chii-chan](https://github.com/alisww/chii-chan)*
        *profile picture and name borrowed from Girl's Last Tour*
        """
    elif args[0] == "series":
        h = f"""
        **{ctx.prefix}series [manga name]**
        searches manga by the specified name and returns the top result in a neat embed.
        *ex: {ctx.prefix}series Still Sick*
        """
    elif args[0] == "subscribe":
        h = f"""
        **{ctx.prefix}subscribe [manga name | mangaupdates link | mangaupdates id]**
        pings you whenever a new chapter of a manga comes out.

        *ex: {ctx.prefix}subscribe Still Sick*
        *or: {ctx.prefix}subscribe https://www.mangaupdates.com/series.html?id=148031*
        """
    elif args[0] == "search":
        genre_list = ['Action','A']
        h = f"""
        **{ctx.prefix}search [query]**
        searches manga by the specified attributes and returns a scrollable results list.
        *ex: {ctx.prefix}search orderby:rating genre:'Yuri, Shoujo Ai' exclude_genre:'Tragedy'*

        **Available Search Attributes**
        *orderby* -> 'title', 'rating' or 'year'; determines how the results are sorted
        *name* -> search by the manga name
        *category* -> categories to search in. [find a list of categories here](https://www.mangaupdates.com/categories.html)
        *genre* -> genres to search in
        *exclude_genre* -> genres to exclude in search results

        **Available Genres**
          - Action
          - Adult
          - Adventure
          - Comedy
          - Doujinshi
          - Drama
          - Ecchi
          - Fantasy
          - Gender Bender
          - Harem
          - Historical
          - Horror
          - Josei
          - Martial Arts
          - Mature
          - Mecha
          - Mystery
          - Psychological
          - Romance
          - School Life
          - Sci-fi
          - Seinen
          - Shoujo
          - Shoujo Ai
          - Shounen
          - Shounen Ai
          - Slice of Life
          - Sports
          - Supernatural
          - Tragedy
          - Yaoi
          - Yuri
        """

    embed=discord.Embed(description=h, color=0xf77665)
    await ctx.send(embed=embed)

class NotifierCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.batch = iter(db['manga'].items())
        self.loader.start()
        self.notifier.start()

    @tasks.loop(minutes=15.0)
    async def loader(self):
        async with self.lock:
            self.batch = iter(db['manga'].items())
        self.notifier.restart()

    @tasks.loop(seconds=5.0)
    async def notifier(self):
        id,manga = next(self.batch,(None,None))
        if manga:
            releases = pymanga.releases(id)
            latest = "no chapters yet" if len(releases) < 1 else releases[0]['chapter']
            if manga['latest'] != latest: # new chapter!
                release = releases[0]

                manga_list = db['manga']
                manga_list[id]['latest'] = release['chapter']
                db['manga'] = manga_list
                db.commit()

                for guild,users in manga['guilds'].items():
                    if db[guild]['notify']:
                        embed = discord.Embed(
                            title=f"**{manga['title']} - Chapter {latest}**",
                            description=f"Hey {', '.join([f'<@!{user}>' for user in users])}! There's a new chapter of {manga['title']} out.",
                            color=0xf77665)
                        embed.set_thumbnail(url=manga['image'])
                        embed.add_field(name="Scanlation Group", value=f"[{release['group']['name']}](https://www.mangaupdates.com/groups.html?id={release['group']['id']})" if 'id' in release['group'] else release['group']['name'], inline=False)

                        channel = await self.bot.fetch_channel(db[guild]['channel'])
                        await channel.send(embed=embed)
            else:
                return
        else:
            self.notifier.stop()

bot.add_cog(NotifierCog(bot))
bot.run(config['discord']['token'])
