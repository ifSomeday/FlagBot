## This is all for old flag. All new processing is done in points.py
## This code is still here for sentimental purposes (lol)

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
import re

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

        self.scoreMatch = r"(?:(\d+) (\w+) ([\d,.]+))"

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
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), commands.is_owner())
    async def trackChannel(self, ctx, ch : discord.TextChannel):
        self.trackChannel = ch.id
        await self.updateSettings()
        print("Now tracking: {0}".format(self.trackChannel))

    
    @commands.command()
    @commands.is_owner()
    async def md5test(self, ctx):
        msg1 = await ctx.channel.fetch_message(839385941625143307)
        msg2 = await ctx.channel.fetch_message(839277381797675039)
        attachment1Hash = hashlib.md5(await msg1.attachments[0].read()).hexdigest()
        attachment2Hash = hashlib.md5(await msg2.attachments[0].read()).hexdigest()
        await ctx.send("Attachments are{0}equal\n```{1}```\n```{2}```".format(" " if attachment1Hash == attachment2Hash else " not ", attachment1Hash, attachment2Hash))


    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def grank(self, ctx):
        print(self.getLastRace())
        embed = await self.buildWorldRankEmbed()
        await ctx.send(embed=embed)

    @grank.error
    async def grankError(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.author.send("You can only use `!grank` once every 60 seconds, please wait {0} seconds then try again.".format(int(error.retry_after)))
        elif isinstance(error, IndexError):
            await ctx.author.send("There have been no ranks entered today. This is being working on, but `grank` can only be used after ranks have been entered.")
        else:
            print(error)
            traceback.print_exc()

    @commands.command()
    @commands.is_owner()
    async def deleteLastRace(self, ctx):
        db = self.bot.get_cog('DB')
        if(not db == None):
            await db.deleteLastRace()
            await ctx.reply("done.")

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


    @commands.Cog.listener()
    async def on_message(self, msg):
        ## you will want to save
        if(not msg.clean_content.startswith("!") and not msg.author == self.bot.user):
            if(msg.channel.id == self.trackChannel):
                if(msg.clean_content == "rank"):
                    for attachment in msg.attachments:
                        await self.parseTopTenImage(attachment, msg)    
                        embed = await self.buildWorldRankEmbed()
                        await msg.channel.send(embed=embed)                                 
                else:
                    points = 0
                    reply = ""
                    numMsg = self.getMsgPoints(msg.clean_content)

                    if(len(msg.attachments) > 0):
                        place, sim, ign, flagPts, placeBuf, ocrBuf = await self.parseImage(msg.attachments[0])
                        if(not flagPts == None):
                            num = 10 if not flagPts in ["730", "720"] else ((100, 50, 40, 35, 30)[place - 1 ] if place <= 5 else 20)

                            if((not numMsg == -1) and (not numMsg == num)):
                                points = numMsg
                                reply = "Mismatch between reported `{0}` and actual `{1}`. Recorded `{2}`.".format(numMsg, num, points)
                            else:
                                points = num
                                reply = "Recorded `{0}`.".format(points)
                                if(sim < 0.95):
                                    reply += " If this score is incorrect, please post the correct score."
                        else:
                            points = numMsg
                    else:
                        points = numMsg

                    if(points == -1):
                        await msg.add_reaction('❌')
                        await msg.author.send("I was unable to parse your message: `{0}`.\nPlease only send the amount of points you earned and nothing else.".format(msg.clean_content))
                        return

                    if(self.insertIdx == 0):
                        await msg.add_reaction('❌')
                        await msg.author.send("No submission window is current open. Results can only be submitted up to an hour after the race has started.")
                        return

                    if(points not in self.VALID_SCORES):
                        await msg.add_reaction('❌')
                        await msg.author.send("Please enter a valid score. Valid scores are: {0}.".format(", ".join([str(x) for x in self.VALID_SCORES])))
                        return

                    if(await self.addToSheet(msg.author, points)):
                        await msg.add_reaction('✅')
                        if(not reply == ""):
                            await msg.reply(reply)
                    else:
                        await msg.add_reaction('❌')
                        await msg.author.send("Unknown error occurred. Try again in several minutes or contact Will.")
            elif(msg.channel.id in [834876019940917278, 641483284244725776]):
                if(not "rank" in msg.clean_content):
                    for attachment in msg.attachments:
                        place, sim, ign, pts, placeBuf, ocrBuf = await self.parseImage(attachment)
                        if not ign == None:
                            await msg.reply("Detected {0} - {1} - {2} [{3}]".format(place, ign, pts, sim), files=[discord.File(placeBuf, filename="place.png"), discord.File(ocrBuf, filename="ocr.png")])
                else:
                    for attachment in msg.attachments:
                        await self.parseTopTenImage(attachment, msg, post=True)
                    
                   

    def getMsgPoints(self, text):
        try:
            pts = int(text)
            return(pts)
        except:
            return(-1)


    ##Loads images at the beginning of time
    def loadAssets(self):
        ##place assets
        self.places = []
        for i in range(1, 21):
            self.places.append(cv.imread('assets/{0}.png'.format(i),0))
        ##select bar
        self.selectBar = cv.imread('assets/selectBar.png',0)
        self.rockUI = cv.imread('assets/backgrnd2.png', 0)

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
                print("adding")
                await db.addWorldRank(scoreList, self.getLastRace())
        else:
            msg.reply("Unable to read scores, please try again with a new screenshot.")

        if(post):
            if(ret):
                await msg.reply(resp)
            else:
                await msg.reply(resp, files=[discord.File(threshBuf, filename="place.png")])

    def isInt(self, num):
        try:
            int(num)
        except:
            return(False)
        return(True)


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


    async def parseImage(self, attachment):
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
            return(num, sim, ign, points, placeBuf, ocrBuf)
            ##Finished the race
            ##if(points == "730"):
            ##    messageText = "I think `{0}` placed `{1}`, with {2}% certainty [{3} ms].".format(ign, num, round(sim*100, 2), round((end-start) * 1000.0, 2))
            ##Did not finish
            ##else:
            ##    messageText = "I think `{0}` did not finish, and ended the race in place `{1}`, with {2}% certainty [{3} ms].".format(ign, num, round(sim*100, 2), round((end-start) * 1000.0, 2))
        ##OCR failed
        else:
            return(num, sim, None, None, None, None)
            ##messageText = "Tesseract did not find a name and a place.\nI think `{0}` placed `{1}`, with {2}% certainty [{3} ms].".format(author.display_name, num, round(sim*100, 2), round((end-start) * 1000.0, 2))

        ##Send result
        ##await ch.send(messageText)

        

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


    ## gets the last submission window for submitting late scores
    def getLastRace(self):

        ##get current hour
        currHour = int(datetime.datetime.now().strftime("%H"))
        dst = time.localtime().tm_isdst

        ##race times
        indices = {
                4  + dst : 0,
                11 + dst : 1,
                13 + dst : 2,
                14 + dst : 3,
                15 + dst : 4
            }

        ##go backwards until we find a valid race
        while currHour not in indices:
            currHour -= 1
            if currHour < 0:
                currHour = 24
                
        ##add 5 per weekday past
        race = indices[currHour] + (5 * datetime.datetime.today().weekday())
        return(race)        


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

        z = self.getAllRacerScores(tag=False)

        tomorrow = datetime.date.today() + datetime.timedelta(days = 1)
        self.duplicateTemplate(tomorrow.strftime("%m/%d"))

        await self.updateRoles(z)


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


    async def buildWorldRankEmbed(self):
        db = self.bot.get_cog('DB')
        if(not db == None):
            print("here")
            ret = await db.getLatestDifferential()
            embed = discord.Embed()
            embed.title = "Guild Rankings"
            embed.url = "https://flag.lostara.com"
            embed.set_footer(text="willmrice.com", icon_url="https://flag.lostara.com/gwenhwyfar.gif")
            embed.color = discord.Color.dark_purple()
            guildEntries = []
            namePad = max(len(x[0]) for x in ret)
            numberPad = max(len(str(x[1])) for x in ret)
            print(namePad)
            for guild in ret:
                entry = ""
                if(guild[4] == None):
                    entry = "{0: <3} {1: <{width}} - {2: >{width2}}".format(str(guild[3])+".", guild[0], guild[1], width=namePad, width2=numberPad)
                else:
                    ##emoji = "🔽" if guild[4] > 1  else "🔼"
                    entry = "{0: <3} {1: <{width}} - {2: >{width2}} (+{3})".format(str(guild[3])+".", guild[0], guild[1], guild[2], width=namePad, width2=numberPad)
                guildEntries.append(entry)
            embed.add_field(name="Top 10", value="```{0}```".format("\n".join(guildEntries)))
            return(embed)
            

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


    async def updateRoles(self, z):
        ## Speed Demon 811030389095268393
        ## relampago 794847144589656114
        ## swift duck 810972999539884033
        guild = self.bot.get_guild(794720132492558386)
        roles = [guild.get_role(x) for x in [811030389095268393, 794847144589656114, 810972999539884033]]
        
        for i, user in enumerate(z[:10]):
            role = roles[0] if i < 1 else (roles[1] if i < 5 else roles[2])
            member = await guild.fetch_member(int(user[0]))
            try:
                print("Setting {0} to {1}".format(member.display_name, role.name))
            except:
                pass
            await member.remove_roles(*roles)
            await member.add_roles(role)


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
