from inspect import trace
import discord
from discord.ext import commands, tasks
from discord import app_commands

import datetime
import os
from contextlib import contextmanager
import traceback

from apiclient import discovery
from google.oauth2 import service_account
import psycopg2
import asyncio
import aiohttp

import config

class GPQ_Sync(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.sheet = self.loadSheets()
        self.getSheetIds()

        self.syncLock = asyncio.Lock()
        self.ignList = []

        self.reboot = 1 ##1 for reboot, 0 for reg

        self.syncLoop.start()
        self.firstLoop = True
        self.rankingLoop.start()


    @contextmanager
    def dbConnect(self, auto=True):
        conn = psycopg2.connect(dbname=config.GPQ_DB_NAME, user=config.DB_USER, password=config.DB_PASS, host=config.DB_ADDR)
        conn.set_session(autocommit=True)
        try:
            yield conn
        finally:
            conn.close()


    @tasks.loop(minutes=10)
    async def syncLoop(self):
        print("Starting automatic sync")
        try:
            await self.syncData()
            print("Automatic sync complete")
        except Exception as e:
            print(f"Exception syncing data: {e}")
            print(traceback.print_exc())


    @tasks.loop(hours=24)
    async def rankingLoop(self):
        if(self.firstLoop):
            self.firstLoop = False
            return
        try:
            users = await self.getAllUsersGlobal()
            with self.dbConnect() as conn:
                with conn.cursor() as cur:
                    for charId, ign in users.items():
                        print(f"inserting {ign}")
                        js = await self.getNexonRanking(ign)
                        if(js == []):
                            print(f"Unable to get user {ign}, response {js}")
                            continue
                        js = js[0]

                        keys = ["CharacterImgUrl", "CharacterName", "Exp", "Gap", "JobDetail", "JobID", "Level", "JobName", "Rank"]
                        insertDict = {k : js.get(k) for k in keys}
                        insertDict["charid"] = charId

                        fKeyString = ", ".join(f"{k}" for k in insertDict.keys())
                        fStrings = ", ".join("%s" for i in range(0, len(insertDict.keys())))
                        fStrings2 = ", ".join(["{0} = %s".format(k) for k in insertDict.keys()])
                        query = f"INSERT INTO nexon_rankings ({fKeyString}) VALUES ({fStrings}) ON CONFLICT (charid) DO UPDATE SET {fStrings2}"

                        cur.execute(query, (*insertDict.values(), *insertDict.values()))
                        
                        await asyncio.sleep(10)
                
        except Exception as e:
            print(e)
            print(traceback.print_exc())


    def loadSheets(self):
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credFile = os.path.join(os.getcwd(), config.CRED_FILE)
        creds = service_account.Credentials.from_service_account_file(credFile, scopes=scopes)
        service = discovery.build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()
        return(sheet)


    async def addOcrData(self, data):
        warnings = []
        errors = []
        added = 0
        with self.dbConnect(auto=False) as conn:
            with conn.cursor() as cur:
                currentWeek = self.getCurrentWeek()
                print(f"Current Week: {currentWeek}")
                for d in data:
                    try:
                        print("=====================================")
                        ign = d[0]
                        score = d[-3]
                        cur.execute("SELECT similarity(%s, ign) as sim, id, ign FROM characters ORDER BY sim DESC", (ign, ))
                        sim, charId, ign2 = cur.fetchone()
                        print(sim, charId, ign2)
                        if ign2.lower() != ign.lower():
                            print(d)
                            if sim < 0.1:
                                error = f"Couldn't find `{ign}` in database. Are they on the sheet?"
                                errors.append(error)
                                print(error)
                            else:
                                warn = f"Using closest match `{ign2}` for `{ign}` ({round(sim, 2)})"
                                warnings.append(warn)
                                print(warn)
                        cur.execute("INSERT INTO scores (charid, week, score) VALUES (%s, %s, %s) ON CONFLICT (charid, week) DO UPDATE SET score = %s", (charId, currentWeek, score, score))
                        added += 1
                    except Exception as e:
                        print(f"Exception adding data: {e}")
                        print(traceback.print_exc())
                conn.commit()
        return(added, warnings, errors)


    async def getNexonRanking(self, ign):
        rankingUrl = f"https://maplestory.nexon.net/api/ranking?id=overall&id2=legendary&rebootIndex={self.reboot}&character_name={ign}&page_index=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(rankingUrl) as response:
                js = await response.json()
                return(js)


    def getSheetIds(self):
        metadata = self.sheet.get(spreadsheetId=config.GPQ_SHEET).execute()
        sheets = metadata.get("sheets", "")
        
        for sheet in sheets:
            prop = sheet.get("properties", {})
            if(prop.get("title", "") == "Character Info"):
                self.charInfoId = prop.get("sheetId", -1)
            elif(prop.get("title", "") == "Culvert"):
                self.culvertId = prop.get("sheetId", -1)


    def updateCharacterTable2(self, users):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                for user in users:
                    cur.execute("INSERT INTO characters (ign) VALUES (%s) ON CONFLICT (ign) DO NOTHING", (user[0],))


    async def getUserScores(self, ign):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM characters ORDER BY SIMILARITY(ign, %s) DESC LIMIT 1;", (ign,))
                charId = cur.fetchone()[0]
                
                cur.execute("SELECT * FROM SCORES WHERE charid = %s ORDER BY week ASC", (charId, ))
                scores = cur.fetchall()
                return(scores)


    async def getRankingInfo(self, ign):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM characters ORDER BY SIMILARITY(ign, %s) DESC LIMIT 1", (ign,))
                charId = cur.fetchone()[0]

                cur.execute("SELECT * FROM nexon_rankings WHERE charid = %s", (charId, ))
                ranking = cur.fetchone()
                return(ranking)


    async def getWeekTopScores(self, week=None):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                if week == None:
                    cur.execute("SELECT week FROM SCORES ORDER BY week DESC LIMIT 1")
                    week = cur.fetchone()[0]
                cur.execute("SELECT * FROM SCORES WHERE week = %s ORDER BY score DESC LIMIT 20", (week, ))
                scores = cur.fetchall()
                return(scores)


    async def getTopScores(self):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM (SELECT DISTINCT ON (charid) * FROM scores ORDER BY charid, score DESC) t ORDER BY score DESC LIMIT 20")
                scores = cur.fetchall()
                return(scores)

    
    async def getCharacterByCharId(self, charId):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM characters WHERE id = %s", (charId, ))
                character = cur.fetchone()
                return(character)


    ## Needs optimization so it isn't inserting every score every single sync
    def updateTableFromSheet(self, data):
        values = data["values"]
        dates = values[0]
        with self.dbConnect(auto=False) as conn:
            with conn.cursor() as cur:
                ## values[0] is headers, so skip
                for row in values[1:]:
                    try:
                        int(row[0]) ## if it isn't a number, it isn't a data row
                    except:
                        continue
                    ## User has no scores
                    if len(row) < 7:
                        continue
                    ## idx: 1-ign 2-avg 3-max 4-attended 5-missed 6-total 7+ scores
                    ign = row[1]
                    cur.execute("SELECT * FROM characters ORDER BY SIMILARITY(ign, %s) DESC LIMIT 1;", (ign,))
                    charId, ign, klass, level = cur.fetchone()
                    
                    firstScore = False

                    ## Start at 7 because that is where the scores start
                    for date, score in zip(dates[7:], row[7:]):
                        ## In case we have whitespace as a score
                        score = score.strip()
                        ## Skip leading empty fields, as those indicate the user was not in the guild at that time
                        if not firstScore and score.strip() == '':
                            continue
                        else:
                            ## Found a real score, set flag so we don't skip any more empty
                            firstScore = True
                            ## Turn date header into an object
                            date = datetime.datetime.strptime(date, "%d/%m/%y").date()
                            scoreNum = 0
                            try:
                                ## Attempt to parse score here, if it can't be parsed there is bad data
                                scoreNum = 0 if score == '' else int(score.replace(",", ""))
                            except Exception as e:
                                print(f"Unable to parse score '{score}' for {ign} on {date}")
                            ## Update that score
                            cur.execute("INSERT INTO scores (charid, week, score) VALUES (%s, %s, %s) ON CONFLICT (charid, week) DO UPDATE SET score = %s", (charId, date, scoreNum, scoreNum))
                    conn.commit()


    def updateSheetFromTable(self, data):
        values = data["values"]
        dates = values[0]

        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                insertData = []

                ## Get all characters
                cur.execute("SELECT * FROM characters")
                charRes = cur.fetchall()

                ## Iterate over each character
                for char in charRes:
                    charId, ign, klass, level = char

                    ## Get all that characters scores
                    cur.execute("SELECT * FROM SCORES WHERE charid = %s ORDER BY week ASC", (charId, ))
                    scoresRes = cur.fetchall()
                    if(scoresRes == []):
                        print(f"User {ign} has no scores recorded")
                        continue

                    ## Get the users first and last week of running
                    row = self.getUserRow(values, ign)
                    if(row == None):
                        ##TODO: add user to table? 
                        print(f"User {ign} is not in table")
                        continue

                    needUpdate, merged = self.mergeScores(scoresRes, values[row][7:], dates[7:])

                    # This means we have new info in the DB, likely from OCR
                    if(needUpdate):
                        mergedTupleList = [(k, v) for k, v in merged.items()]
                        sortedMergedTupleList = sorted(mergedTupleList, key=lambda x : datetime.datetime.strptime(x[0], "%d/%m/%y"))
                        valList = [x[1] for x in sortedMergedTupleList]
                        insertData.append(
                            {
                                "range" : f"Culvert!{self.getColFromDate(dates, sortedMergedTupleList[0][0])}{row + 1}:{self.getColFromDate(dates, sortedMergedTupleList[-1][0])}{row + 1}",
                                "values" : [valList]
                            }
                        )
                
                ## Check if we found any new data to insert
                if len(insertData) > 0:
                    print(insertData)
                    body = {
                        'valueInputOption': "USER_ENTERED",
                        'data' : insertData
                    }
                    result = self.sheet.values().batchUpdate(spreadsheetId=config.GPQ_SHEET, body=body).execute()
                    print(f"Update sheet result: {result}")


    def mergeScores(self, dbScores, sheetScores, dates):
        f = "#" if os.name == "nt" else "-"
        dbScoresDict = {s[2].strftime(f"%{f}d/%{f}m/%y") : s[3] for s in dbScores}
        sheetScoresDict = {k : v for k, v in zip(dates, sheetScores)}
        merged = sheetScoresDict.copy()
        for k, v in dbScoresDict.items():
            merged[k] = v
        if(len(sheetScoresDict) != len(merged)):
            for date in dates:
                merged.setdefault(date, '')
        return(len(sheetScoresDict) != len(merged), merged)


    def getColFromDate(self, dates, week):
        dateStr = week
        idx = dates.index(dateStr)
        col = self.cs(idx)
        return(col)


    def getUserRow(self, values, ign):
        for i, row in enumerate(values):
            if(len(row) > 1):
                if row[1].lower().strip() == ign.lower().strip():
                    return(i)


    def removeLeadingElements(self, arr, e=''):
        out = []
        start = False
        for a in arr:
            if not start and a == e:
                continue
            start = True
            out.append(a)
        return(out)


    def getCurrentWeek(self):
        today = datetime.date.today()
        weekday = today.weekday()
        monday = today - datetime.timedelta(days=weekday)
        return(monday)


    ## converts a number to the column string
    def cs(self, n):
        n += 1
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return(s)


    def __getWholeSheet(self):
        return(self.sheet.values().get(spreadsheetId=config.GPQ_SHEET, range="Culvert", majorDimension="ROWS").execute())


    def getAllUsers2(self):
        resp = self.sheet.values().get(spreadsheetId=config.GPQ_SHEET, range="Culvert!{0}:{0}".format("B"), majorDimension="ROWS").execute()
        values = resp.get("values")[1:]
        return(values)


    ## Since the sheet is gospel, we update first the DB based on sheet information
    ## Next, we update the sheet based on the table for **new** information the bot adds (OCR)
    ## This way, we can update the sheet to correct OCR errors the bot might encounter
    async def syncData(self):
        async with self.syncLock:
            print("Getting users")
            users = self.getAllUsers2()
            print("Updating characters")
            self.updateCharacterTable2(users)
            
            print("Getting data")
            data = self.__getWholeSheet()
            print("Updating Table from Sheet")
            self.updateTableFromSheet(data)
            print("Updating Sheet from Table")
            self.updateSheetFromTable(data)

            print("Updating IGN list")
            out = await self.getAllUsersGlobal()
            self.ignList = list(out.values())


    ## Gets all users for autocomplete
    async def getAllUsersGlobal(self):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, ign FROM characters")
                resp = cur.fetchall()
                out = {id : ign for id, ign in resp}
                return(out)


    async def getIgnList(self):
        return(self.ignList)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GPQ_Sync(bot))