import discord
from discord.ext import commands, tasks

import os
import pickle
import config
import asyncio
import typing
import re
import traceback
from enum import Enum
from collections import OrderedDict

import datetime
import pytz

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
            try:
                ch = self.bot.get_channel(self.gpqMessage["ch"])
                msg = await ch.fetch_message(self.gpqMessage["id"])
                for reaction in msg.reactions:
                    users = await reaction.users().flatten()
                    if(reaction.emoji == "✅"):
                        await self.updateSheet(users, self.Attendance.YES)
                    elif(reaction.emoji == "❌"):
                        await self.updateSheet(users, self.Attendance.NO)
                    elif(reaction.emoji == "❔"):
                        await self.updateSheet(users, self.Attendance.MAYBE)
                    else:
                        try:
                            await reaction.clear()
                        except:
                            pass ## Didn't have permissions probably
            except discord.errors.NotFound as e:
                pass
            except Exception as e:
                print(e)
                traceback.print_exc()
                


    @reactLoop.before_loop
    async def beforeReactLoop(self):
        print("reactLoop waiting...")
        await self.bot.wait_until_ready()


    @commands.command()
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
    async def postGpq(self, ctx, hours : int = 3, minutes : int = 45):
        today = datetime.date.today()
        friday = today + datetime.timedelta( (5-today.weekday()) % 7 )
        dt = datetime.datetime.combine(friday, datetime.time())

        gpqTime = dt + datetime.timedelta(hours = hours, minutes = minutes)

        pstTZ = pytz.timezone('US/Pacific')
        pst = pytz.utc.localize(gpqTime).astimezone(pstTZ)

        cstTZ = pytz.timezone('US/Central')
        cst = pytz.utc.localize(gpqTime).astimezone(cstTZ)

        estTZ = pytz.timezone('US/Eastern')
        est = pytz.utc.localize(gpqTime).astimezone(estTZ)

        bstTZ = pytz.timezone('Europe/London')
        bst = pytz.utc.localize(gpqTime).astimezone(bstTZ)

        aestTZ = pytz.timezone('Australia/Melbourne')
        aest = pytz.utc.localize(gpqTime).astimezone(aestTZ)

        gpqText = """
<@&795087707046543370> This week's GPQ will be Friday Reset+{0}. Check below for your time zone and react if you can/can't make it.

{1} {3} PST / {4} CST / {5} EST
[ {2} {6} BST / {7} AEST ]

React with :white_check_mark: if you are able to make it, :x: if you are not, :grey_question:if you don't know/want to fill.
        """

        plusTime = "{0}:{1}".format(hours, minutes)

        d = int(pst.strftime("%d"))
        d2 = int(bst.strftime("%d"))

        suffix1 = 'th' if 11<=d<=13 else {1:'st',2:'nd',3:'rd'}.get(d%10, 'th')
        weekday1 = pst.strftime("%A %B %d{0}".format(suffix1))
        
        suffix2 = 'th' if 11<=d2<=13 else {1:'st',2:'nd',3:'rd'}.get(d2%10, 'th')
        weekday2 = bst.strftime("%A %B %d{0}".format(suffix2))

        time1 = pst.strftime("%I:%M %p")
        time2 = cst.strftime("%I:%M %p")
        time3 = est.strftime("%I:%M %p")
        time4 = bst.strftime("%I:%M %p")
        time5 = aest.strftime("%I:%M %p")

        ch = self.bot.get_channel(794753791153012788)
        msg = await ch.send(gpqText.format(plusTime, weekday1, weekday2, time1, time2, time3,  time4, time5))
        await self.gpq(ctx, msg, 0)


###<@&795087707046543370>

    @commands.command()
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
    async def gpq(self, ctx, u : typing.Union[discord.Message, discord.TextChannel, int, None], c : typing.Optional[int]):
        if(u):
            msg = None
            if(isinstance(u, discord.Message)):
                msg = u
            elif(isinstance(u, int) and c):
                ch = self.bot.get_channel(c)
                msg = await ch.fetch_message(u)
            else:
                print("Getting latest message in channel {0}".format(u.name))
                messages = await u.history(limit=1).flatten()
                msg = messages[0]
            print("Setting GPQ message to {0}".format(msg.id))
            await self.updateMessage(msg)

            ##Add Yes and no Reactions
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            await msg.add_reaction("❔")

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
    async def updateSheet(self, users, attendance):

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
        self.updateAttendance(arr, attendance)


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
    def updateAttendance(self, v, attendance):
        if(not self.sheet == None):
            r1 = "{0}!{1}3:{1}".format(self.currentPageName, attendance.value)
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
    

    class Attendance(Enum):
        YES = 'Z'
        NO = 'AC'
        MAYBE = 'AE'
         

def setup(bot):
    bot.add_cog(GPQ(bot))
