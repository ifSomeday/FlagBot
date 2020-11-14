from __future__ import print_function

import discord
from discord.ext import commands, tasks

import asyncio
import aioschedule as schedule
import datetime
import time
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
        self.insertIdx = 0

        self.loadChannel()
        self.loadSheets()
        self.prepSchedule()

        print("Currently tracking points in channel id: {0}".format(self.trackChannel))

        self.scheduler.start()


    @tasks.loop(seconds=1)
    async def scheduler(self):
        await schedule.run_pending()

    @scheduler.before_loop
    async def beforeScheduler(self):
        print("waiting...")
        await self.bot.wait_until_ready()


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


    ## Schedules our tasks around flag times
    def prepSchedule(self):

        ## Maple doesn't do DST, so we need to account for it
        dst = time.localtime().tm_isdst

        ## Flag Schedules
        schedule.every().day.at("{0}:00".format(4+dst)).do(self.updateSubmissionWindow, t=0)    ## Open 4AM submissions
        schedule.every().day.at("{0}:00".format(5+dst)).do(self.updateSubmissionWindow)         ## Close 4AM submissions
        schedule.every().day.at("{0}:00".format(11+dst)).do(self.updateSubmissionWindow, t=1)   ## Open 11AM submissions
        schedule.every().day.at("{0}:00".format(12+dst)).do(self.updateSubmissionWindow)        ## Close 11AM submissions
        schedule.every().day.at("{0}:00".format(13+dst)).do(self.updateSubmissionWindow, t=2)   ## Open 1PM submissions
        schedule.every().day.at("{0}:00".format(14+dst)).do(self.updateSubmissionWindow, t=3)   ## Close 1PM submissions, Open 2PM submissions
        schedule.every().day.at("{0}:00".format(15+dst)).do(self.updateSubmissionWindow, t=4)   ## Close 2PM submissions, Open 3PM submissions
        schedule.every().day.at("{0}:00".format(16+dst)).do(self.updateSubmissionWindow)        ## Close 3PM submissions

        ## Prepares new sheet for the coming week
        schedule.every().sunday.at("{0}:00".format(17+dst)).do(self.newWeek)

        ## set up our current submission index, in case bot restarts during submission window.
        ## we could have used this instead of scheduling, but I like the ideal of a scheduler.
        ## we would need to use a scheduler for the weekly reset anyway.
        try:
            self.insertIdx = {
                4  + dst : 0,
                11 + dst : 1,
                13 + dst : 2,
                14 + dst : 3,
                15 + dst : 4
            }.get(int(datetime.datetime.now().strftime("%H")), None) + 5 + (6 * datetime.datetime.today().weekday())
        except:
            self.insertIdx = 0
        
        print(self.insertIdx)


    ## Updates the active submission window
    async def updateSubmissionWindow(self, t=None):
        print("I am updating Submission Window")
        if(not t == None):
            self.insertIdx = 5 + (6 * datetime.datetime.today().weekday()) + t
            print("Set insertIdx to {0}".format(self.insertIdx))
        else:
            print("closed submissions")
            self.insertIdx = 0


    ## Barren for now, eventually add weekly leaderboard and stuff
    async def newWeek(self):
        tomorrow = datetime.date.today() + datetime.timedelta(days = 1)
        self.duplicateTemplate(tomorrow.strftime("%m/%d"))


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
        if(not self.sheet == None):
            reply = self.sheet.values().get(spreadsheetId=self.spreadsheetId, range=self.currentPageName).execute()
            values = reply.get("values")
            idRow = values[1]
            tagRow = values[2]

            idx = -1
            try:
                idx = idRow.index(str(user.id))
                if(not tagRow[idx] == user.nickname):
                    updateRange = self.currentPageName + "!" + self.cs(idx) + "3"
                    body = {
                        "values" : [
                            [user.nickname]
                        ]
                    }
                    reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=updateRange, valueInputOption='RAW', body=body).execute()
            except:
                updateRange = self.currentPageName + "!" + self.cs(len(idRow)) + "2:" + self.cs(len(idRow)) + "3"
                body = {
                    "values" : [
                        [str(user.id)],
                        [user.nickname]
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