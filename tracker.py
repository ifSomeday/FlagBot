import discord
from discord.ext import commands, tasks
from contextlib import contextmanager

import aioschedule as schedule
import aiohttp
import asyncio

import requests
import os
import psycopg2
from psycopg2.extras import Json
import json
import time
import config
from datetime import datetime

jobIds = {
    "Warrior" : 1,
    "Magician" : 2,
    "Bowman" : 3,
    "Thief"	: 4,
    "Pirate" : 5,
    "Noblesse" : 10,
    "Dawn Warrior" : 11,
    "Blaze Wizard" : 12,
    "Wind Archer" : 13,
    "Night Walker" : 14,
    "Thunder Breaker" : 15,
    "Legend" : 20,
    "Aran" : 21,
    "Evan" : 22,
    "Mercedes" : 23,
    "Phantom" : 24,
    "Citizen" : 30,
    "Demon Slayer" : 31,
    "Battle Mage" : 32,
    "Wild Hunter" : 33,
    "Mechanic" : 35,
    "Demon Avenger" : 209,
    "Jett" : 201,
    "Mihile" : 202,
    "Luminous" : 203,
    "Kaiser" :204,
    "Angelic Buster" : 205,
    "Hayato" : 206,
    "Kanna" : 207,
    "Xenon" : 208,
    "Zero" : 210,
    "Beast Tamer" : 211,
    "Shade" : 212,
    "Kinesis" : 214,
    "Blaster" : 215,
    "Cadena" : 216,
    "Illium" : 217,
    "Ark" : 218,
    "Pathfinder" : 219,
    "Ho Young" : 220,
    "Adele"	: 221,
    "Kain" : 222
}

