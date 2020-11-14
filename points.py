from __future__ import print_function

import discord
from discord.ext import commands

import asyncio
import pickle
import os

from apiclient import discovery
from google.oauth2 import service_account

import config

class Points(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.trackChannel = 0

        self.fileLock = asyncio.Lock()
        self.filePath = "trackChannel.pickle"

        self.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        self.spreadsheetId = config.SHEET_ID
        self.sheet = None
        self.currentPageId = 548441837
        self.currentPageName = "11/16"

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
        credFile = os.path.join(os.getcwd(), config.CRED_FILE)
        creds = service_account.Credentials.from_service_account_file(credFile, scopes=self.scopes)
        service = discovery.build('sheets', 'v4', credentials=creds)
        self.sheet = service.spreadsheets()

        ##self.duplicateTemplate("11/16")
        print(self.getAddRacer("user"))

    ## Duplicate template to new sheet
    def duplicateTemplate(self, newName):
        if(not self.sheet == None):
            metadata = self.sheet.get(spreadsheetId=self.spreadsheetId).execute()
            sheets = metadata.get('sheets', '')
            for sheet in sheets:
                if(sheet.get("properties", {}).get("title", "Sheet1") == "Template"):

                    body = {
                            'requests' : [
                                {
                                    'duplicateSheet' : {
                                        'sourceSheetId' : sheet.get("properties", {}).get("sheetId", 0),
                                        'insertSheetIndex' : 0,
                                        'newSheetName' : newName
                                    }
                                }
                            ]
                    }

                    reply = self.sheet.batchUpdate(spreadsheetId=self.spreadsheetId, body=body).execute()
                    self.currentPageId = reply.get("replies")[0].get("duplicateSheet").get("properties").get("sheetId")
                    self.currentPageName = newName
                    print("Added sheet {0} with id {1}".format(newName, reply.get("replies")[0].get("duplicateSheet").get("properties").get("sheetId")))

                    return

    ## Gets the column a specified racer is being tracked in, or creates one for them
    ## Also updates the racers username if necessary
    def getAddRacer(self, user):
        uid = 181465803344838656
        nick = "JJ"
        if(not self.sheet == None):
            reply = self.sheet.values().get(spreadsheetId=self.spreadsheetId, range=self.currentPageName).execute()
            values = reply.get("values")
            idRow = values[1]
            tagRow = values[2]

            idx = -1
            try:
                idx = idRow.index(str(uid))
                if(not tagRow[idx] == nick):
                    updateRange = self.currentPageName + "!" + self.cs(idx) + "3"
                    body = {
                        "values" : [
                            [nick]
                        ]
                    }
                    reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=updateRange, valueInputOption='RAW', body=body).execute()
            except:
                updateRange = self.currentPageName + "!" + self.cs(len(idRow)) + "2:" + self.cs(len(idRow)) + "3"
                body = {
                    "values" : [
                        [str(uid)],
                        [nick]
                    ]
                }
                reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=updateRange, valueInputOption='RAW', body=body).execute()
                idx = len(idRow)
            return(idx)
            

    ## converts a number to the column string
    def cs(self, n):
        n += 1
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return(s)


def setup(bot):
    bot.add_cog(Points(bot))