from discord.ext import commands, tasks
from discord import ChannelType
from sqlitedict import SqliteDict
import discord, requests, toml, pymanga
import re, asyncio, io, typing, traceback, sys, statistics, json
import pymanga

config = {}
with open("chiichan.toml") as f:
    config = toml.load(f)

filtered_genres = set([g.lower() for g in config.get('filtering',{}).get('exclude_genres',[])])

internal = config.get('internal',{})

db = SqliteDict(internal.get('db_path','./chiichan.db'),encode=json.dumps,decode=json.loads)
# TODO: Add lock for db; move things like ratings to their own tables.

caching = internal.get('caching',False)
caching_interval = internal.get('caching_interval',6) # TODO: implement this

cache = SqliteDict(internal.get('cache_path','./chiichan_cache.db'),tablename='cache',encode=json.dumps,decode=json.loads)
cache_by_name = SqliteDict(internal.get('cache_path','./chiichan_cache.db'),tablename='cache_by_name',encode=json.dumps,decode=json.loads)

lists = SqliteDict(internal.get('lists_db_path','./chiichan_lists.db'),tablename='lists',encode=json.dumps,decode=json.loads)
lists_lock = asyncio.Lock()

triggersdb = SqliteDict(internal.get('tws_db_path','./chiichan_tws.db'),tablename='triggers',encode=json.dumps,decode=json.loads)
ratingsdb = SqliteDict(internal.get('ratings_db_path','./chiichan_ratings.db'),tablename='ratings',encode=json.dumps,decode=json.loads)

ratings_lock = asyncio.Lock()
triggers_lock = asyncio.Lock()

cache_lock = asyncio.Lock()
namecache_lock = asyncio.Lock()

# first init stuff
if 'manga' not in db:
    db['manga'] = {}
    db.commit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config['discord'].get('prefix','$'),intents=intents)
bot.remove_command("help")

async def fetch_cached(id):
    if caching:
        if id in cache:
            return cache[id]
        else:
            manga = pymanga.series(id)
            if manga:
                manga['id'] = id

                async with cache_lock:
                    cache[id] = manga
                    cache.commit()

                async with namecache_lock:
                    cache_by_name[manga['title']] = id
                    for name in manga['associated_names']:
                        cache_by_name[name] = id

                    cache_by_name.commit()
            return manga
    else:
        manga = pymanga.series(id)
        manga['id'] = id
        return manga

def fetch_cached_sync(id):
    if caching:
        if id in cache:
            return cache[id]
        else:
            manga = pymanga.series(id)
            if manga:
                manga['id'] = id

                cache[id] = manga
                cache.commit()

                cache_by_name[manga['title']] = id
                for name in manga['associated_names']:
                    cache_by_name[name] = id

                cache_by_name.commit()
            return manga
    else:
        manga = pymanga.series(id)
        manga['id'] = id
        return manga

async def cached_by_name(name):
    if caching:
        if name in cache_by_name:
            return await fetch_cached(cache_by_name[name])
        else:
            id = pymanga.search(name)['series'][0]['id']
            manga = pymanga.series(id)
            if manga:
                async with namecache_lock:
                    cache_by_name[manga['title']] = id

                    for name in manga['associated_names']:
                        cache_by_name[name] = id
                        cache_by_name.commit()

            return await fetch_cached(id)
    else:
        id = pymanga.search(name)['series'][0]['id']
        manga = pymanga.series(id)
        manga['id'] = id
        return manga

def stars(rating):
    rounded = round(rating*2)/2
    floored = int(rounded)
    return ('⭐' * floored) + ('✨' if rounded > floored else '')

