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
import io
import traceback

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
        self.flameCalc = FlameCalc.FlameCalc()

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
    @commands.is_owner()
    async def flame2(self, ctx, level : int = -1):
        if(len(ctx.message.attachments) == 0):
            await ctx.reply("Please attach an image of an item.")
            return

        async with ctx.channel.typing():
            try:
                attach = await ctx.message.attachments[0].read()
                img = cv.imdecode(np.asarray(bytearray(attach), dtype=np.uint8), 1)

                lines, imgs = await self.parseImage2(img, level=level)


                files = []
                for i, img in enumerate(imgs):
                    success, buf = cv.imencode(".png", img)
                    debugBuffer = io.BytesIO(buf)
                    # files.append(discord.File(debugBuffer, filename=f"debug{i}.png"))

                await ctx.reply("\n".join([str(x) for x in lines]), files=files)
                #await ctx.reply("", embed=parsed)
            except Exception as e:
                print(e)
                print(traceback.print_exc())


    async def matchImageScale(self, img, templatePath, label=""):
        template = cv.imread(templatePath)
        template = cv.resize(template, (template.shape[1] * 2, template.shape[0] * 2), interpolation = cv.INTER_CUBIC)
        baseH, baseW = template.shape[:2]
        #print(f"Base bounds: {baseH}, {baseW}")

        edges = cv.Canny(img.copy(), 150, 200)
        #cv.imwrite(f"templates/edges_{label}.png", edges)

        bestFit = None
        bestCrop = None
        bounds = None
        #bestCanny = None
        #bestScale = 1

        for scale in np.linspace(0.5, 2.0, 7):
            # resize template to a scale
            templateR = cv.resize(template.copy(), (int(baseW * scale), int(baseH * scale)), cv.INTER_CUBIC)
            #ret, templateR = cv.threshold(templateR, 75, 255, cv.THRESH_BINARY)
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
                #bestCanny = edges.copy()[maxLoc[1]:maxLoc[1]+tH, maxLoc[0]:maxLoc[0]+tW]
                bounds = (maxLoc[1], maxLoc[1]+tH, maxLoc[0], maxLoc[0]+tW)
                #bestScale = scale

        #print(f"Matched {templatePath} at scale {scale} with certainty {bestFit[0]}")
        #print(f"Matched bounds {tH}, {tW}")
        #cv.imwrite(f"templates/crop{label}.png", bestCrop)
        #cv.imwrite(f"templates/canny{label}.png", bestCanny)
        return(bestCrop, bestFit, bounds)


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


    async def parseImage2(self, img, level = -1):

        ## Get greyscale image for processing
        imgGrey = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        ## Creates a resized copy of the input image for drawing on and using as debug output
        img2 = cv.resize(img.copy(), (img.shape[1] * 2, img.shape[0] * 2), interpolation = cv.INTER_CUBIC)

        ## Clean up images
        cleaned = self.cleanImage(img)
        cleanedGrey = self.cleanImage(imgGrey, thresh=75)
        cleanedFlame = self.cleanFlame(img)
        cleanedLevel = self.cleanLevel(img)       

        cv.imwrite(f"templates/grey.png", imgGrey)

        ## TODO: DO MATCHING BEFORE RESIZING
        ## Match top of stats portion
        crop1, fit2, bounds1 = await self.matchImageScale(cleanedGrey, "assets/normal.png", label="top")
        ## Crop top of stats down to the bottom of the page
        cleanedGreyCrop = cleanedGrey.copy()[bounds1[0]:, bounds1[2]:bounds1[3]]
        cv.imwrite(f"templates/cleanedGreyCrop.png", cleanedGreyCrop)
        ## Match bottom of stats portion
        crop2, fit2, bounds2 = await self.matchImageScale(cleanedGreyCrop, "assets/bottom.png", label="bot")

        ## Use two matches to crop stats 
        flameBounds = list(bounds1)
        flameBounds[1] = flameBounds[0] + bounds2[0]
        flameBounds[0] = bounds1[1]

        ## Create cropped copy of debug image for output
        img3 = img2.copy()[flameBounds[0]:flameBounds[1], flameBounds[2]:flameBounds[3]]
        ## Crop isolated flames to stats portion
        flame3 = cleanedFlame.copy()[flameBounds[0]:flameBounds[1], flameBounds[2]:flameBounds[3]]
        ## Crop full stats to stats portion
        grey3 = cleanedGrey.copy()[flameBounds[0]:flameBounds[1], flameBounds[2]:flameBounds[3]]

        # blur horizontally for contour detection
        kernel = cv.getStructuringElement(cv.MORPH_RECT, (int(460 * 1/2), int(8 * 1/2)))
        morph = cv.morphologyEx(grey3, cv.MORPH_DILATE, kernel)

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
            #crop = grey3[y-2:y+h+2, x:x+w]      ## Full stats
            crop = self.cropContour(x, y, w, h, grey3)
            cropF = self.cropContour(x, y, w, h, flame3)
            #cropF = flame3[y-2:y+h+2, x:x+w]    ## Flames

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
                    baseDict[self.statMap[stat[0]]] = int(match3[0])         ## Update base stat dictionary
                else:
                    print("Invalid Stats {0}".format(flame))
                    return(False, "Invalid stat {0}".format(flame[0]))
            else:
                print(f"Flame matching failed:\nInput: {str(flame)}\nMatch: {match}\nMatch2: {match2}\nMatch3: {match3}")


        print(flameDict)
        print(baseDict)

        calc = FlameCalc.FlameCalc()
        validFlames = calc.calcFlame(flameDict, baseDict, 200)


        return(validFlames, (img3, morph, contourImg, grey3, flame3))


    def cropContour(self, x, y, w, h, img):
        imgW = img.shape[1]
        imgH = img.shape[0]

        e = int(h * 0.2) 

        y1 = max(0, y-e)
        y2 = min(imgH, y+h+e)

        #print(f"Shape: {imgH}, {imgW}\nCrop: {y1}, {y2}, {x}, {x+w}")
        return(img[y1:y2, x:x+w])



    def parseImage(self, img, level = -1):

        #print(img.shape)
        imgGrey = cv.cvtColor(img, cv.COLOR_BGR2GRAY)

        start = time.time()

        cleaned = self.cleanImage(img)
        cleanedGrey = self.cleanImage(imgGrey, thresh=75)
        cleanedFlame = self.cleanFlame(img)
        cleanedLevel = self.cleanLevel(img)

        levelFrame = tess.image_to_data(cleanedLevel, output_type=tess.Output.DATAFRAME)

        croppedLevel = self.cropLevel(cleanedLevel, levelFrame)

        data = tess.image_to_data(cleanedGrey, output_type=tess.Output.DICT)

        end = time.time()
        print("initial processing took {0}s".format(end - start))


        statsTopLeft = (0, 0)
        dataText = data["text"]
        m = difflib.get_close_matches("Type", dataText, cutoff=0.5)
        #print(dataText)
        if(m):
            idx = dataText.index(m[0])
            statsTopLeft = (data["top"][idx], data["left"][idx])
        else:
            print("Unable to find stats")
            return(False, "Unable to locate stats")

        start2 = time.time()

        croppedStats = cleaned.copy()[statsTopLeft[0]:,:]
        croppedFlameStats = cleanedFlame.copy()[statsTopLeft[0]:,:]

        ##Crop stats
        statFrame = tess.image_to_data(croppedStats, output_type=tess.Output.DATAFRAME)
        statFrame = statFrame.copy()[~statFrame.text.isnull()]
        
        ##Crop flames
        flameFrame = tess.image_to_data(croppedFlameStats, output_type=tess.Output.DATAFRAME)
        flameFrame = flameFrame.copy()[~flameFrame.text.isnull()]

        ##Level Frame
        levelData = tess.image_to_data(croppedLevel, output_type=tess.Output.DICT)

        end2 = time.time()

        print("Seconary Processing Took {0}s".format(end2 - start2))

        flames = []
        base = []
        flameFrame["text"] = flameFrame["text"].astype(str)
        
        for i, row in flameFrame.iterrows():
            if(re.search(r"\+(\d+)%?", row["text"])):
                top = statFrame.loc[statFrame['top'].sub(row["top"]).abs().idxmin()]["top"]
                statRow = statFrame.loc[(abs(statFrame["top"] - top) < 5) & (statFrame["left"] < row["left"] - 1)]
                
                statText = re.findall(r"([\w ]+)", " ".join(statRow["text"]))[0]
                statValue = int(re.findall(r"(\d+)", row["text"])[-1])
                
                m = re.search(r"(\d+)", statRow.iloc[-1]["text"])
                
                baseValue = 0
                if(m):
                    baseValue = int(m.group(1))
                flames.append([statText, statValue, baseValue])
        

        flameDict = {}
        baseDict = {}

        for flame in flames:
            stat = difflib.get_close_matches(flame[0].lower(), self.statMap.keys(), cutoff=0)
            if(len(stat) > 0):
                flameDict[self.statMap[stat[0]]] = flame[1]
                baseDict[self.statMap[stat[0]]] = flame[2]
            else:
                print("Invalid Stats {0}".format(flame))
                return(False, "Invalid stat {0}".format(flame[0]))
        

        levelText = [x for x in levelData["text"] if not x == ""]
        if(level == -1):
            level = 0
            m = difflib.get_close_matches("LEV:", levelText)
            if(len(m) == 0):
                print("No LEV matches")
                return(False, "Unable to automatically determine level.\nFlame bot struggles with this, and you can manually specify the level with `!flame <level>`")
            idx = levelText.index(m[0])
            if(idx == len(levelText) - 1):
                print("No numbers")
                return(False, "Unable to automatically determine level.\nFlame bot struggles with this, and you can manually specify the level with `!flame <level>`")
            m = re.findall(r"(\d+)", " ".join(levelText[idx:]))
            print(" ".join(levelText[idx:]))
            if(m):
                level = int(m[0])
                print("Level: {0}".format(m[0]))
            else:
                print("re match failed")
                return(False, "Unable to automatically determine level.\nFlame bot struggles with this, and you can manually specify the level with `!flame <level>`")


        if(level != 0):
            print("Level:{0}\nBase Stats: {1}\nFlame Stats: {2}".format(level, str(baseDict), str(flameDict)))
            calc = FlameCalc.FlameCalc()
            validFlames = calc.calcFlame(flameDict, baseDict, level)
            return(True, validFlames)
        else:
            pass
        return(False, "Unknown error")

    def cleanImage(self, img, thresh=95):
        img2 = img.copy()
        img2 = cv.resize(img2, (img2.shape[1] * 2, img2.shape[0] * 2), interpolation = cv.INTER_CUBIC)
        ret, img2 = cv.threshold(img2, thresh, 255, cv.THRESH_BINARY)
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


    def cleanLevel(self, img):
        levelImg = img.copy()
        mask = cv.inRange(levelImg, np.array([0, 203, 253], dtype = "uint8"), np.array([0, 206, 255], dtype = "uint8"))
        ret, levelImg = cv.threshold(levelImg, 127, 255, cv.THRESH_BINARY)
        levelImg = cv.bitwise_and(levelImg, levelImg, mask=mask)
        levelImg = cv.resize(levelImg, (levelImg.shape[1] * 2, levelImg.shape[0] * 2), interpolation = cv.INTER_CUBIC)
        return(levelImg)

    def cleanlevel2(self, img):
        levelImg = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        bbox = cv.boundingRect(levelImg)
        x, y, w, h = bbox
        w = levelImg.shape[::-1][0]
        h = levelImg.shape[::-1][1]
        print(bbox)
        fg = levelImg[y:y+h, x:x+w]
        cv.imshow("a", fg)
        cv.waitKey(0)
        return(fg)

    def cropLevel(self, img, data):
        data = data.copy()[~data.text.isnull()]
        data.loc[:, "right"] = data.apply(lambda row: row.left + row.width, axis=1)
        data.loc[:, "bottom"] = data.apply(lambda row: row.top + row.height, axis=1)
        (x, y, x2, y2) = data["left"].min(), data["top"].min(), data["right"].max(), data["bottom"].max()

        w = img.shape[1]
        h = img.shape[0]
        wMod = int(abs(x2 - x) * 0.25)
        hMod = int(abs(y2 - y) * 0.25)
        x, y, x2, y2 = max(x - wMod, 0), max(y - hMod, 0), min(x2 + wMod, w), min(y2 + hMod, h)

        img2 = img.copy()[y:y2, x:x2]
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        img2 = cv.filter2D(img2, -1, kernel)

        return(img2)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Flames(bot))