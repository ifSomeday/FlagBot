from inspect import trace
import discord
from discord.ext import commands
import logging

import asyncio
import traceback
import config

if __name__ == "__main__":

    ##set up client
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    client = commands.Bot(command_prefix='!', intents=intents)
    #discord.utils.setup_logging(level=logging.DEBUG, root=False)

    @client.event
    async def on_ready():
        print("We have logged in as {0}".format(client.user))
        game = discord.Game("Korea Guild Bro")
        await client.change_presence(activity=game)

        print(client.tree.get_commands())

        try:
            guild = client.get_guild(config.GPQ_GUILD)
            ret = await client.tree.sync(guild=guild)
            print(f"sync ret {ret}")
            print(await client.tree.fetch_commands(guild=guild))
        except Exception as e:
            print(f"sync error {e}")
            print(traceback.print_exc())


    @client.event
    async def setup_hook():
        print("setup hook")

    async def main():
        async with client:
            await client.load_extension("serverChecker")
            #await client.load_extension("tracker")
            await client.load_extension("gpqSync")
            await client.load_extension("gpq")
           
            await client.start(config.TOKEN)


    ##run bot
    asyncio.run(main())
