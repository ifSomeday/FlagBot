from __future__ import print_function

import discord
from discord.ext import commands, tasks

import asyncio
import aioschedule as schedule
import datetime
import time
import pickle
import os
import traceback

from apiclient import discovery
from google.oauth2 import service_account

import config
import templates

class Points(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.trackChannel = 0

        self.fileLock = asyncio.Lock()
        self.filePath = "trackChannel.pickle"

        self.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        self.spreadsheetId = config.SHEET_ID
        self.sheet = None
        self.currentPageId = 0
        self.currentPageName = None
        self.insertIdx = 0

        self.COLORS = [(0xf4, 0xcc, 0xcc), (0xfc, 0xe5, 0xcd), (0xff, 0xf2, 0xcc), (0xd9, 0xea, 0xd3), (0xd0, 0xe0, 0xe3), (0xc9, 0xda, 0xf8), (0xcf, 0xe2, 0xf3), (0xd9, 0xd2, 0xe9), (0xea, 0xd1, 0xdc),]

        self.loadChannel()
        self.loadSheets()
        self.prepSchedule()
        self.getActivePage()

        print("Currently tracking points in channel id: {0}".format(self.trackChannel))

        self.scheduler.start()


    @tasks.loop(seconds=1)
    async def scheduler(self):
        await schedule.run_pending()

    @scheduler.before_loop
    async def beforeScheduler(self):
        print("scheduler waiting...")
        await self.bot.wait_until_ready()


    ## updates the channel to track points in
    @commands.command()
    @commands.is_owner()
    async def trackChannel(self, ctx, ch : discord.TextChannel):
        await self.updateChannel(ch.id)
        print("Now tracking: {0}".format(self.trackChannel))


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

            if(self.insertIdx == 0):
                await msg.add_reaction('❌')
                await msg.author.send("No submission window is current open. Results can only be submitted up to an hour after the race has started.")

            if(await self.addToSheet(msg.author, pts)):
                await msg.add_reaction('✅')
            else:
                await msg.add_reaction('❌')
                await msg.author.send("Unknown error occurred. Try again in several minutes or contact Will.")


    ## adds points to the sheet for the given user
    async def addToSheet(self, user, points):
        if(not self.sheet == None):
            try:
                col = self.getAddRacer(user)
                updateRange = self.currentPageName + "!" + self.cs(col) + str(self.insertIdx)
                body = {
                    "values" : [
                        [points]
                    ]
                }
                reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=updateRange, valueInputOption='RAW', body=body).execute()
                return(True)
            except Exception as e:
                print(e)
                traceback.print_exc()
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

                    break

            body = {
                "valueInputOption" : "USER_ENTERED",
                "data" : []
            }

            for i in range(1, 8):
                body["data"].append(templates.batchValueEntry(self.currentPageName + "!A" + str(((i - 1) * 6) + 5), [[(datetime.date.today() + datetime.timedelta(days = i)).strftime("%m/%d")]]))

            reply = self.sheet.values().batchUpdate(spreadsheetId=self.spreadsheetId, body=body).execute()


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
                if(not tagRow[idx] == user.display_name):
                    updateRange = self.currentPageName + "!" + self.cs(idx) + "3"
                    body = {
                        "values" : [
                            [user.display_name]
                        ]
                    }
                    reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=updateRange, valueInputOption='RAW', body=body).execute()
            except:
                body = {
                    "valueInputOption" : "USER_ENTERED",
                    "data" : [
                        templates.batchValueEntry(self.currentPageName + "!" + self.cs(len(idRow)) + "2:" + self.cs(len(idRow)) + "3", [[str(user.id)], [user.display_name]]),
                        templates.batchValueEntry(self.currentPageName + "!" + self.cs(len(idRow)) + "47", [["=SUM({0}5:{0}45)".format(self.cs(len(idRow)))]]),
                    ]
                }
                reply = self.sheet.values().batchUpdate(spreadsheetId=self.spreadsheetId, body=body).execute()

                idx = len(idRow)
                self.updateColumnColor(idx)
            return(idx)
            
    
    ## Gets the current active page (always index 0)
    def getActivePage(self):
        if(not self.sheet == None):
            metadata = self.sheet.get(spreadsheetId=self.spreadsheetId).execute()
            sheets = metadata.get('sheets', '')
            for sheet in sheets:
                props = sheet["properties"]
                if(props["index"] == 0):
                    if(props["title"] == "Template"):
                        tomorrow = datetime.date.today() + datetime.timedelta(days = 1)
                        self.duplicateTemplate(tomorrow.strftime("%m/%d"))
                    else:
                        self.currentPageId = props["sheetId"]
                        self.currentPageName = props["title"]
                    return


    def updateColumnColor(self, col):
        if(not self.sheet == None):
            color = self.COLORS[(col-2)%len(self.COLORS)]
            body = {
                "requests" : [
                    templates.backgroundColor(col, 1, 3, self.currentPageId, color),
                    templates.backgroundColor(col, 46, 47, self.currentPageId, color)
                ]
            }

            for i in range(0, 7):
                body["requests"].append(templates.backgroundColor(col, 4 + (6 * i), 9 + (6 * i), self.currentPageId, color))

            res = self.sheet.batchUpdate(spreadsheetId = self.spreadsheetId, body=body).execute()


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