class Manga(commands.Converter):
    async def convert(self, ctx, mangaid):
        manga = None

        if mangaid.isdecimal():
            manga = await fetch_cached(id)
        else:
            link_regex = re.compile(r"""mangaupdates\.com\/series\.html\?id=(\d+)""")
            m = link_regex.search(mangaid)
            if m:
                manga = await fetch_cached(m.group(1))
            else:
                manga = await cached_by_name(mangaid)

        if manga:
            if not filtered_genres & set([a.strip().lower() for a in manga['genres']]):
                desc = f"""
                **{manga['title']}**

                {manga['description'].strip().split(chr(10),1)[0] }

                *✅ to confirm*
                *❌ to reject*
                """
                embed = discord.Embed(title="Is this the manga you were looking for?", url=f"https://www.mangaupdates.com/series.html?id={manga['id']}",description=desc, color=0xf77665)
                embed.set_image(url=manga['image'])

                confirm_msg = await ctx.send(embed=embed)

                await confirm_msg.add_reaction("✅")
                await confirm_msg.add_reaction("❌")

                try:
                    reaction = await bot.wait_for("raw_reaction_add", timeout=60, check=lambda reaction: reaction.message_id == confirm_msg.id and reaction.user_id == ctx.author.id and str(reaction.emoji) in ["✅", "❌"])
                    user = await bot.fetch_user(reaction.user_id)
                    if reaction.emoji.name == "✅":
                        await confirm_msg.delete()
                        return manga
                    elif reaction.emoji.name == "❌":
                        await ctx.send("Aw ): Please try using the mangaupdates' link or id instead of title.")
                        await confirm_msg.delete()
                    else:
                        await confirm_msg.remove_reaction(reaction.emoji, user)
                except asyncio.TimeoutError:
                    await confirm_msg.delete()
            else:
                await ctx.send('This manga is part of a genre that is blocked in this server :/')
                await ctx.send("If you think i got the wrong manga, please try using the mangaupdates' link or id instead of title!")
        else:
            await ctx.send('Manga not found ):')

        return None


def gen_search_embed(res):
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

    if res['id'] in triggersdb:
        triggers = '; '.join(triggersdb[res['id']].keys())
        embed.add_field(name="User-submitted TWs",value='||'+triggers+'||',inline=False)

    return embed

class ScrollingCog(commands.Cog):
    def __init__(self, bot, ctx, gen, gen_embed=gen_search_embed):
        self.bot = bot
        self.ctx = ctx
        self.gen = gen
        self.idx = 0
        self.items = []
        self.gen_embed = gen_embed

    def consume(self):
        r = next(self.gen,None)
        while r:
            if not filtered_genres & set([a.strip().lower() for a in r['genres']]):
                self.items.append(self.gen_embed(r))
                break
            else:
                r = next(self.gen,None)
        if r:
            self.idx += 1
            return True
        else:
            return False

    async def scroll(self):
        if self.consume():
            self.idx -= 1
        else:
            await self.ctx.send(embed = discord.Embed(title='no results ):'))
            return

        message = await self.ctx.send(embed=self.items[0])
        # getting the message object for editing and reacting

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction):
            return reaction.message_id == message.id and reaction.user_id == self.ctx.author.id and str(reaction.emoji) in ["◀️","▶️"]
            # This makes sure nobody except the command sender can interact with the "menu"

        while True:
            try:
                reaction = await self.bot.wait_for("raw_reaction_add", timeout=60, check=check)
                user = await self.bot.fetch_user(reaction.user_id)
                # waiting for a reaction to be added - times out after x seconds, 60 in this
                # example

                if str(reaction.emoji) == "▶️":
                    if self.idx+1 > len(self.items)-1:
                        self.consume()
                    else:
                        self.idx += 1

                    await message.edit(embed=self.items[self.idx])
                    await message.remove_reaction(reaction.emoji, user)

                elif str(reaction.emoji) == "◀️" and self.idx > 0:
                    self.idx -= 1
                    await message.edit(embed=self.items[self.idx])
                    await message.remove_reaction(reaction.emoji, user)

                else:
                    await message.remove_reaction(reaction.emoji, user)
            except asyncio.TimeoutError:
                break
                # ending the loop if user doesn't react after x seconds

@bot.listen()
async def on_command_error(ctx,exception):
    traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)
    if isinstance(exception, commands.errors.MissingRequiredArgument):
        if ctx.invoked_with == "lists":
            await ctx.send('Invalid usage of command :/')
            h = f"""Usage:
**{ctx.prefix}lists [user]**
shows [user]'s lists

**{ctx.prefix}lists [user] [list name]**
shows a [user]'s list.

**{ctx.prefix}lists add [list name]**
adds a manga to [list name]. creates list if it doesn't exist yet
            """
            await ctx.send(h)
        elif invoked_command == "tw":
            await ctx.send('Invalid usage of command :/')
            h = f"""
            **{ctx.prefix}tw show [manga name | mangaupdates link]**
            see trigger warnings submitted for this manga by other users. (p.s: the triggers are spoilered. you can also use this command in a dm with this bot.)

            **{ctx.prefix}tw add [manga name | mangaupdates link]**
            submit trigger warnings for this manga. (p.s: you can also use this command in a dm with this bot.)

            *ex: {ctx.prefix}tw show Still Sick*
            *or: {ctx.prefix}tw show https://www.mangaupdates.com/series.html?id=148031*

            *ex: {ctx.prefix}tw add Still Sick*
            *or: {ctx.prefix}tw add https://www.mangaupdates.com/series.html?id=148031*
            """
            await ctx.send(h)
        else:
            await ctx.send('Please specify a manga :c')


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

    if 'name' not in params and 'title' in params:
        params['name'] = params['title']

    if 'name' not in params and 'orderby' not in params:
        params['orderby'] = 'rating'


    scroll = ScrollingCog(bot,ctx,pymanga.advanced_search_iter(params))
    await scroll.scroll()

