from discord.ext import commands, tasks
import discord
from discord import ChannelType
import pymanga
import typing

class AdminCog(commands.Cog):
    def __init__(self,bot):
        self.bot = bot

    @commands.group()
    async def admin(self,ctx):
        pass

    @admin.group()
    async def notify(self,ctx):
        pass

    @notify.command(name='toggle')
    async def toggle_notify(self,ctx,on: bool):
        if ctx.author.permissions_in(ctx.message.channel).administrator:
            await ctx.db.set_notify(ctx.guild.id,on)
            await ctx.send(f"set manga release notifications for this server {'on' if on else 'off'} ^^")
        else:
            await ctx.send('only admins may use this command >.>')

    @notify.command(name='channel')
    async def set_channel(self,ctx,channel: discord.TextChannel):
        if ctx.author.permissions_in(ctx.message.channel).administrator:
            await ctx.db.set_notify_channel(ctx.guild.id,channel.id)
            await ctx.send(f'manga notifications for this server will now appear in {channel}!')
        else:
            await ctx.send('only admins may use this command >.>')

    @admin.command(name='help')
    async def adm_help(self,ctx,*args):
        if ctx.author.permissions_in(ctx.message.channel).administrator:
            await ctx.send(embed=discord.Embed(description=self.bot.help_descs['admin'].format(ctx=ctx), color=0xf77665))
        else:
            await ctx.send('only admins may use this command >.>')

def setup(bot):
    bot.add_cog(AdminCog(bot))
