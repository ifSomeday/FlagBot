import discord
from discord.ext import commands, tasks

import os
import pickle
import asyncio
import config
import templates
import datetime

from apiclient import discovery
from google.oauth2 import service_account


class PB(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.COLORS = [(0xf4, 0xcc, 0xcc), (0xfc, 0xe5, 0xcd), (0xff, 0xf2, 0xcc), (0xd9, 0xea, 0xd3), (0xd0, 0xe0, 0xe3), (0xc9, 0xda, 0xf8), (0xcf, 0xe2, 0xf3), (0xd9, 0xd2, 0xe9), (0xea, 0xd1, 0xdc),]

        self.trackChannel = 0
        self.fileLock = asyncio.Lock()

        self.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        self.spreadsheetId = config.PB_SHEET_ID

        self.currentPageId = 0
        self.currentPageName = None

        self.loadSheets()
        self.getActivePage()


    ## Load Sheets with service account
    def loadSheets(self):
        credFile = os.path.join(os.getcwd(), config.CRED_FILE)
        creds = service_account.Credentials.from_service_account_file(credFile, scopes=self.scopes)
        service = discovery.build('sheets', 'v4', credentials=creds)
        self.sheet = service.spreadsheets()


    ## Gets the current active page (always index 0)
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
                        templates.batchValueEntry(self.currentPageName + "!" + self.cs(len(idRow)) + "5:" + self.cs(len(idRow)) + "11", [[0]] * 7),
                        templates.batchValueEntry(self.currentPageName + "!" + self.cs(len(idRow)) + "13", [["=SUM({0}5:{0}11)".format(self.cs(len(idRow)))], ["=AVERAGE({0}5:{0}11)".format(self.cs(len(idRow)))]]),
                    ]
                }
                reply = self.sheet.values().batchUpdate(spreadsheetId=self.spreadsheetId, body=body).execute()

                idx = len(idRow)
                self.updateColumnColor(idx)
            return(idx)

    def updateColumnColor(self, col):
        if(not self.sheet == None):
            color = self.COLORS[(col-1)%len(self.COLORS)]
            body = {
                "requests" : [

                ]
            }

            body["requests"].append(templates.backgroundColor(col, 1, 3, self.currentPageId, color))
            body["requests"].append(templates.backgroundColor(col, 4, 11, self.currentPageId, color))
            body["requests"].append(templates.backgroundColor(col, 12, 14, self.currentPageId, color))

            res = self.sheet.batchUpdate(spreadsheetId = self.spreadsheetId, body=body).execute()

    @commands.command()
    async def bank(self, ctx, b: float, * junk):
        try:
            col = self.getAddRacer(ctx.author)
            updateRange = self.currentPageName + "!" + self.cs(col) + str(self.getInsertDay())
            body = {
                "values" : [
                    [b]
                ]
            }
            reply = self.sheet.values().update(spreadsheetId=self.spreadsheetId, range=updateRange, valueInputOption='RAW', body=body).execute()
            await ctx.message.add_reaction('✅')
        except Exception as e:
            print("oopsie woopsie")
            print(e)
            await ctx.message.add_reaction('❌')
        

    def getInsertDay(self):
        return(5 -5 + datetime.datetime.today().weekday())

    ## converts a number to the column string
    def cs(self, n):
        n += 1
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return(s)

def setup(bot):
    bot.add_cog(PB(bot))