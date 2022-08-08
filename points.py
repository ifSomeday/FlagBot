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
import re

import config
import templates

import cv2 as cv
import numpy as np
import skimage.metrics as metrics
import io
import time
import pytesseract as tess
import hashlib

##tess.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

class Points(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.trackChannel = 0
        self.clearChannel = False
        self.leaderboardChannel = 0

        self.fileLock = asyncio.Lock()
        self.filePath = "trackChannel.pickle"

        self.COLORS = [(0xf4, 0xcc, 0xcc), (0xfc, 0xe5, 0xcd), (0xff, 0xf2, 0xcc), (0xd9, 0xea, 0xd3), (0xd0, 0xe0, 0xe3), (0xc9, 0xda, 0xf8), (0xcf, 0xe2, 0xf3), (0xd9, 0xd2, 0xe9), (0xea, 0xd1, 0xdc),]

        self.loadSettings()
        self.prepSchedule()

        self.scoreMatch = r"(?:(\d+) (\w+) ([\d,.]+))"

        self.scheduler.start()


    @tasks.loop(seconds=1)
    async def scheduler(self):
        await schedule.run_pending()

    @scheduler.before_loop
    async def beforeScheduler(self):
        print("scheduler waiting...")
        await self.bot.wait_until_ready()


    @commands.command()
    @commands.is_owner()
    async def test(self):
        pass


    ## updates the channel to track points in
    @commands.command()
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
    async def trackChannel(self, ctx, ch : discord.TextChannel):
        self.trackChannel = ch.id
        await self.updateSettings()
        print("Now tracking: {0}".format(self.trackChannel))


    ## updates the channel to post end of week leaderboard in
    @commands.command()
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
    async def leaderboardChannel(self, ctx, ch : discord.TextChannel):
        self.leaderboardChannel = ch.id
        await self.updateSettings()
        print("Leaderboard: {0}".format(self.trackChannel))

    
    @commands.command()
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
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
        print(score)
        embed = self.buildPointsEmbed(score, user, z.index(score) + 1)
        await ctx.send(embed=embed)


    @points.error
    async def pointsError(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.author.send("You can only use `!points` 3 times every 60 seconds, please wait {0} seconds then try again.".format(int(error.retry_after)))


    async def parseTopTenImage(self, attachment, msg, post=False):
        attach  = await attachment.read()
        img = cv.imdecode(np.asarray(bytearray(attach), dtype=np.uint8), 0)

        w = min(self.rockUI.shape[::-1][0], img.shape[::-1][0])
        h = min(self.rockUI.shape[::-1][1], img.shape[::-1][1])

        template = self.rockUI.copy()[0:h, 0:w]

        res = cv.matchTemplate(img, template, cv.TM_CCOEFF)
        minVal, maxVal, minLoc, maxLoc = cv.minMaxLoc(res)
        crop = img.copy()[maxLoc[1]:maxLoc[1]+h, maxLoc[0]:maxLoc[0]+w]

        thresh = cv.medianBlur(crop, 1)
        thresh = thresh.copy()[85:335, 40:290] ##hardcoded LOL
        ret, thresh = cv.threshold(thresh, 105, 255, cv.THRESH_BINARY_INV) 
        thresh = cv.resize(thresh, (thresh.shape[1] * 2, thresh.shape[0] * 2), interpolation = cv.INTER_CUBIC)

        success, buffer = cv.imencode(".png", thresh)
        threshBuf = io.BytesIO(buffer)

        text = tess.image_to_string(thresh)

        ret, resp, scoreList = self.extractRanks(text)

        if(not scoreList == None):
            db = self.bot.get_cog('DB')
            if(not db == None):
                await db.addWorldRank(scoreList, self.getLastRace())
        else:
            msg.reply("Unable to read scores, please try again with a new screenshot.")

        if(post):
            if(ret):
                await msg.reply(resp)
            else:
                await msg.reply(resp, files=[discord.File(threshBuf, filename="place.png")])


    def extractRanks(self, text):
        scoreList = re.findall(self.scoreMatch, text)
        response = ""
        ## Best case scenario our regex works
        if(len(scoreList) == 10):
            response = "[1] Found scores:\n```{0}```".format("\n".join(["{0} - {1} - {2}".format(*x) for x in scoreList]))
            return(True, response, scoreList)
        ## Start fallback methods
        else:
            text2 = text.replace("Rank", "").replace("Guild", "").replace("Score", "").replace(".", "").strip()
            scoreList2 = text2.split()

            ##Text splitting got 30 entries
            if(len(scoreList2) == 30):
                scoreTuple = list(zip(scoreList2[0:10], scoreList2[10:20], scoreList2[20:30]))
                if(all(self.isInt(x[0]) and self.isInt(x[2].replace(",", "")) for x in scoreTuple)):
                    response = "[2] Found scores:\n```{0}```".format("\n".join(["{0} - {1} - {2}".format(*x) for x in scoreTuple]))
                    return(True, response, scoreTuple)

            ##Original scoreList
            if(len(scoreList)> 0):
                response = "[3] Found scores:\n```{0}```".format("\n".join(["{0} - {1} - {2}".format(*x) for x in scoreList]))
                return(False, response, scoreList)

            ##Text 
            if(len(scoreList2) % 3 == 0):
                scoreTuple = list(zip(scoreList2[0:10], scoreList2[10:20], scoreList[20:30]))
                response = "[4] Found scores:\n```{0}```".format("\n".join(["{0} - {1} - {2}".format(*x) for x in scoreTuple]))
                return(False, response, scoreTuple)

        return(False, "Unable to retreive scores.\nOCR data: ```{0}```".format(text), None)


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




    ## Barren for now, eventually add weekly leaderboard and stuff
    async def newWeek(self):

        if(not self.leaderboardChannel == 0):
            z = self.getAllRacerScores()
            embed = self.buildLeaderboardEmbed(z)
            ch = self.bot.get_channel(self.leaderboardChannel)
            await ch.send(embed=embed)

        tomorrow = datetime.date.today() + datetime.timedelta(days = 1)
        self.duplicateTemplate(tomorrow.strftime("%m/%d"))



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
