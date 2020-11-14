import discord
from discord.ext import commands

import keys

if __name__ == "__main__":

    ##set up client
    client = commands.Bot(command_prefix='!')

    @client.event
    async def on_ready():
        print("We have logged in as {0}".format(client.user))
        game = discord.Game("Korea Guild Bro")
        await client.change_presence(activity=game)

    client.load_extension("points")

    ##run bot
    client.run(keys.TOKEN)