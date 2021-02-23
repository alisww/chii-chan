from discord.ext import commands
import discord
import asyncio
from .utils import *

async def gen_search_embed(ctx,res):
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

    rating = await ctx.db.get_rating(res['id'])
    if rating:
        embed.add_field(name="Chii-chan's Rating",
         value=stars(rating), inline=True)

    embed.add_field(name="Genres", value=', '.join(res['genres']), inline=False)

    triggers = await ctx.db.get_triggers(res['id'])
    if triggers:
        triggers = '; '.join(triggers.keys())
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

    async def consume(self):
        try:
            r = await self.gen.asend(None)
        except StopAsyncIteration:
            return False

        while r:
            if not self.bot.config['filtered_genres'] & set([a.strip().lower() for a in r['genres']]):
                self.items.append(await self.gen_embed(self.ctx,r))
                break
            else:
                try:
                    r = await self.gen.asend(None)
                except StopAsyncIteration:
                    r = None
        if r:
            self.idx += 1
            return True
        else:
            return False

    async def scroll(self):
        if await self.consume():
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
                        await self.consume()
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
