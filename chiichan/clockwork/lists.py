from discord.ext import commands, tasks
import discord
from discord import ChannelType
import pymanga
from .scrolling import ScrollingCog
from .utils import stars
import typing
from chiichan import Manga

class ListCog(commands.Cog):
    def __init__(self,bot):
        self.bot = bot

    @commands.group(name='lists',invoke_without_command=True)
    async def listsg(self,ctx,user: typing.Union[discord.Member,discord.User],*,list=None):
        async def gen_list_embed(ctx,res):
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

        if not list:
            lists = await ctx.db.get_lists(user.id)
            print(lists)
            if not lists:
                await ctx.send(f'{user.display_name} has no lists ):')
            else:
                await ctx.send(f'{user.display_name} has the following lists:')
                await ctx.send('\n'.join([f"-> {list}" for list in lists.keys()]))
        else:
            user_list = await ctx.db.get_list(user.id,list)
            if not user_list:
                await ctx.send(f'{user.display_name} has no such list ):')
            else:
                generator = (await ctx.cache.fetch_cached(id) for id in user_list)
                scrolling = ScrollingCog(self.bot,ctx,generator,gen_embed=gen_list_embed)
                await scrolling.scroll()

    @listsg.command(name='add')
    async def add_to_list(self,ctx,*,list):
        list = list.replace('\n','')

        await ctx.send("What manga do you want to add to this list?")

        msg = await self.bot.wait_for('message', check=lambda m: m.author.id == ctx.author.id and m.channel.id == ctx.channel.id)
        manga = await Manga().convert(ctx,msg.content)

        if not manga:
            return

        await ctx.db.add_to_list(ctx.author.id,list,manga['id'])

        await ctx.send(f"Added {manga['title']} to your list {list} ^^")

def setup(bot):
    bot.add_cog(ListCog(bot))