## Tracks top N players of each class to see if any change names
## Does this by collecting the top 2N players every day, then
## searching for the previous days top N in that list
## If any are not found, it then finds the first new player in todays list
## And assumes that is the new ign
class Tracker(commands.Cog):

    def __init__(self, bot, n, ids):
        self.bot = bot

        self.url = "https://maplestory.nexon.net/api/ranking?id=job&id2={0}&rebootIndex={1}&page_index={2}"
        self.reboot = 1 ##1 for reboot, 0 for reg
        self.n = n

        self.trackedClasses = ["Kanna"]

        self.ids = ids

        self.createSchedule()
        self.scheduler.start()


    @tasks.loop(seconds=1)
    async def scheduler(self):
        await schedule.run_pending()

    @scheduler.before_loop
    async def beforeScheduler(self):
        print("tracker scheduler waiting...")
        await self.bot.wait_until_ready()
        print("tracker schedler started")

    @commands.command()
    @commands.is_owner()
    async def update(self, ctx):
        print("doing update")
        new = await self.getAllRankings()
        print("getting old")
        old = self.getEntries(numEntries=1)[0][1]
        print("adding entry")
        self.addEntry(new)
        
        print("tracking classes")
        for cl in self.ids.keys():
            print(cl)
            if(cl in new.keys() and cl in old.keys()):
                print("checking diff {0}".format(cl))
                n = new[cl]
                o = old[cl]

                ch = self.bot.get_channel(641483284244725776)
                await self.compareAndSend(ch, n, o)

    
    async def doUpdate(self):
        print("doing update")
        new = await self.getAllRankings()
        print("getting old")
        old = self.getEntries(numEntries=1)[0][1]
        print("adding entry")
        self.addEntry(new)
        
        print("tracking classes")
        for cl in self.ids.keys():
            print(cl)
            if(cl in new.keys() and cl in old.keys()):
                print("checking diff {0}".format(cl))
                n = new[cl]
                o = old[cl]

                ch = self.bot.get_channel(641483284244725776)
                await self.compareAndSend(ch, n, o)

    @commands.command()
    async def checkAll(self, ctx):
        for cl in self.ids.keys():
            print(cl)
            new, old = self.getEntries(numEntries=2)
            new = new[1]
            old = old[1]
            if(cl in new.keys() and cl in old.keys()):
                print("checking diff {0}".format(cl))
                n = new[cl]
                o = old[cl]

                ch = self.bot.get_channel(641483284244725776)
                await self.compareAndSend(ch, n, o)
                
    @commands.command()
    @commands.is_owner()
    async def checkClass(self, ctx, cl):
        if(cl in self.ids.keys()):
            new = await self.getRanking(self.ids[cl])
            old = self.getEntries(numEntries=1)[0][1][cl]

            await self.compareAndSend(ctx, new, old)
        else:
            ctx.reply("Invalid class `{0}`".format(cl))

    
    @commands.command()
    @commands.is_owner()
    async def lastUpdate(self, ctx):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute(("SELECT timestamp FROM cheaters ORDER BY timestamp DESC"))
                res = cur.fetchone()[0]
                await ctx.reply("Last update was `{0}`".format(res.strftime("%H:%M:%S %m-%d-%Y")))


    async def compareAndSend(self, ctx, new, old):
        z = self.compare(new, old)
        #print("{0} changes found".format(len(z)))
        for curr, prev in z:
            rankDiff = abs(curr["Rank"] - prev["Rank"])
            expDiff = curr["Exp"] - prev["Exp"]
            changePercent = round(expDiff/prev["Exp"], 2)
            r = "Name Change Detected!\n\tCurr: {0} - Rank {1}\n\tPrev: {2} - Rank {3}\n\tRank Differential: {4}\n\tExp Differential: {5:,} ({6}%)".format(curr["CharacterName"], curr["Rank"], prev["CharacterName"], prev["Rank"], rankDiff, expDiff, changePercent)
            await ctx.send(r)

    @contextmanager
    def dbConnect(self):
        conn = psycopg2.connect(dbname=config.DB_NAME, user=config.DB_USER, password=config.DB_PASS, host=config.DB_ADDR)
        conn.set_session(autocommit=True)
        try:
            yield conn
        finally:
            conn.close()

    #gets the lastest rankings for all classes:
    async def getAllRankings(self):
        start = time.time()
        print("Start get all")
        d = {}
        for name in self.ids.keys():
            print("Getting {0}".format(name))
            d[name] = await self.getRanking(self.ids[name])
            await asyncio.sleep(60)
        end = time.time()
        print("End get all ({0} s)".format(end - start))
        return(d)

    #gets the latest rankings for class cl
    async def getRanking(self, cl):
        data = []
        async with aiohttp.ClientSession() as session:
            for i in range(1, 2 * self.n + 1, 5):
                retries = 0
                while retries < 10:
                    async with session.get(self.url.format(cl, self.reboot, i)) as response:
                        if(response.status == 200):
                            data += await response.json()
                            await asyncio.sleep(1)
                            break
                        else:
                            print("Get failed ({0}, {1}, {2}), status {3}, retrying in 10...".format(cl, self.reboot, i, response.status))
                            print(await response.text())
                            await asyncio.sleep(10)
                            retries += 1
        return(data)

    def createSchedule(self):

        #dst = dst = time.localtime().tm_isdst

        schedule.every().day.at("{0}:00".format(6)).do(self.doUpdate)
        schedule.every().day.at("{0}:00".format(18)).do(self.doUpdate)

    #Get n entries from database
    #n=0 gets all
    def getEntries(self, numEntries=2):
        res = []
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                if(numEntries == 0):
                    cur.execute("SELECT * FROM cheaters ORDER BY timestamp DESC")
                else:
                    cur.execute("SELECT * FROM cheaters ORDER BY timestamp DESC LIMIT %s", (numEntries, ))
                res = cur.fetchall()
        return(res)

    ## Add new entry
    def addEntry(self, data):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO cheaters (json) VALUES (%s)", (Json(data), ))

    #compare two character lists, and find discrepancies 
    def compare(self, new, old):
        #new[8]["CharacterName"] = "test"
        newChars = [x for x in new[:self.n] if all(x["CharacterName"] != y["CharacterName"] for y in old)]
        oldChars = [x for x in old if all(x["CharacterName"] != y["CharacterName"] for y in new)]
        #print([x["CharacterName"] for x in newChars])
        #print([x["CharacterName"] for x in oldChars])
        return(zip(newChars, oldChars))

def setup(bot):
    bot.add_cog(Tracker(bot, 50, jobIds))
