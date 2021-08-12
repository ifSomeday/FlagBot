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

"""
This is a super rudimentary flame bot
The image recognition could be vastly improved, and tess should be trained on the correct fonts to improve accuracy
There is a lot of unused stuff in here, just to remind me of what I have tried and ideas for improvement
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
        

    @commands.command()
    async def flame(self, ctx, *text : str):

        if(len(ctx.message.attachments) == 0):
            await ctx.reply("Please attach an image of an item.")
            return

        async with ctx.channel.typing():
            attach = await ctx.message.attachments[0].read()
            img = cv.imdecode(np.asarray(bytearray(attach), dtype=np.uint8), 1)

            ret, flames = self.parseImage(img)
            if(ret):
                emb = self.buildFlameEmbed(flames)
                await ctx.reply("", embed=emb)
            else:
                pass

    
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

    def parseImage(self, img):

        print(img.shape)
        imgGrey = cv.cvtColor(img, cv.COLOR_BGR2GRAY)

        cleaned = self.cleanImage(img)
        cleanedGrey = self.cleanImage(imgGrey)
        cleanedFlame = self.cleanFlame(img)
        cleanedLevel = self.cleanLevel(img)

        levelFrame = tess.image_to_data(cleanedLevel, output_type=tess.Output.DATAFRAME)
        croppedLevel = self.cropLevel(cleanedLevel, levelFrame)

        data = tess.image_to_data(cleanedGrey, output_type=tess.Output.DICT)

        statsTopLeft = (0, 0)

        ##TODO: difflib to make this more reliable
        for i, line in enumerate(data["text"]):
            if("Type" in line):
                statsTopLeft = (data["top"][i], data["left"][i])

        if statsTopLeft == (0, 0):
            print("Unable to find stats")
            return(False, "Unable to find stats section")


        croppedStats = cleaned.copy()[statsTopLeft[0]:,:]
        croppedFlameStats = cleanedFlame.copy()[statsTopLeft[0]:,:]

        ##Crop stats
        statData = tess.image_to_data(croppedStats, output_type=tess.Output.DICT)
        statFrame = tess.image_to_data(croppedStats, output_type=tess.Output.DATAFRAME)
        statFrame = statFrame.copy()[~statFrame.text.isnull()]
        
        ##Crop flames
        flameData = tess.image_to_data(croppedFlameStats, output_type=tess.Output.DICT)
        flameFrame = tess.image_to_data(croppedFlameStats, output_type=tess.Output.DATAFRAME)
        flameFrame = flameFrame.copy()[~flameFrame.text.isnull()]

        ##Level Frame
        levelData = tess.image_to_data(croppedLevel, output_type=tess.Output.DICT)

        groups = statFrame.groupby(["level", "page_num", "block_num", "par_num", "line_num"])

        flames = []
        base = []
        for i, row in flameFrame.iterrows():
            if(re.match(r"\+(\d+)%?", row["text"])):
                top = statFrame.loc[statFrame['top'].sub(row["top"]).abs().idxmin()]["top"]
                statRow = statFrame.loc[(statFrame["top"] == top) & (statFrame["left"] < row["left"] - 1)]

                statText = re.findall(r"([\w ]+)", " ".join(statRow["text"]))[0]
                statValue = int(re.findall(r"(\d+)", row["text"])[0])

                m = re.search(r"(\d+)", statRow.iloc[-1]["text"])
                baseValue = 0
                if(m):
                    baseValue = int(m.group(1))
                flames.append([statText, statValue, baseValue])
        

        flameDict = {}
        baseDict = {}
        for flame in flames:
            stat = difflib.get_close_matches(flame[0].lower(), self.statMap.keys())
            flameDict[self.statMap[stat[0]]] = flame[1]
            baseDict[self.statMap[stat[0]]] = flame[2]
        

        levelText = [x for x in levelData["text"] if not x == ""]
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
        if(m):
            level = int(m[0])
            print("Level: {0}".format(m[0]))

        if(level != 0):
            calc = FlameCalc.FlameCalc()
            validFlames = calc.calcFlame(flameDict, baseDict, level)
            return(True, validFlames)
        else:
            pass
        return(False, "Unknown error")

    def cleanImage(self, img):
        img2 = cv.medianBlur(img, 1)
        img2 = cv.resize(img2, (img2.shape[1] * 3, img2.shape[0] * 3), interpolation = cv.INTER_CUBIC)
        ret, img2 = cv.threshold(img2, 95, 255, cv.THRESH_BINARY)
        return(img2)

    def cleanFlame(self, img):
        flame = ([0, 160, 130], [20, 255, 230]) ##0, 255, 204
        flameImg = img.copy()
        flameImg = cv.resize(flameImg, (flameImg.shape[1] * 3, flameImg.shape[0] * 3), interpolation = cv.INTER_CUBIC)
        mask = cv.inRange(flameImg, np.array(flame[0], dtype = "uint8"), np.array(flame[1], dtype = "uint8"))
        flameImg = cv.bitwise_and(flameImg, flameImg, mask=mask)
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


def setup(bot):
    bot.add_cog(Flames(bot))
