import discord
from discord.ext import commands
import psycopg2

import config
import datetime as dt

class DB(commands.Cog):



    def __init__(self, bot):
        self.bot = bot


    def dbConnect(self):
        conn = psycopg2.connect(dbname=config.DB_NAME, user=config.DB_USER, password=config.DB_PASS, host=config.DB_ADDR)
        conn.set_session(autocommit=True)
        return(conn)

    
    async def addWorldRank(self, ranks, insertIdx):
        conn = self.dbConnect()
        with conn.cursor() as cur:
            for rank in ranks:
                r, g, p = rank
                r = int(r)
                p = int(p.replace(",", "")) 
                #print("inserting {0}".format(str(rank)))
                cur.execute("SELECT * FROM worldrankings WHERE guild=%s AND race=%s AND date=%s;", (g, insertIdx, dt.date.today()))
                res = cur.fetchone()
                print(res)
                if(res == None):
                    cur.execute("INSERT INTO worldrankings (guild, points, rank, race) VALUES (%s, %s, %s, %s);", (g, p, r, insertIdx))
                else:
                    cur.execute("UPDATE worldrankings SET points=%s, rank=%s WHERE id=%s;", (p, r, res[0]))
        conn.close()

    async def getWeeklyWorldRanks(self):
        conn = self.dbConnect()
        today = dt.date.today()
        monday = today + dt.timedelta(days=-today.weekday())
        res = []
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM worldrankings WHERE date >= %s", (monday, ))
            res = cur.fetchall()
        conn.close()
        return(res)


    async def getLatestWorldRanks(self):
        conn = self.dbConnect()
        today = dt.date.today()
        monday = today + dt.timedelta(days=-today.weekday())
        res = []
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM (SELECT DISTINCT ON (guild) * FROM worldrankings WHERE date >= %s and race=(SELECT MAX (race) FROM worldrankings WHERE date=%s) ORDER BY guild, race DESC) t ORDER BY points DESC", (monday, today,))
            res = cur.fetchall()
        conn.close()
        return(res)
    
    async def deleteLastRace(self):
        conn = self.dbConnect()
        today = dt.date.today()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM worldrankings WHERE race=(SELECT MAX (race) FROM worldrankings WHERE date=%s)", (today, ))
        conn.close()
    

    async def getLatestDifferential(self):
        latest = await self.getLatestWorldRanks()
        guilds = tuple(entry[2] for entry in latest)
        print(latest)
        race = latest[0][5]

        conn = self.dbConnect()
        today = dt.date.today()
        monday = today + dt.timedelta(days=-today.weekday())
        past = {}
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM (SELECT DISTINCT ON (guild) * FROM worldrankings WHERE date >= %s AND race < %s AND guild IN %s ORDER BY guild, race DESC) t ORDER BY points DESC", (monday, race, guilds,))
            past = {x[2] : x for x in cur.fetchall()}
            print(past)
        ret = []
        for entry in latest:
            name = entry[2]
            if name in past:
                ##guildname, points, ptdiff, rank, rankdiff
                ret.append([entry[2], entry[3], entry[3] - past[name][3], entry[4], entry[4] - past[name][4]])
            else:
                ret.append([entry[2], entry[3], None, entry[4], None])
        conn.close()
        return(ret)

def setup(bot):
    bot.add_cog(DB(bot))
