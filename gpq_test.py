import discord
from discord.ext import commands, tasks

import cv2 as cv
import numpy as np
import pytesseract as tess
import io


class GPQ_Test(commands.Cog):
    
    def __init__(self, bot):
        self.bot = bot

    async def readScores(self, im, fit):

        scale = fit[2]

        SCALE_FACTOR = 2

        # If the locating worked, these are the hard coords of the information we want
        # We do need to scale it by the factor we determined the input was scaled by.
        X, Y = (int(48 * scale), int(87 * scale))
        X2, Y2 = (int(503 * scale), int(502 * scale))

        im = im[Y:Y2, X:X2]

        im2 = cv.resize(im, (im.shape[1] * SCALE_FACTOR, im.shape[0] * SCALE_FACTOR), interpolation = cv.INTER_CUBIC)
        gray = cv.cvtColor(im, cv.COLOR_BGR2GRAY)

        # clean image
        ret, thresh = cv.threshold(gray, 125, 255, cv.THRESH_BINARY)
        thresh = cv.resize(thresh, (thresh.shape[1] * SCALE_FACTOR, thresh.shape[0] * SCALE_FACTOR), interpolation = cv.INTER_CUBIC)

        # blur horizontally for contour detection
        kernel = cv.getStructuringElement(cv.MORPH_RECT, (int(460 * SCALE_FACTOR/2), int(14 * SCALE_FACTOR/2)))
        morph = cv.morphologyEx(thresh, cv.MORPH_DILATE, kernel)

        # find contours
        contours = cv.findContours(morph, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]

        # Invert colors (I think tess likes black on white better?)
        thresh = cv.bitwise_not(thresh)

        # Sharpen
        # kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        # thresh = cv.filter2D(thresh, -1, kernel)

        # Iterate over contours (effectively parsing each line individually)
        res = []
        print("=============================================")
        for c in contours:

            # Grab the bounding box for each contour
            box = cv.boundingRect(c)
            x, y, w, h = box
            cv.rectangle(im2, (x, y), (x+w, y+h), (0, 0, 255), 1)

            # Crop and OCR just the current line
            crop = thresh[y:y+h, x:x+w]
            out = tess.image_to_string(crop)
            
            # Clean data
            out = out.replace("\n", " ").strip()
            out = out.replace("Oo", " 0 0 ")
            s = [x for x in out.split(" ") if not x == ""]


            # Convert trailing entries to integers until we find one that cant be converted
            for i in range(len(s) - 1, 0, -1):
                if(not isInt(s[i])):
                    break
                else:
                    
                    s[i] = int(s[i].replace(",", ""))

            # Pad list with 0s until we reach the 5 scores we want. Tesseract doesn't read trailing 0s, so this is how we account for them        
            s += [0 for j in range(4 - (len(s) - 1 - i))]
            print(s)
            print("=============================================")

            res.append(s)
        
        return(res, im2)

    async def matchGuildUI(self, img):
        template = cv.imread("assets/member_participation_status.png")
        baseH, baseW = template.shape[:2]

        edges = cv.Canny(img.copy(), 150, 200)

        bestFit = None
        bestCrop = None

        for scale in np.linspace(0.5, 2.0, 7):
            # resize template to a scale
            templateR = cv.resize(template.copy(), (int(baseW * scale), int(baseH * scale)), cv.INTER_CUBIC)
            templateR = cv.Canny(templateR.copy(), 150, 200)
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

        cv.imwrite("crop.png", bestCrop)


        return(bestCrop, bestFit)

    @commands.command()
    async def testParse(self, ctx):
        if(len(ctx.message.attachments) > 0):
            attachment = await ctx.message.attachments[0].read()
            img = cv.imdecode(np.asarray(bytearray(attachment), dtype=np.uint8), cv.IMREAD_UNCHANGED)
            
            crop, fit = await self.matchGuildUI(img)
            results, debugImage = await self.readScores(crop, fit)

            success, buf = cv.imencode(".png", debugImage)
            debugBuffer = io.BytesIO(buf)

            resultsR = results[::-1]
            resultsStr = "\n".join(str(x) for x in resultsR)
            response = "Scale: `{scale}` Certainty: `{cert}`\n```{resultsStr}```".format(scale=fit[2], cert=fit[0], resultsStr=resultsStr)

            await ctx.reply(response, files=[discord.File(debugBuffer, filename="debug.png")])


    

def isInt(i):
    try:
        i = i.replace(",", "")
        i = int(i)
        return(True)
    except:
        return(False)

def setup(bot):
    bot.add_cog(GPQ_Test(bot))