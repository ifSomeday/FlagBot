import discord
from discord.ext import commands, tasks

class SupremeLeader(commands.Cog):

    def __init__(self, bot):

        self.channelId = 826314852619780166


    @commands.Cog.listener()
    async def on_message(self, msg):
        if(msg.channel.id == self.channelId):
            print("hi")
            target, text = msg.content.split(" ", 1)
            channel = await self.getCh(msg.guild, target)
            if(not channel is None):
                await channel.send(text)
                await msg.add_reaction('✅')
            else:
                await msg.add_reaction('❌')


    async def getCh(self, guild, channelName):
        result = discord.utils.get(guild.text_channels, name=channelName)
        if isinstance(result, discord.TextChannel):
            return(result)
        return(None)

def setup(bot):
    bot.add_cog(SupremeLeader(bot))