@bot.command()
async def series(ctx, *, querystring):
    manga = await cached_by_name(querystring)
    if manga:
        id = manga['id']

        embed = discord.Embed(title=manga['title'], url=f"https://www.mangaupdates.com/series.html?id={manga['id']}",
         description=manga['description'].strip().split("\n",1)[0],
         color=0xf77665)

        embed.set_author(name=', '.join([a['name'] for a in manga['authors']]))
        embed.set_image(url=manga['image'])

        embed.add_field(name="Genres", value=', '.join(manga['genres']), inline=False)

        embed.add_field(name="Type", value=manga['type'], inline=True)
        embed.add_field(name="Year", value=manga['year'], inline=True)
        embed.add_field(name="Status", value=manga['status'], inline=True)

        # if manga['associated_names']:
        #     associated_names = manga['associated_names']
        #     if len(associated_names) > 4:
        #         associated_names = associated_names[:4] + ['...and more!']
        #     embed.add_field(name="Also known as",
        #     value=''.join(associated_names),
        #     inline=True)

        if manga['related_series']:
            related = manga['related_series']
            if len(related) > 2:
                related  = related[:2] + ['...and more!']

            related = '\n'.join([f"[{r_s['name']} *({r_s['relation']})*](https://www.mangaupdates.com/series.html?id={r_s['id']})" for r_s in related])

            embed.add_field(name="Related series",
            value=related,
            inline=False)

        if manga['anime_chapters']:
            anime_chapters = manga['anime_chapters']
            anime_chapters[0] = anime_chapters[0][0].lower() + anime_chapters[0][1:]
            anime_chapters[1] = anime_chapters[1][0].lower() + anime_chapters[1][1:]
            embed.add_field(name="Anime",
            value="*This manga has an anime adaptation!*\n It " +  ' and '.join(anime_chapters),
            inline=False)

        if manga['average']:
            embed.add_field(name="MangaUpdates' Rating",
             value=manga['average']['average'], inline=True)

        if id in ratingsdb and ratingsdb[id] != {}:
            embed.add_field(name="Chii-chan's Rating",
             value=stars(ratingsdb[id]['average']), inline=True)

        if id in triggersdb:
            triggers = '; '.join(triggersdb[id].keys())
            embed.add_field(name="User-submitted TWs",value='||'+triggers+'||',inline=False)


        await ctx.send(embed=embed)
    else:
        await ctx.send(embed=discord.Embed(title='no results ):'))

@bot.command()
async def subscribe(ctx,*,manga: Manga):
    if not manga:
        return

    if not db[ctx.guild.id]['notify']:
        await ctx.send("This server doesn't allow for manga release notifications.")
        return

    id = manga['id']

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

    await ctx.send(f"You'll now be pinged for new releases of {manga['title']} ^~^")

@bot.command()
async def rate(ctx,*,manga: Manga):
    if not manga:
        return

    number_regex = re.compile(r"""(?P<rating>[\d]+(?:\.(\d+)?)?)(?:\/(?P<base>\d+))?""") # group 'rating': matches number + optional decimal places; group 'base': matches /(integer)
    async def convert_rating(rating):
        m = number_regex.match(rating)
        if m:
            groups = m.groupdict()
            base = int(groups['base']) if groups['base'] else 5
            r = float(groups['rating'])

            if r > base:
                await ctx.send('invalid rating :/')
                return None

            return (r / base) * 5
        else:
            await ctx.send('invalid rating :/')
            return None

    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and number_regex.search(m.content) != None

    question = await ctx.send("How do you rate this manga? *(ratings are 5 Point Decimal, ex. 4.3/5)*")

    try:
        msg = await bot.wait_for('message', check=check)
        rating = await convert_rating(msg.content)

        id = manga['id']
        if id not in db:
            ratingsdb[id] = {'users':{}}

        async with ratings_lock:
            ratings = ratingsdb[id]
            ratings['users'][ctx.author.id] = rating

            ratings['users'] = dict(sorted(ratings['users'].items(), key=lambda item: item[1]))
            rating_vals = ratings['users'].values()
            ratings['average'] = statistics.fmean(rating_vals)
            ratings['median'] = statistics.median(rating_vals)

            ratingsdb[id] = ratings
            ratingsdb.commit()

        await ctx.send(f"rating submitted ;)")
        await ctx.send(f"the average rating for {manga['title']} is now {ratings['average']:.1f}/5")

    except asyncio.TimeoutError:
        await question.delete()

    if not manga:
        return

