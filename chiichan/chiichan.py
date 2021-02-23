from discord.ext import commands, tasks
from discord import ChannelType
from sqlitedict import SqliteDict
import discord, requests, toml, pymanga
import re, asyncio, io, typing, traceback, sys, statistics, json
import pymanga
from clockwork import *
from clockwork.scrolling import *
from clockwork.utils import *

config = {}
with open("chiichan.toml") as f:
    config = toml.load(f)


config['internal'] = config.get('internal',{})

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config['discord'].get('prefix','$'),intents=intents)
bot.remove_command("help")
bot.config = config
bot.config['filtered_genres'] = set([g.lower() for g in config.get('filtering',{}).get('exclude_genres',[])])
filtered_genres = bot.config['filtered_genres']

class Manga(commands.Converter):
    async def convert(self, ctx, mangaid):
        manga = None
        ctx.cache = bot.get_cog('cache')

        if mangaid.isdecimal():
            manga = await ctx.cached.fetch_cached(id)
        else:
            link_regex = re.compile(r"""mangaupdates\.com\/series\.html\?id=(\d+)""")
            m = link_regex.search(mangaid)
            if m:
                manga = await ctx.cache.fetch_cached(m.group(1))
            else:
                manga = await ctx.cache.fetch_by_name(mangaid)

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

@bot.listen('on_ready')
async def load_dbs():
    await bot.get_cog('DatabaseCog').load_db()
    await bot.get_cog('cache').load_db()

@bot.before_invoke
async def before_invoke_loads(ctx):
    ctx.db = bot.get_cog('DatabaseCog')
    ctx.cache = bot.get_cog('cache')

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

    async def async_search_iter(iter):
        for val in iter:
            yield val

    scroll = ScrollingCog(bot,ctx,async_search_iter(pymanga.advanced_search_iter(params)))
    await scroll.scroll()

@bot.command()
async def series(ctx, *, querystring):
    manga = await ctx.cache.fetch_by_name(querystring)
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

        rating = await ctx.db.get_rating(manga['id'])
        if rating:
            embed.add_field(name="Chii-chan's Rating",
             value=stars(rating), inline=True)

        triggers = await ctx.db.get_triggers(manga['id'])
        if triggers:
            triggers = '; '.join(triggers.keys())
            embed.add_field(name="User-submitted TWs",value='||'+triggers+'||',inline=False)


        await ctx.send(embed=embed)
    else:
        await ctx.send(embed=discord.Embed(title='no results ):'))

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

        await ctx.db.set_rating(manga['id'],rating,ctx.author.id)

        new_rating = await ctx.db.get_rating(manga['id'])

        await ctx.send(f"rating submitted ;)")
        await ctx.send(f"the average rating for {manga['title']} is now {new_rating:.1f}/5")

    except asyncio.TimeoutError:
        await question.delete()

    if not manga:
        return

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

bot.load_extension('clockwork.cache')
bot.load_extension('clockwork.db')
bot.load_extension('clockwork.tws')
bot.load_extension('clockwork.lists')
bot.load_extension('clockwork.notifier')
bot.load_extension('clockwork.admin')
bot.run(config['discord']['token'])
