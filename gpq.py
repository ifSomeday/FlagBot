import discord
from discord.ext import commands, tasks

import cv2 as cv
import numpy as np
import pytesseract as tess
import io
import os
import difflib
from typing import List, Optional
import traceback
import aiohttp, aiofiles
import datetime
import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from discord import app_commands

import config


def isRightGuild():
    def predicate(ctx):
        return ctx.guild.id in [config.GPQ_GUILD, config.DEV_GUILD]
    return commands.check(predicate)


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

        #Resize and grayscale
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

        # Magic
        kernel = np.ones((5, 5), np.float32)/30
        thresh = cv.filter2D(thresh, -1, kernel)

        # Iterate over contours (effectively parsing each line individually)
        res = []
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
            i = 0
            for i in range(len(s) - 1, 0, -1):
                if(not isInt(s[i])):
                    break
                else:
                    
                    s[i] = int(s[i].replace(",", ""))

            # Pad list with 0s until we reach the 5 scores we want. Tesseract doesn't read trailing 0s, so this is how we account for them        
            s += [0 for j in range(4 - (len(s) - 1 - i))]

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
    @commands.is_owner()
    async def atest(self, ctx):
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


    #@app_commands.guilds(discord.Object(config.GPQ_GUILD))
    @commands.command()
    @commands.check_any(commands.has_guild_permissions(manage_guild=True), isRightGuild())
    async def addscores(self, ctx, debug: Optional[str]):
        try:
            gpqSync = self.bot.get_cog("GPQ_Sync")
            if gpqSync is not None:
                if(len(ctx.message.attachments) > 0):
                    for attachment in ctx.message.attachments:
                        a = await attachment.read()
                        img = cv.imdecode(np.asarray(bytearray(a), dtype=np.uint8), cv.IMREAD_UNCHANGED)

                        crop, fit = await self.matchGuildUI(img)
                        results, debugImage = await self.readScores(crop, fit)
                        resultsR = results[::-1]

                        success, buf = cv.imencode(".png", debugImage)
                        debugBuffer = io.BytesIO(buf)

                        added, warnings, errors = await gpqSync.addOcrData(resultsR)
                        out = f"Added {added} entries"
                        if len(warnings) > 0:
                            out += "\nWarnings:\n    {0}".format("\n    ".join(warnings))
                        if len(errors) > 0:
                            out += "\nErrors:\n    {0}".format("\n    ".join(errors))
                        if debug:
                            await ctx.reply(out, files=[discord.File(debugBuffer, filename="debug.png")])
                        else:
                            await ctx.reply(out)
                else:
                    await ctx.reply("Missing score screenshot")
            else:
                await ctx.reply("GPQ Sync not loaded, contact developer")
        except Exception as e:
            print(e)
            print(traceback.print_exc())    


    @app_commands.guilds(discord.Object(config.GPQ_GUILD), discord.Object(config.DEV_GUILD))
    @app_commands.command(name="graph", description="Displays a graph with the given user's past GPQ scores.")
    async def graph(self, ctx, ign:str, ign2: Optional[str]):
        try:
            if not await self.isInGpqChannel(ctx):
                return
            gpqSync = self.bot.get_cog("GPQ_Sync")
            if gpqSync is not None:
                scores = await gpqSync.getUserScores(ign)
                scores2 = []
                if ign2:
                    scores2 = await gpqSync.getUserScores(ign2)
                buf = await self.buildGraph(scores, ign, scores2=scores2, ign2=ign2)
                await ctx.response.send_message(file=discord.File(fp=buf, filename="graph.png"))
            else:
                await ctx.response.send_message("GPQ Sync not loaded, contact developer")
        except Exception as e:
            print(e)
            print(traceback.print_exc())


    @app_commands.guilds(discord.Object(config.GPQ_GUILD), discord.Object(config.DEV_GUILD))
    @app_commands.command(name="gpq", description="Returns the given user's scorecard, with stats about their GPQ scores.")
    async def gpq(self, ctx, ign:str):
        try:
            if not await self.isInGpqChannel(ctx):
                return
            gpqSync = self.bot.get_cog("GPQ_Sync")
            if gpqSync is not None:
                scores = await gpqSync.getUserScores(ign)
                ranking = await gpqSync.getRankingInfo(ign)
                emb, file = await self.buildScoreEmbed(ign, scores, ranking)
                if file == None:
                    await ctx.response.send_message(embed=emb)
                else:
                    await ctx.response.send_message(file=file, embed=emb)
            else:
                await ctx.response.send_message("GPQ Sync not loaded, contact developer")
        except Exception as e:
            print(e)
            print(traceback.print_exc())


    @app_commands.guilds(discord.Object(config.GPQ_GUILD), discord.Object(config.DEV_GUILD))
    @app_commands.command(name="topweek", description="Returns the top GPQ scores of the current week (default 10 scores).")
    async def topweek(self, ctx, n : Optional[int] = 10):
        try:
            if not await self.isInGpqChannel(ctx):
                return
            gpqSync = self.bot.get_cog("GPQ_Sync")
            if gpqSync is not None:
                scores = await gpqSync.getWeekTopScores()
                emb, file = await self.buildTopEmbed(scores, gpqSync, week=True, title=f"Top {n} GPQ Scores ({scores[0][2]})", numScores=n)
                if file == None:
                    await ctx.response.send_message(embed=emb)
                else:
                    await ctx.response.send_message(file=file, embed=emb)
            else:
                await ctx.response.send_message("GPQ Sync not loaded, contact developer")
        except Exception as e:
            print(e)
            print(traceback.print_exc())

    
    @app_commands.guilds(discord.Object(config.GPQ_GUILD), discord.Object(config.DEV_GUILD))
    @app_commands.command(name="top", description="Returns the top GPQ scores of all-time (default 10 scores). Only includes each user's highest score.")
    async def top(self, ctx, n : Optional[int] = 10):
        try:
            if not await self.isInGpqChannel(ctx):
                return
            gpqSync = self.bot.get_cog("GPQ_Sync")
            if gpqSync is not None:
                scores = await gpqSync.getTopScores()
                emb, file = await self.buildTopEmbed(scores, gpqSync, numScores=n, title=f"Top {n} GPQ Scores (All-Time)")
                if file == None:
                    await ctx.response.send_message(embed=emb)
                else:
                    await ctx.response.send_message(file=file, embed=emb)
            else:
                await ctx.response.send_message("GPQ Sync not loaded, contact developer")
        except Exception as e:
            print(e)
            print(traceback.print_exc())


    @app_commands.guilds(discord.Object(config.GPQ_GUILD), discord.Object(config.DEV_GUILD))
    @app_commands.command(name="toptotal", description="Returns the top total GPQ scores of all-time (default 10 scores).")
    async def toptotal(self, ctx, n : Optional[int] = 10):
        try:
            if not await self.isInGpqChannel(ctx):
                return
            gpqSync = self.bot.get_cog("GPQ_Sync")
            if gpqSync is not None:
                scores = await gpqSync.getTopTotalScores()
                ##needs to be in the format [x, charid, x, score]
                scores = [(None, x[0], None, x[1]) for x in scores]
                emb, file = await self.buildTopEmbed(scores, gpqSync, title=f"Top {n} Dubsly Dollar Earners (All-Time)", numScores=n, week=True)
                if file == None:
                    await ctx.response.send_message(embed=emb)
                else:
                    await ctx.response.send_message(file=file, embed=emb)
            else:
                await ctx.response.send_message("GPQ Sync not loaded, contact developer")
        except Exception as e:
            print(e)
            print(traceback.print_exc())


    async def isInGpqChannel(self, interaction):
        if(not interaction.channel.id in config.GPQ_CHANNELS):
            await interaction.response.send_message("Command must be used in GPQ channel", ephemeral=True)
            return(False)
        return(True)


    async def buildScoreEmbed(self, ign, scores, ranking):
        emb = discord.Embed(title=ign, description="Bounce GPQ stats", color=discord.Colour.green())
        file = None

        ## Ranking Stuff
        if ranking != None:

            ##idx 0: serial, 1: image, 2: name, 3: exp, 4: gap, 5: jobdetail, 6: jobid, 7: level, 8: jobname, 9: rank, 10: charid 
            filePath = await self.saveCharImg(ranking[10], ranking[1])
            if filePath != None:
                file = discord.File(filePath, filename="{0}.png".format(ranking[10]))
                emb.set_thumbnail(url= "attachment://{0}.png".format(ranking[10]))

            emb.add_field(name="Class", value=ranking[8])
            emb.add_field(name="Level", value=ranking[7])

            gapEmoji = "🔻" if ranking[4] > 0 else "🔺 "if ranking[4] < 0 else "➖"
            emb.add_field(name="Reboot rank", value="{0} ({1}{2})".format(ranking[9], gapEmoji, abs(ranking[4])))

        ## Tops
        nonZeroScores = [s for s in scores if s[3] != 0]
        bestScore = max([s[3] for s in nonZeroScores])
        totalScore = sum([s[3] for s in nonZeroScores])
        averageScore = round(totalScore / len(nonZeroScores))

        emb.add_field(name="Average Score", value=f"{averageScore:,} points")
        emb.add_field(name="Best Score", value=f"{bestScore:,} points")
        emb.add_field(name="Total Dubsly Dollars", value=f"{totalScore:,} points")

        ## Recents
        recentScores = list(reversed(scores))[:5]
        emb.add_field(name="Recent Scores", value="```{0}```".format("\n".join(["{0}: {1:,}".format(s[2], s[3]) for s in recentScores])), inline=False)

        return(emb, file)


    async def buildTopEmbed(self, scores, gpqSync, title="Top 10 GPQ Scores (All-Time)", week=False, numScores = 10):
        emb = discord.Embed(title=title, color=discord.Colour.green())
        file = None

        scorers = [await gpqSync.getCharacterByCharId(s[1]) for s in scores[:min(numScores, 25)]]
        topScorer = await gpqSync.getRankingInfo(scorers[0][1])

        if topScorer != None:
            filePath = await self.saveCharImg(topScorer[10], topScorer[1])
            if filePath != None:
                file = discord.File(filePath, filename="{0}.png".format(topScorer[10]))
                emb.set_thumbnail(url= "attachment://{0}.png".format(topScorer[10]))
        
        for i, (scorer, score) in enumerate(zip(scorers, scores)):
            emb.add_field(name="{0}. {1}".format(i+1, scorer[1]), value=f"{score[3]:,}" + (" ({0})".format(score[2]) if not week else ""), inline = False if i == 0 else True)

        return(emb, file)


    async def buildGraph(self, scores, ign, scores2=[], ign2=None):
        ## Create score dictionaries and labels
        scores1Dict = {k : v for _, _, k, v in scores}
        scores2Dict = {k : v for _, _, k, v in scores2}
        xLabels = sorted(list(set([s[2] for s in scores]) | set([s[2] for s in scores2])))
        
        ## Prepare dict
        d = {"dates" : [], ign : []}
        columns = ["dates", ign]
        if scores2:
            d[ign2] = []
            columns.append(ign2)

        ## Fill dict
        for label in xLabels:
            d["dates"].append(label)
            d[ign].append(scores1Dict.get(label, 0))
            if scores2:
                d[ign2].append(scores2Dict.get(label, 0))
        
        ## Dict to dataframe
        ## Kinda pointless for now, might be helpful later
        df = pd.DataFrame(d, columns=columns)

        ## Set themes
        sns.set_theme()
        sns.set_palette("Set2", n_colors=2)
        sns.set_style("darkgrid")

        ## Generate and configure plot
        ax = sns.lineplot(data=df, dashes=False)
        ax.set_xticks(range(len(xLabels)))
        ax.set_xticklabels(xLabels, rotation=-45, ha='left')
        ax.set(xlabel="Week", ylabel="Score", title="GPQ Scores")
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.tight_layout()

        ## Save plot to buffer, close plot
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)

        return(buf)


    ## Discord cant embed directly from nexon API, have to save locally
    async def saveCharImg(self, charId, url):
        ## expected filepath
        filePath = "{0}/assets/{1}.png".format(os.getcwd(), charId)
        ## check if file exists
        if os.path.exists(filePath):
            st = os.stat(filePath)
            mtime = st.st_mtime
            dt = datetime.datetime.fromtimestamp(mtime)
            ## Check if file is <24 hours old, if it is reuse
            if datetime.datetime.now() - datetime.timedelta(hours=24) < dt:
                return(filePath)
        ## Here we either don't have an image, or its old, so get one
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                async with aiofiles.open(filePath, mode="wb") as f:
                    await f.write(await resp.read())
                    return(filePath)


    @gpq.autocomplete('ign')
    @graph.autocomplete('ign')
    @graph.autocomplete('ign2')
    async def scoreAutocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        gpqSync = self.bot.get_cog("GPQ_Sync")
        if gpqSync is not None:
            ignList, ignListLower = await gpqSync.getIgnLists()
            d = {k : v for k, v in zip(ignListLower, ignList)}
            cutoff = 0.0
            ## Get 5 closest entries
            closeLower = difflib.get_close_matches(current, ignListLower, n=5, cutoff=cutoff)
            print(closeLower)
            close = [d[x] for x in closeLower]
            print(close)
            if current == "":
                close = ignList[:5]      ## No input is just first 5
            return([app_commands.Choice(name=ign, value=ign) for ign in close])
        return([])

    
def isInt(i):
    try:
        i = i.replace(",", "")
        i = int(i)
        return(True)
    except:
        return(False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GPQ_Test(bot))
