import discord
from discord.ext import commands

import config

if __name__ == "__main__":

    ##set up client
    intents = discord.Intents.default()
    intents.members = True
    client = commands.Bot(command_prefix='!')

    @client.event
    async def on_ready():
        print("We have logged in as {0}".format(client.user))
        game = discord.Game("Korea Guild Bro")
        await client.change_presence(activity=game)

    ## Points Tracker
    client.load_extension("points")
    client.load_extension("serverChecker")
    client.load_extension("db")
    client.load_extension("flames")
    client.load_extension("supremeLeader")

    ## GPQ Tracker
    if(not config.GPQ_SHEET_ID == None):
        client.load_extension("gpq")

    ## Piggy Bank Tracker
    if(not config.PB_SHEET_ID == None):
        client.load_extension("piggybank")

    ##run bot
    client.run(config.TOKEN)
