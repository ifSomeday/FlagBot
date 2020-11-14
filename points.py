from __future__ import print_function

import discord
from discord.ext import commands

import asyncio
import pickle
import os

from apiclient import discovery
from google.oauth2 import service_account

import keys

class Points(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.trackChannel = 0

        self.fileLock = asyncio.Lock()
        self.filePath = "trackChannel.pickle"

        self.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        self.spreadsheetId = "19pcMuokGHeXr-NBRQNXn4Mrr9u858jTdzcxIVI0ayXg"
        self.sheet = None

        self.loadChannel()
        self.loadSheets()

        print("Currently tracking points in channel id: {0}".format(self.trackChannel))


    ## updates the channel to track points in
    @commands.command()
    async def trackChannel(self, ctx, ch : discord.TextChannel):
        await self.updateChannel(ch.id)
        print(self.trackChannel)


    @commands.Cog.listener()
    async def on_message(self, msg):
        if(msg.channel.id == self.trackChannel):
            pts = 0
            try:
                pts = int(msg.clean_content)
            except:
                await msg.add_reaction('❌')
                await msg.author.send("I was unable to parse your message: `{0}`.\nPlease only send the amount of points you earned and nothing else.".format(msg.clean_content))
                return

            if(await self.addToSheet(msg.author, pts)):
                await msg.add_reaction('✅')
            else:
                await msg.add_reaction('❌')
                await msg.author.send("Unknown error occurred. Try again in several minutes or contact Will.")

    async def addToSheet(self, name, points):
        return(False)

    ## updates the trackChannel and saves to pickle, all under lock
    async def updateChannel(self, channelId):
        async with self.fileLock:
            self.trackChannel = channelId
            with open(self.filePath, "wb") as f:
                pickle.dump(self.trackChannel, f)

    ## Not under lock because we only call this in init
    def loadChannel(self):
        if os.path.exists(self.filePath):
            with open(self.filePath, "rb") as f:
                self.trackChannel = pickle.load(f)

    ## Load Sheets with service account
    def loadSheets(self):
        credFile = os.path.join(os.getcwd(), keys.CRED_FILE)
        creds = service_account.Credentials.from_service_account_file(credFile, scopes=self.scopes)
        service = discovery.build('sheets', 'v4', credentials=creds)
        self.sheet = service.spreadsheets()




def setup(bot):
    bot.add_cog(Points(bot))