@bot.group()
async def tw(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send('Invalid usage of command :/')
        h = f"""
**{ctx.prefix}tw show [manga name | mangaupdates link]**
see trigger warnings submitted for this manga by other users. (p.s: the triggers are spoilered. you can also use this command in a dm with this bot.)

**{ctx.prefix}tw add [manga name | mangaupdates link]**
submit trigger warnings for this manga. (p.s: you can also use this command in a dm with this bot.)

*ex: {ctx.prefix}tw show Still Sick*
*or: {ctx.prefix}tw show <https://www.mangaupdates.com/series.html?id=148031>*

*ex: {ctx.prefix}tw add Still Sick*
*or: {ctx.prefix}tw add <https://www.mangaupdates.com/series.html?id=148031>*
        """
        await ctx.send(h)

@tw.command(name="show")
async def get_triggers(ctx,*,manga: Manga):
    if not manga:
        return

    id = manga['id']
    if not id in triggersdb:
        await ctx.send("No one has added trigger warnings for this manga yet.")
        return

    triggers = triggersdb[id]
    await ctx.send("people have added the following trigger warnings for this manga:")

    msg = "||"
    for t,users in triggers.items():
        msg += f"{t} *({len(users)} {'user' if len(users) == 1 else 'users'})*" + '\n'
    msg += "||"
    await ctx.send(msg)

@tw.command(name="add")
async def add_triggers(ctx,*,manga: typing.Optional[Manga]):
    if not manga:
        return

    id = manga['id']
    if id not in triggersdb:
        triggersdb[id] = {}

    warnings = triggersdb[id]
    question = await ctx.send("What trigger warnings would you like to add to this manga? (*separate multiple warnings using ';'.*)\n*p.s: please spoiler your message if you're in a server!*")

    try:
        msg = await bot.wait_for('message', check=lambda m: m.author.id == ctx.author.id and m.channel.id == ctx.channel.id)
        async with triggers_lock:
            for trigger in (warning.strip() for warning in msg.content.replace('||','').split(';')):
                if trigger not in warnings:
                    warnings[trigger] = []

                if ctx.author.id not in warnings[trigger]:
                    warnings[trigger].append(ctx.author.id)

        channel = await bot.fetch_channel(msg.channel.id)
        if channel.type != ChannelType.private and channel.type != ChannelType.group:
            await msg.delete()
    except asyncio.TimeoutError:
        await question.delete()

    async with triggers_lock:
        triggersdb[id] = warnings
        triggersdb.commit()
    await ctx.send("trigger warnings added to database. thank you for submitting them :)")

@bot.group(name='lists',invoke_without_command=True)
async def listsg(ctx,user: typing.Union[discord.Member,discord.User],*,list=None):
    def gen_list_embed(res):
        embed = discord.Embed(
            title=f"{user.display_name}'s {list} list",
            description=f"[**{res['title']}**](https://www.mangaupdates.com/series.html?id={res['id']})\n" + res['description'].split('\n',1)[0],
            color=0xff7474
        )

        if res.get('image',False):
            embed.set_thumbnail(url=res['image'])

        if res.get('year',False):
            embed.add_field(name="Year", value=res['year'], inline=True)

        if res.get('average',{}).get('average',False):
            embed.add_field(name="MangaUpdates' Rating", value=res['average']['average'], inline=True)

        embed.add_field(name="Genres", value=', '.join(res['genres']), inline=False)

        if res['id'] in triggersdb:
            triggers = '; '.join(triggersdb[res['id']].keys())
            embed.add_field(name="User-submitted TWs",value='||'+triggers+'||',inline=False)

        return embed

    if user.id not in lists:
        await ctx.send(f'{user.display_name} has no lists ):')
        return

    user_lists = lists[user.id]

    if not list:
        await ctx.send(f'{user.display_name} has the following lists:')
        await ctx.send('\n'.join([f"-> {list}" for list in user_lists.keys()]))
        return

    if list not in user_lists:
        await ctx.send(f'{user.display_name} has no such list ):')
        return

    generator = (fetch_cached_sync(id) for id in user_lists[list])
    scrolling = ScrollingCog(bot,ctx,generator,gen_embed=gen_list_embed)
    await scrolling.scroll()

@listsg.command(name='add')
async def add_to_list(ctx,*,list):
    list = list.replace('\n','')

    if ctx.author.id not in lists:
        async with lists_lock:
            print("hi")
            lists[ctx.author.id] = {}
            lists.commit()


    if list not in lists[ctx.author.id]:
        async with lists_lock:
            user_lists = lists[ctx.author.id]
            user_lists[list] = []
            lists[ctx.author.id] = user_lists
            lists.commit()


    await ctx.send("What manga do you want to add to this list?")

    msg = await bot.wait_for('message', check=lambda m: m.author.id == ctx.author.id and m.channel.id == ctx.channel.id)
    manga = await Manga().convert(ctx,msg.content)

    if not manga:
        return

    async with lists_lock:
        user_lists = lists[ctx.author.id]
        user_lists[list].append(manga['id'])
        lists[ctx.author.id] = user_lists
        lists.commit()

    await ctx.send(f"Added {manga['title']} to your list {list} ^^")

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

🗞️ |        **{ctx.prefix}subscribe [manga name | mangaupdates link]**
                -> get pinged whenever a new chapter of a manga series comes out!

⭐ |        **{ctx.prefix}rate [manga name | mangaupdates link]**
                -> submit a rating for a manga!

🔖 |        **{ctx.prefix}lists [user]**
                -> shows [user]'s lists
                *(users may be a nickname, a username, or username#tag)*

🔖 |        **{ctx.prefix}lists [user] [list name]**
                -> shows a [user]'s list.
                *(users may be a nickname, a username, or username#tag)*

🔖 |        **{ctx.prefix}lists add [list name]**
                -> adds a manga to [list name]. creates list if it doesn't exist yet

⚠️ |        **{ctx.prefix}tw show [manga name | mangaupdates link]**
                -> see trigger warnings submitted for this manga by other users. (p.s: the triggers are spoilered. you can also use this command in a dm with this bot.)

⚠️ |        **{ctx.prefix}tw add [manga name | mangaupdates link]**
                -> submit trigger warnings for this manga. (p.s: you can also use this command in a dm with this bot.)

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
    elif 'lists' in args[0]:
        h = f"""
        🔖 |        **{ctx.prefix}lists [user]**
                        -> shows [user]'s lists
                        *(users may be a nickname, a username, or username#tag)*

        🔖 |        **{ctx.prefix}lists [user] [list name]**
                        -> shows a [user]'s list.
                        *(users may be a nickname, a username, or username#tag)*

        🔖 |        **{ctx.prefix}lists add [list name]**
                        -> adds a manga to [list name]. creates list if it doesn't exist yet
        """
    elif 'tw' in args[0]:
        h = f"""
⚠️ |     **{ctx.prefix}tw show [manga name | mangaupdates link]**
        see trigger warnings submitted for this manga by other users. (p.s: the triggers are spoilered. you can also use this command in a dm with this bot.)

⚠️ |     **{ctx.prefix}tw add [manga name | mangaupdates link]**
        submit trigger warnings for this manga. (p.s: you can also use this command in a dm with this bot.)

        *ex: {ctx.prefix}tw show Still Sick*
        *or: {ctx.prefix}tw show https://www.mangaupdates.com/series.html?id=148031*

        *ex: {ctx.prefix}tw add Still Sick*
        *or: {ctx.prefix}tw add https://www.mangaupdates.com/series.html?id=148031*
        """
    elif args[0] == "rate":
        h = f"""
        **{ctx.prefix}rate [manga name | mangaupdates link | mangaupdates id]**
        submit a rating for a manga.

        *ex: {ctx.prefix}rate Still Sick*
        *or: {ctx.prefix}subscribe https://www.mangaupdates.com/series.html?id=148031*
        """
    elif args[0] == "search":
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

@bot.command()
async def changelog(ctx):
    h = f"""
    we have lists now. so you can share you favourites, your recommendations and your 'never read this; my eyes are bleeding!' series.

    🔖 |        **{ctx.prefix}lists [user]**
                    -> shows [user]'s lists
                    *(users may be a nickname, a username, or username#tag)*

    🔖 |        **{ctx.prefix}lists [user] [list name]**
                    -> shows a [user]'s list.
                    *(users may be a nickname, a username, or username#tag)*

    🔖 |        **{ctx.prefix}lists add [list name]**
                    -> adds a manga to [list name]. creates list if it doesn't exist yet
    """
    embed=discord.Embed(title="The Lists Update",description=h, color=0xf77665)
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
