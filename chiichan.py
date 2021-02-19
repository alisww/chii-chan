from discord.ext import commands
import discord
import asyncio
import re
import pymanga
import requests
import io
import configparser


config = configparser.ConfigParser()
config.read('chiichan.ini')
#
bot = commands.Bot(command_prefix=config['Discord'].get('prefix','$'))
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

    results_iter = (result_to_embed(res) for res in pymanga.advanced_search_iter(params))
    results = [next(results_iter,none_embed)]

    idx = 0
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
                    r = next(results_iter,None)
                    if r:
                        idx += 1
                        results.append(r)
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
                # removes reactions if the user tries to go forward on the last page or
                # backwards on the first page
        except asyncio.TimeoutError:
            break
            # ending the loop if user doesn't react after x seconds

@bot.command()
async def series(ctx, *, querystring):
    res = pymanga.search(querystring)['series']
    if len(res) > 0:
        manga = pymanga.series(res[0]['id'])
        embed = discord.Embed(title=manga['title'], url=f"https://www.mangaupdates.com/series.html?id={res[0]['id']}", description=manga['description'], color=0xf77665)

        embed.set_author(name=', '.join([a['name'] for a in manga['artists']]))
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
async def help(ctx,*args):
    h = ""
    if len(args) < 1:
        h = """
        **Available Commands**
        📚  series [manga name]
        🔎   search [query]
        ℹ️    help [command]

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
    elif args[0] == "search":
        h = f"""
        **{ctx.prefix}search [query]**
        searches manga by the specified attributes and returns a scrollable results list.
        *ex: {ctx.prefix}series genre:'Yuri, Shoujo Ai' exclude_genre:'Tragedy'*

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

bot.run(config['Discord']['token'])
