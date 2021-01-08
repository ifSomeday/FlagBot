import discord
from discord.ext import commands, tasks

import os
import pickle
import config
import asyncio
import typing
import re
from collections import OrderedDict

from apiclient import discovery
from google.oauth2 import service_account

class GPQ(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        

        self.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        self.spreadsheetId = config.GPQ_SHEET_ID
        self.sheet = None

        self.gpqMessage = None

        self.filePath = "{0}/gpq.pickle".format(os.getcwd())
        self.fileLock = asyncio.Lock()

        self.currentPageId = 0
        self.currentPageName = None
        self.nicknamePageId = 0
        self.nicknamePageName = "Nicknames"

        self.loadSheets()
        self.loadMessage()
        self.getActivePage()
        self.getNicknamePage()
        self.reactLoop.start()


    @tasks.loop(seconds=300)
    async def reactLoop(self):
        if(self.gpqMessage):
            ch = self.bot.get_channel(self.gpqMessage["ch"])
            msg = await ch.fetch_message(self.gpqMessage["id"])
            for reaction in msg.reactions:
                users = await reaction.users().flatten()
                if(reaction.emoji == "✅"):
                    await self.updateSheet(users)
                elif(reaction.emoji == "❌"):
                    pass ## Not doing anything special for this right now
                else:
                    try:
                        await reaction.clear()
                    except:
                        pass ## Didn't have permissions probably



    @reactLoop.before_loop
    async def beforeReactLoop(self):
        print("reactLoop waiting...")
        await self.bot.wait_until_ready()


    @commands.command()
    @commands.is_owner()
    async def gpq(self, ctx, u : typing.Union[discord.Message, discord.TextChannel, int], c : typing.Optional[int]):
        if(u):
            if(isinstance(u, discord.Message)):
                msg = u
            else:
                print("Getting latest message in channel {0}".format(u.name))
                messages = await u.history(limit=1).flatten()
                msg = messages[0]
            print("Setting GPQ message to {0}".format(msg.id))
            await self.updateMessage(msg)

            ##Add Yes and no Reactions
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            await ctx.send("Tracking GPQ attendance")

        else:
            await ctx.send("Closing GPQ attendance")
            await self.updateMessage(None)


    ## updates the gpq message id and saves to pickle, all under lock
    async def updateMessage(self, msg):
        async with self.fileLock:
            self.gpqMessage = None
            if(msg):
                self.gpqMessage = { "id" : msg.id, "ch" : msg.channel.id }
            with open(self.filePath, "wb") as f:
                pickle.dump(self.gpqMessage, f)

    ## Not under lock because we only call this in init
    def loadMessage(self):
        if os.path.exists(self.filePath):
            with open(self.filePath, "rb") as f:
                self.gpqMessage = pickle.load(f)

    ## Load Sheets with service account
    def loadSheets(self):
        credFile = os.path.join(os.getcwd(), config.CRED_FILE)
        creds = service_account.Credentials.from_service_account_file(credFile, scopes=self.scopes)
        service = discovery.build('sheets', 'v4', credentials=creds)
        self.sheet = service.spreadsheets()


    ## updates the sheet based on the latest reactions
    async def updateSheet(self, users):

        self.getActivePage()
        self.getNicknamePage()

        nicks = OrderedDict([ x for x in self.getNicknameMapping() if not len(x) is 0 ])
        arr = []

        for user in users:
            if(not user == self.bot.user):
                ## Not using setdefault() here because we want to avoid unnecessary interation with discord API
                if not str(user.id) in nicks:
                    nicks[str(user.id)] = await self.getNickOrIgn(user.id)
                arr.append([nicks[str(user.id)]])

        self.updateNicknameMapping(list(nicks.items()))
        self.updateAttending(arr)


    ## Gets the Nickname page, and if it does not exist, creates it
    def getNicknamePage(self):
        if(not self.sheet == None):
            metadata = self.sheet.get(spreadsheetId=self.spreadsheetId).execute()
            sheets = metadata['sheets']
            for sheet in sheets:
                props = sheet["properties"]
                if(props["title"] == self.nicknamePageName):
                    self.nicknamePageId = props["sheetId"]
                    return
            
            ## If we get here there was no nickname sheet
            body = {
                'requests' : [
                    {
                        'addSheet' : {
                            'properties' : {
                                'title' : self.nicknamePageName,
                            }
                        }
                    }
                ]
            }

            reply = self.sheet.batchUpdate(spreadsheetId=self.spreadsheetId, body=body).execute()
            self.nicknamePageId = reply.get("replies")[0].get("addSheet").get("properties").get("sheetId")

            body = {
                "values" : [
                    ["ID (DO NOT CHANGE)", "Nickname"]
                ]
            }
            r1 = "{0}!A1".format(self.nicknamePageName)
            reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=r1, body=body, valueInputOption="RAW").execute()


    ## Gets the current nickname mapping
    def getNicknameMapping(self):
        if(not self.sheet == None):
            ## First row is headers
            r1 = "{0}!A:B".format(self.nicknamePageName)
            reply = self.sheet.values().get(spreadsheetId=self.spreadsheetId, range=r1).execute()
            return(reply["values"])


    ## Clears the nickname mapping, then adds back the new mapping
    def updateNicknameMapping(self, v):
        if(not self.sheet == None):
            r1 = "{0}!A:B".format(self.nicknamePageName)
            body= {
                "values" : v
            }
            reply = self.sheet.values().clear(spreadsheetId=self.spreadsheetId, range=r1).execute()
            reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=r1, valueInputOption='RAW', body=body).execute()


    ## Gets active GPQ party page
    def getActivePage(self):
        if(not self.sheet == None):
            metadata = self.sheet.get(spreadsheetId=self.spreadsheetId).execute()
            sheets = metadata.get('sheets', '')
            for sheet in sheets:
                props = sheet["properties"]
                if(props["index"] == 0):
                    self.currentPageId = props["sheetId"]
                    self.currentPageName = props["title"]
                    return


    ## Clears the attending column, then adds back everyone that is still attending
    def updateAttending(self, v):
        if(not self.sheet == None):
            r1 = "{0}!Z3:Z".format(self.currentPageName)
            body = {
                "values" : v
            }
            reply = self.sheet.values().clear(spreadsheetId=self.spreadsheetId, range=r1).execute()
            reply = self.sheet.values().update(spreadsheetId = self.spreadsheetId, range=r1, valueInputOption="RAW", body=body).execute()


    ## display_name is not always accurate it appears (perhaps just in reaction lists)
    ## Also will extract text within parenthesis if available, assuming that is an IGN
    async def getNickOrIgn(self, i):
        ch = self.bot.get_channel(self.gpqMessage["ch"])
        g = ch.guild
        user = await g.fetch_member(i)
        res = re.search(r"\((.*)\)", user.display_name)
        if(res):
            return(res.group(1))
        else:
            return(user.display_name)


    ## converts a number to the column string
    def cs(self, n):
        n += 1
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return(s)

def setup(bot):
    bot.add_cog(GPQ(bot))