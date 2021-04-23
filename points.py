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
import typing

from apiclient import discovery
from google.oauth2 import service_account

import config
import templates

import cv2 as cv
import numpy as np
import skimage.metrics as metrics
import io
import time
import pytesseract as tess

tess.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

class Points(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.trackChannel = 0
        self.clearChannel = False
        self.leaderboardChannel = 0

        self.fileLock = asyncio.Lock()
        self.filePath = "trackChannel.pickle"

        self.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        self.spreadsheetId = config.SHEET_ID
        self.sheet = None
        self.currentPageId = 0
        self.currentPageName = None
        self.insertIdx = 0

        self.VALID_SCORES = [100, 50, 40, 35, 30, 20, 10, 0]
        self.COLORS = [(0xf4, 0xcc, 0xcc), (0xfc, 0xe5, 0xcd), (0xff, 0xf2, 0xcc), (0xd9, 0xea, 0xd3), (0xd0, 0xe0, 0xe3), (0xc9, 0xda, 0xf8), (0xcf, 0xe2, 0xf3), (0xd9, 0xd2, 0xe9), (0xea, 0xd1, 0xdc),]

        self.loadAssets()
        self.loadSettings()
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
    @commands.has_guild_permissions(manage_guild=True)
    async def trackChannel(self, ctx, ch : discord.TextChannel):
        self.trackChannel = ch.id
        await self.updateSettings()
        print("Now tracking: {0}".format(self.trackChannel))


    ## updates the channel to post end of week leaderboard in
    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def leaderboardChannel(self, ctx, ch : discord.TextChannel):
        self.leaderboardChannel = ch.id
        await self.updateSettings()
        print("Leaderboard: {0}".format(self.trackChannel))

    
    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def leaderboard(self, ctx):
        z = self.getAllRacerScores()
        embed = self.buildLeaderboardEmbed(z)
        await ctx.send(embed=embed)


    @commands.command()
    @commands.cooldown(3, 60, commands.BucketType.user)
    async def points(self, ctx, user : typing.Optional[discord.Member]):
        user = ctx.author if user == None else user
        z = self.getAllRacerScores(tag=False)
        try:
            score = [x for x in z if int(x[0]) == user.id][0]
        except:
            await ctx.send("User has not recorded any scores")
            return
        embed = self.buildPointsEmbed(score, user, z.index(score) + 1)
        await ctx.send(embed=embed)


    @points.error
    async def pointsError(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.author.send("You can only use `!points` 3 times every 60 seconds, please wait {0} seconds then try again.".format(int(error.retry_after)))


    @commands.Cog.listener()
    async def on_message(self, msg):
        ## you will want to save
        if(not msg.clean_content.startswith("!") and not msg.author == self.bot.user):
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
                    return

                if(pts not in self.VALID_SCORES):
                    await msg.add_reaction('❌')
                    await msg.author.send("Please enter a valid score. Valid scores are: {0}.".format(", ".join([str(x) for x in self.VALID_SCORES])))
                    return

                if(await self.addToSheet(msg.author, pts)):
                    await msg.add_reaction('✅')
                else:
                    await msg.add_reaction('❌')
                    await msg.author.send("Unknown error occurred. Try again in several minutes or contact Will.")
            elif(msg.channel.id in [834877778573918249]):
                for attachment in msg.attachments:
                    await self.parseImage(attachment, msg.author)
                    
                   

    ##Loads images at the beginning of time
    def loadAssets(self):
        ##place assets
        self.places = []
        for i in range(1, 21):
            self.places.append(cv.imread('assets/{0}.png'.format(i),0))
        ##select bar
        self.selectBar = cv.imread('assets/selectBar.png',0)


    async def parseImage(self, attachment, author):
        ##prep
        attach = await attachment.read()
        ch = self.bot.get_channel(834877778573918249)

        ##retrieve place
        start = time.time()
        num, sim, img, crop, cords = self.recognizePlace(attach)
        end = time.time()

        #Store the place image in a buffer
        success, buffer = cv.imencode(".png", img)
        placeBuf = io.BytesIO(buffer)

        ##text
        text, img2 = self.extractText(crop, cords)
        textSplit = text.split()
        print(text)

        #Store the OCR image in a buffer
        success, buffer = cv.imencode(".png", img2)
        ocrBuf = io.BytesIO(buffer)

        messageText = ""

        ##len > 1 means we found IGN and place
        if(len(textSplit) > 1):
            ign = textSplit[0]
            ##Sometimes we get random periods in the number, so this should strip them out
            points = ''.join([x for x in textSplit[-1] if x.isdigit()])
            ##Finished the race
            if(points == "730"):
                messageText = "I think `{0}` placed `{1}`, with {2}% certainty [{3} ms].".format(ign, num, round(sim*100, 2), round((end-start) * 1000.0, 2))
            ##Did not finish
            else:
                messageText = "I think `{0}` did not finish, and ended the race in place `{1}`, with {2}% certainty [{3} ms].".format(ign, num, round(sim*100, 2), round((end-start) * 1000.0, 2))
        ##OCR failed
        else:
            messageText = "Tesseract did not find a name and a place.\nI think `{0}` placed `{1}`, with {2}% certainty [{3} ms].".format(author.display_name, num, round(sim*100, 2), round((end-start) * 1000.0, 2))

        ##Send result
        await ch.send(messageText, files=[discord.File(placeBuf, filename="place.png"), discord.File(ocrBuf, filename="ocr.png")])

        

    def recognizePlace(self, attach):
        ##Convert byte arrary to cv2 image
        img = cv.imdecode(np.asarray(bytearray(attach), dtype=np.uint8), 0)

        ##Crop select bar to screenshot size if necessary
        w = min(self.selectBar.shape[::-1][0], img.shape[::-1][0])
        h = min(self.selectBar.shape[::-1][1], img.shape[::-1][1])
        template = self.selectBar[0:h, 0:w]

        ## look for select bar
        res = cv.matchTemplate(img, template, cv.TM_CCOEFF)
        minVal, maxVal, minLoc, maxLoc = cv.minMaxLoc(res)
        crop = img.copy()[maxLoc[1]:maxLoc[1]+h, maxLoc[0]:maxLoc[0]+w]

        #most likely canidate
        num = 0
        maxSim = 0
        img2 = None
        cords = ()

        ##Iterate over the possible places and compare each one
        for i in range(1, 21):
            ##template matches each place, then runs ssim on that match to determine likelyhood
            sim, imgTmp, cordsTmp = self.ssim(crop, self.places[i - 1])
            ##higher sim means its more likely we got the correct place
            if sim > maxSim:
                maxSim = sim
                img2 = imgTmp.copy()
                num = i
                cords = cordsTmp

        return(num, maxSim, img2, crop, cords)

    
    ##structural similarity 
    def ssim(self, img1, temp):

        ##greyscale and w/h
        img1 = cv.cvtColor(img1, cv.COLOR_BGR2RGB)
        w, h = temp.shape[::-1]
        temp = cv.cvtColor(temp, cv.COLOR_BGR2RGB)

        ##find most likely canidate for palce
        res = cv.matchTemplate(img1, temp, cv.TM_CCOEFF)
        minVal, maxVal, minLoc, maxLoc = cv.minMaxLoc(res)
        crop = img1[maxLoc[1]:maxLoc[1]+h, maxLoc[0]:maxLoc[0]+w]
        cords = (maxLoc[1], maxLoc[1]+h, maxLoc[0], maxLoc[0]+w)

        ##Determine likelyhood it is that place
        sim = metrics.structural_similarity(temp, crop, multichannel=True)

        ##Draw rectangle for debug
        cv.rectangle(img1, maxLoc, (maxLoc[0] + w, maxLoc[1] + h), 255, 2)

        return(sim, img1, cords)


    #Extract text with tesseract
    def extractText(self, img, cords):

        ##Need to clean the image with thresholding for tesseract to work
        thresh = img.copy()
        ##zero out the place so we dont't OCR it
        ##we arent OCRing the place number in the first place because tesseract really struggles with that font + small numbers
        ##we also have the actual place assets from the .wz files, so template matching it is much more accurate
        thresh[cords[0]:cords[1],cords[2]:cords[3]] = 0
        ##190 threshold seems to work best, could use some tuning maybe
        ##Adaptive tuning doesn't work here because the text is too small to use nearby samples
        ret, thresh = cv.threshold(thresh,190,255,cv.THRESH_BINARY_INV) 
        #run tesseract on the thresholded image
        text = tess.image_to_string(thresh)
        return(text, thresh)

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
    async def updateSettings(self):
        async with self.fileLock:
            with open(self.filePath, "wb") as f:
                pickle.dump({
                    "trackChannel" : self.trackChannel,
                    "clearChannel" : self.clearChannel,
                    "leaderboardChannel" : self.leaderboardChannel
                }, f)


    ## Not under lock because we only call this in init
    def loadSettings(self):
        if os.path.exists(self.filePath):
            with open(self.filePath, "rb") as f:
                tmp = pickle.load(f)
                if(isinstance(tmp, int)):
                    self.trackChannel = tmp
                else:
                    self.trackChannel = tmp.setdefault("trackChannel", 0)
                    self.clearChannel = tmp.setdefault("clearChannel", False)
                    self.leaderboardChannel = tmp.setdefault("leaderboardChannel", 0)


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

        if(not self.leaderboardChannel == 0):
            z = self.getAllRacerScores()
            embed = self.buildLeaderboardEmbed(z)
            ch = self.bot.get_channel(self.leaderboardChannel)
            await ch.send(embed=embed)

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


    ## Gets the current racers weekly scores
    def getAllRacerScores(self, tag=True):

        ## Get sheet
        reply = self.sheet.values().get(spreadsheetId=self.spreadsheetId, range=self.currentPageName).execute()
        values = reply.get("values")

        ## The next 4 lines of code are a disaster
        ## strip out the discord user name and weekly total rows
        arr = [x[2:] for x in values if len(x) > 2 and any(s in x[1] for s in ["Discord Tag" if tag else "Discord ID", "Weekly Total"])]
        ## cast the scores as ints
        arr[1] = [int(x) for x in arr[1]]
        ## zip into a list of (username, score, inital index) tuples
        z = [(*x, i) for i, x in enumerate(zip(*arr))]
        ## sort by scores, high to low
        z.sort(key=lambda x: x[1], reverse=True)

        return(z)


    def buildLeaderboardEmbed(self, z):
        embed = discord.Embed()
        ##embed.set_author(name="Flag Leaderboard", url="https://docs.google.com/spreadsheets/d/{}".format(self.spreadsheetId))
        embed.title = "Flag Leaderboard"
        embed.set_footer(text="Scores for the week of {0}".format(self.currentPageName))
        embed.url = "https://docs.google.com/spreadsheets/d/{}".format(self.spreadsheetId)
        embed.color = discord.Color.from_rgb(*self.COLORS[z[0][2] % len(self.COLORS)])

        ##no racers, so return
        if(len(z) == 0):
            return(None)
        embed.add_field(name="Speed Demon", value="1. {0[0]} - {0[1]} points".format(z[0]), inline=False)
        if(len(z[1:5]) > 0):
            embed.add_field(name="Relámpago", value="{0}".format("\n".join(["{0}. {1[0]} - {1[1]} points".format(i + 2, x) for i, x in enumerate(z[1:5])])), inline=False)
        if(len(z[5:10]) > 0):
            embed.add_field(name="Swift Duck", value="{0}".format("\n".join(["{0}. {1[0]} - {1[1]} points".format(i + 6, x) for i, x in enumerate(z[5:10])])), inline=False)

        if(hasattr(config, "EMBED_IMAGE_URL") and not config.EMBED_IMAGE_URL == None):
            embed.set_thumbnail(url=config.EMBED_IMAGE_URL)

        return(embed)


    def buildPointsEmbed(self, score, user, place):
        embed = discord.Embed()
        embed.title = "Points for {0}".format(user.display_name)
        embed.set_footer(text="Points for the week of {0}".format(self.currentPageName))
        embed.url = "https://docs.google.com/spreadsheets/d/{}".format(self.spreadsheetId)
        embed.color = discord.Color.from_rgb(*self.COLORS[score[2] % len(self.COLORS)])

        ##lmao
        embed.add_field(name="Place", value="{0}{1}".format(place, 'trnshddt'[0xc0006c000000006c>>2*place&3::4]))
        embed.add_field(name="Points", value=score[1])

        embed.set_thumbnail(url = user.avatar_url)

        return(embed)

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