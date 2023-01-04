import discord
from discord.ext import commands
import FlameCalc
import pytesseract as tess
import os
import cv2 as cv
import numpy as np
import requests.api
import difflib
import re
import typing
import time
import math
import io
import traceback
import config

"""
This is a super rudimentary flame bot
The image recognition could be vastly improved, and tess should be trained on the correct fonts to improve accuracy
There is a lot of unused stuff in here, just to remind me of what I have tried and ideas for improvement

TODO:
new number detection:
1) contour stat lines
2) pattern match stat lines
3) kernel for numbers

Level detection:
1) pattern match level
2) kernel for numbers

Tooltip: UI_003.wz/UIToolTip.img/Item


"""
class Flames(commands.Cog):

    def __init__(self, bot):

        self.bot = bot
        self.calc = FlameCalc.FlameCalc()

        self.statMap = {
            "str" : FlameCalc.Stats.STR,
            "dex" : FlameCalc.Stats.DEX,
            "int" : FlameCalc.Stats.INT,
            "luk" : FlameCalc.Stats.LUK,
            "attack power" : FlameCalc.Stats.ATTACK,
            "magic attack" : FlameCalc.Stats.MAGIC_ATTACK,
            "defense" : FlameCalc.Stats.DEF,
            "max hp" : FlameCalc.Stats.HP,
            "max mp" : FlameCalc.Stats.MP,
            "speed" : FlameCalc.Stats.SPEED,
            "jump" : FlameCalc.Stats.JUMP,
            "all stats" : FlameCalc.Stats.ALL_STAT,
            "boss damage" : FlameCalc.Stats.BOSS,
            "damage" : FlameCalc.Stats.DMG,
        }

        self.level = ([0, 128, 128], [0, 255, 255])
        self.star = ([128, 128, 0], [255, 255, 0])
        self.flame = ([0, 250, 250], [0, 255, 255])
        self.flame2 = ([0, 100, 100], [15, 255, 224]) ##0, 255, 204

        ##My windows env doesnt have tess on the path
        if(os.name == "nt"):
            tess.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        

    #@commands.command()
    async def flame(self, ctx, level : int = -1):

        if(len(ctx.message.attachments) == 0):
            await ctx.reply("Please attach an image of an item.")
            return

        async with ctx.channel.typing():
            attach = await ctx.message.attachments[0].read()
            img = cv.imdecode(np.asarray(bytearray(attach), dtype=np.uint8), 1)

            level 
            ret, flames = self.parseImage(img, level=level)
            if(ret):
                emb = self.buildFlameEmbed(flames)
                await ctx.reply("", embed=emb)
            else:
                await ctx.reply(flames)

    

    @commands.command()
    async def flame(self, ctx, level : int = -1):
        if(ctx.channel.id != config.BOT_COMMANDS and ctx.guild.id != config.DEV_GUILD):
            print(ctx.channel.id, ctx.guild.id)
            return
        if(len(ctx.message.attachments) == 0):
            await ctx.reply("Please attach an image of an item.")
            return
        async with ctx.channel.typing():
            try:
                attach = await ctx.message.attachments[0].read()
                img = cv.imdecode(np.asarray(bytearray(attach), dtype=np.uint8), 1)

                lines, inc, flameScores, imgs = await self.parseImage2(img, level=level)

                if(lines == {}):
                    await ctx.reply("No flames found, try a different image.")
                    return

                files = []
                for i, img in enumerate(imgs):
                    success, buf = cv.imencode(".png", img)
                    debugBuffer = io.BytesIO(buf)
                    # files.append(discord.File(debugBuffer, filename=f"debug{i}.png"))
                emb = self.buildFlameEmbed2(lines, flameScores, inc)
                await ctx.reply("", embed=emb, files=files)
                #await ctx.reply("", embed=parsed)
            except Exception as e:
                print(e)
                print(traceback.print_exc())
                await ctx.reply("Unknown error occoured, try a different image")


    async def matchImageScale(self, img, templatePath, label="", canny=True):
        template = cv.imread(templatePath)
        baseH, baseW = template.shape[:2]

        edges = cv.Canny(img.copy(), 150, 200)
        #cv.imwrite(f"templates/edges_{label}.png", edges)

        bestFit = None
        bestCrop = None
        bounds = None
        bestCanny = None
        bestScale = 1

        for scale in np.linspace(0.5, 2.0, 7):
            # resize template to a scale
            templateR = cv.resize(template.copy(), (int(baseW * scale), int(baseH * scale)), cv.INTER_CUBIC)
            ret, templateR = cv.threshold(templateR, 75, 255, cv.THRESH_BINARY)
            templateR = cv.Canny(templateR.copy(), 150, 200)
            #cv.imwrite(f"templates/template_{label}_{scale}.png", templateR)
            tH, tW = templateR.shape[:2]
            
            # make sure our template isn't larger than the matcher
            if(img.shape[1] <= tW or img.shape[0] <= tH):
                continue
            
            # Find best match
            matches = cv.matchTemplate(edges, templateR, cv.TM_CCOEFF)
            minVal, maxVal, minLoc, maxLoc = cv.minMaxLoc(matches)

            #If this is our best overall match, save it
            if(bestFit == None or bestFit[0] < maxVal):
                bestFit = (maxVal, maxLoc, scale)
                bestCrop = img.copy()[maxLoc[1]:maxLoc[1]+tH, maxLoc[0]:maxLoc[0]+tW]
                bestCanny = edges.copy()[maxLoc[1]:maxLoc[1]+tH, maxLoc[0]:maxLoc[0]+tW]
                bounds = (maxLoc[1], maxLoc[1]+tH, maxLoc[0], maxLoc[0]+tW)
                bestScale = scale

        #print(f"Matched {templatePath} at scale {bestScale} with certainty {bestFit[0]}")
        #print(f"Matched bounds {tH}, {tW}")
        #cv.imwrite(f"templates/crop_{label}.png", bestCrop)
        #cv.imwrite(f"templates/canny_{label}.png", bestCanny)
        return(bestCrop, bestFit, bestScale, bounds)


    def buildFlameEmbed(self, flames):
        emb = discord.Embed()
        emb.title = "Flame Stats"
        emb.set_footer(text="WIP")
        emb.color = discord.Color.purple()
        if(len(flames) == 1):
            flamesText = ", ".join("T{0} {1}".format(flame.tier, " + ".join(flame.stats)) for flame in flames[0])
            emb.add_field(name="Flame", value=flamesText)
        else:
            flamesText = ["• " + ", ".join("T{0} {1}".format(flame.tier, " + ".join(flame.stats)) for flame in x) for x in flames]
            emb.add_field(name="Possible Flames", value="\n".join(flamesText))
        return(emb)

    def buildFlameEmbed2(self, flameDict, flameScores, inc):
        emb = discord.Embed()
        emb.title = "Flame Stats"
        emb.set_footer(text="by lostara", icon_url="https://cdn.discordapp.com/emojis/947022653082988544.png")
        emb.color = discord.Color.purple()
        #emb.set_thumbnail(url="https://cdn.discordapp.com/emojis/743215456839532604.png")
        emb.set_thumbnail(url="https://cdn.discordapp.com/emojis/724484702769119232.png")
        for level, flames in flameDict.items():
            titleText = "Level {0}".format(level)
            if inc != -1:
                titleText = "Levels {0}-{1}".format(level, level+inc-1)
            if(len(flames) == 1):
                flamesText = ", ".join("T{0} {1}".format(flame.tier, " + ".join(flame.stats)) for flame in flames[0])
                emb.add_field(name=titleText, value=flamesText, inline=False)
            else:
                flamesText = ["• " + ", ".join("T{0} {1}".format(flame.tier, " + ".join(flame.stats)) for flame in x) for x in flames]
                emb.add_field(name=titleText, value="\n".join(flamesText), inline=False)

        if level == 200:
            flameScoresText = []
            for stat, score in flameScores.items():
                if(score != 0):
                    flames = math.ceil(self.calc.scoreOverFast(score))
                    flameScoresText.append("• {0}: {1} ({2} flames)".format(stat, score, flames))
            if len(flameScoresText) > 0:
                emb.add_field(name="Flame Scores", value="{0}\n\nFlames estimates are for Misty Island".format("\n".join(flameScoresText)))
        else:
            flameScoreText =  "\n".join("• {0}: {1}".format(k, v) for k, v in flameScores.items() if v != 0)
            if len(flameScoreText) > 0:
                emb.add_field(name="Flame Scores", value=flameScoreText)
        return(emb)


    @commands.command()
    async def flamesfor(self, ctx, score : int):
        if(ctx.channel.id != config.BOT_COMMANDS and ctx.guild.id != config.DEV_GUILD):
            print(ctx.channel.id, ctx.guild.id)
            return
        async with ctx.channel.typing():
            flames = self.calc.scoreOverFast(score)

            await ctx.reply("Getting a score of {0} or greater on your totem takes an estimated {1:,} flames.".format(score, math.ceil(flames)))


    def calculateFlameScore(self, flameDict):
        ## https://drive.google.com/file/d/1NK4ny-zF2mu8DzfK1QuyFlVmB961JXJm/view
        attackRatio = 2.5
        secondaryRatio = 1/15
        allStatRatio = 9

        ##Indicates we have a weapon, so dont calculate flame atk in flame score
        if(flameDict.get(FlameCalc.Stats.ATTACK, 0) > 7 or flameDict.get(FlameCalc.Stats.MAGIC_ATTACK, 0) > 7 or flameDict.get(FlameCalc.Stats.BOSS, 0) != 0 or flameDict.get(FlameCalc.Stats.DMG, 0) != 0):
            attackRatio = 0

        flames = { "STR" : 0,
                "DEX" : 0,
                "INT" : 0,
                "LUK" : 0 }
        if(FlameCalc.Stats.STR in flameDict):
            flames["STR"] = math.floor(flameDict.get(FlameCalc.Stats.STR, 0) + (flameDict.get(FlameCalc.Stats.DEX, 0) * secondaryRatio) + (flameDict.get(FlameCalc.Stats.ATTACK, 0) * attackRatio) + (flameDict.get(FlameCalc.Stats.ALL_STAT, 0) * allStatRatio))
        if(FlameCalc.Stats.DEX in flameDict):
            flames["DEX"] = math.floor(flameDict.get(FlameCalc.Stats.DEX, 0) + (flameDict.get(FlameCalc.Stats.STR, 0) * secondaryRatio) + (flameDict.get(FlameCalc.Stats.ATTACK, 0) * attackRatio) + (flameDict.get(FlameCalc.Stats.ALL_STAT, 0) * allStatRatio))
        if(FlameCalc.Stats.INT in flameDict):
            flames["INT"] = math.floor(flameDict.get(FlameCalc.Stats.INT, 0) + (flameDict.get(FlameCalc.Stats.LUK, 0) * secondaryRatio) + (flameDict.get(FlameCalc.Stats.MAGIC_ATTACK, 0) * attackRatio) + (flameDict.get(FlameCalc.Stats.ALL_STAT, 0) * allStatRatio))
        if(FlameCalc.Stats.LUK in flameDict):
            flames["LUK"] = math.floor(flameDict.get(FlameCalc.Stats.LUK, 0) + (flameDict.get(FlameCalc.Stats.DEX, 0) * secondaryRatio) + (flameDict.get(FlameCalc.Stats.ATTACK, 0) * attackRatio) + (flameDict.get(FlameCalc.Stats.ALL_STAT, 0) * allStatRatio))

        print(flames)

        return(flames)


    async def parseImage2(self, img, level = -1):

        ## Get greyscale image for processing
        imgGrey = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        ## Creates a resized copy of the input image for drawing on and using as debug output
        img2 = cv.resize(img.copy(), (img.shape[1] * 2, img.shape[0] * 2), interpolation = cv.INTER_CUBIC)

        ret, cropImg = cv.threshold(imgGrey, 75, 255, cv.THRESH_BINARY)
        ## Match top of stats portion
        crop1, fit1, scale1, bounds1 = await self.matchImageScale(imgGrey, "assets/normal.png", label="top")
        ## Crop top of stats down to the bottom of the page
        cleanedGreyCrop = cropImg.copy()[bounds1[0]:, bounds1[2]:bounds1[3]]
        ## Match bottom of stats portion
        crop2, fit2, scale2, bounds2 = await self.matchImageScale(cleanedGreyCrop, "assets/bottom.png", label="bot")

        ## Use two matches to crop stats 
        flameBounds = list(bounds1)
        flameBounds[1] = flameBounds[0] + bounds2[0]
        flameBounds[0] = bounds1[1]

        crop3, fit3, scale3, bounds3 = await self.matchImageScale(cropImg, "assets/reqLEV3.png", label="level")

        ##offset is 53
        levelOffset = int(25 * scale3)
        levelCrop = cropImg[bounds3[0]:bounds3[1], bounds3[2]:bounds1[3]]

        img = img[flameBounds[0]:flameBounds[1], flameBounds[2]:flameBounds[3]]
        imgGrey = imgGrey[flameBounds[0]:flameBounds[1], flameBounds[2]:flameBounds[3]]

        ## Clean up images
        cleanedGrey = self.cleanImage(imgGrey, thresh=75)
        cleanedFlame = self.cleanFlame(img)
        cleanedLevel = self.cleanLevel2(levelCrop)  

        #cv.imwrite("templates/cleanedGrey.png", cleanedGrey)
        #cv.imwrite("templates/cleanedFlame.png", cleanedFlame)
        #cv.imwrite("templates/cleanedLevel.png", cleanedLevel)

        ## Create cropped copy of debug image for output
        img3 = img.copy() #[flameBounds[0]:flameBounds[1], flameBounds[2]:flameBounds[3]]

        # blur horizontally for contour detection
        kernel = cv.getStructuringElement(cv.MORPH_RECT, (int(460 * 1/2), int(8 * 1/2)))
        morph = cv.morphologyEx(cleanedGrey, cv.MORPH_DILATE, kernel)

        # find contours
        contours = cv.findContours(morph, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]

        #cv.drawContours(image=img3, contours=contours, contourIdx=-1, color=(0, 255, 0), thickness=2, lineType=cv.LINE_AA)

        fullRes = []
        flameRes = []
        contourImg = img3.copy()
        for c in contours:

            # Grab the bounding box for each contour
            box = cv.boundingRect(c)
            x, y, w, h = box

            if h < 10:
                continue
            
            ## debug output
            cv.rectangle(contourImg, (x, y), (x+w, y+h), (255, 255, 255), 1)

            #print(f"Height: {h}")
            # Crop and OCR just the current line plus a couple pixels to improve OCR
            crop = self.cropContour(x, y, w, h, cleanedGrey)
            cropF = self.cropContour(x, y, w, h, cleanedFlame)

            out = tess.image_to_string(crop)    ## Full stats
            outF = tess.image_to_string(cropF)  ## Flames
            
            # Clean data
            out = out.replace("\n", " ").strip()    ## Full stats
            out = out.replace("Oo", " 0 0 ")        ## Full stats

            outF = outF.replace("\n", " ").strip()  ## Flames
            outF = outF.replace("Oo", " 0 0 ")      ## Flames

            fullRes.append(out)
            flameRes.append(outF)

        ## zip full stats and flames togeter, and reverse so it is read top down
        lines = list(zip(fullRes, flameRes))
        lines.reverse()

        ## Snips out trailing data like potential, soul, charm data
        endData = len(lines)
        for i, line in enumerate(lines):
            print(f"{i}: {str(line)}")
            if any([x in " ".join(line).lower() for x in ["grants", "charm", "exp", "when", "first", "equipped", "potential"]]):
                endData = min(endData, i)
        lines = lines[:endData]

        ## Only a flame line if there is data in both the full stats and flames sections
        flames = [line for line in lines if line[1] != '']

        flameDict = {}
        baseDict = {}

        for flame in flames:
            match = re.match(r"([\w\s]+)", flame[0])            ## Matches leading char+space characters from main crop (stat)
            match2 = re.findall(r"([\d]+)", flame[1])           ## Matches only numbers from flame crop (flame)
            match3 = re.findall(r"(?<![+\d])\d+", flame[0])     ## Matches the first number without a leading + from main crop (base stat)
            if match and len(match2) > 0 and len(match3) > 0:
                ## Difflib to find closest stat match (in case of OCR issues)
                stat = difflib.get_close_matches(match.group(0).strip().lower(), self.statMap.keys(), cutoff=0)
                if(len(stat) > 0):
                    flameDict[self.statMap[stat[0]]] = int(match2[0])        ## Update flame dictionary
                    ## Set base dict to 0 if atk/matk less than 10, so we don't calculate weapon varients of those stats
                    if stat[0] in ["attack power", "magic attack"] and int(match2[0]) < 10:
                        baseDict[self.statMap[stat[0]]] = 0                         ## Update base stat dictionary (non weapon atk/matk)
                    else:
                        baseDict[self.statMap[stat[0]]] = int(match3[0])            ## Update base stat dictionary (rest)
                else:
                    print("Invalid Stats {0}".format(flame))
                    return(False, "Invalid stat {0}".format(flame[0]))
            else:
                print(f"Flame matching failed:\nInput: {str(flame)}\nMatch: {match}\nMatch2: {match2}\nMatch3: {match3}")


        print(flameDict)
        print(baseDict)

        flameScores = self.calculateFlameScore(flameDict)

        #calc = FlameCalc.FlameCalc()
        validFlames = {}
        inc = -1
        if level == -1:
            #cv.imwrite("levelcrop.png", cleanedLevel)
            levelOcr = tess.image_to_string(cleanedLevel)
            print(f"levelOcr {levelOcr}")
            levels = re.findall(r"([\d]+)", levelOcr)

            for level in levels:
                res = self.calc.calcFlame(flameDict, baseDict, int(level))
                if len(res) > 0:
                    validFlames[level] = res

            if validFlames == {}:
                inc = 20
                if any(x in list(flameDict.keys()) for x in [FlameCalc.Stats.MP, FlameCalc.Stats.HP]):
                    inc = 10
                for level in range(0, 250, inc):
                    res = self.calc.calcFlame(flameDict, baseDict, level)
                    if len(res) > 0:
                        validFlames[level] = res
        
        ## User defined level
        else:
            res = self.calc.calcFlame(flameDict, baseDict, int(level))
            if len(res) > 0:
                validFlames[level] = res


        return(validFlames, inc, flameScores, (img3, morph, contourImg, cleanedGrey, cleanedFlame))


    def cropContour(self, x, y, w, h, img):
        imgW = img.shape[1]
        imgH = img.shape[0]

        e = int(h * 0.2) 

        y1 = max(0, y-e)
        y2 = min(imgH, y+h+e)

        #print(f"Shape: {imgH}, {imgW}\nCrop: {y1}, {y2}, {x}, {x+w}")
        return(img[y1:y2, x:x+w])

    def cleanImage(self, img, thresh=95):
        img2 = img.copy()
        img2 = cv.resize(img2, (img2.shape[1] * 2, img2.shape[0] * 2), interpolation = cv.INTER_CUBIC)
        ret, img2 = cv.threshold(img2, thresh, 255, cv.THRESH_BINARY)
        return(img2)


    def cleanLevel2(self, img, thresh=95):
        img2 = img.copy()
        img2 = cv.resize(img2, (img2.shape[1] * 3, img2.shape[0] * 3), interpolation = cv.INTER_CUBIC)
        #ret, img2 = cv.threshold(img2, thresh, 255, cv.THRESH_BINARY)
        kernel = np.ones((5, 5), np.float32)/30
        img2 = cv.filter2D(img2, -1, kernel)
        return(img2)


    def cleanFlame(self, img):
        ##0, 255, 204
        #flame = ([0, 80, 80], [20, 255, 220]) OLD, PERFORMS WORSE SO FAR
        flame = ([0, 60, 60], [20, 255, 220]) ##0, 255, 204
        flameImg = img.copy()
        flameImg = cv.resize(flameImg, (flameImg.shape[1] * 2, flameImg.shape[0] * 2), interpolation = cv.INTER_CUBIC)

        mask = cv.inRange(flameImg, np.array(flame[0], dtype = "uint8"), np.array(flame[1], dtype = "uint8"))
        flameImg = cv.bitwise_and(flameImg, flameImg, mask=mask)

        ret, flameImg = cv.threshold(flameImg, 100, 255, cv.THRESH_BINARY)
        return(flameImg)


#async def setup(bot: commands.Bot) -> None:
#    await bot.add_cog(Flames(bot))

def setup(bot):
    bot.add_cog(Flames(bot))
