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


    async def addOcrData(self, data, week = None):
        warnings = []
        errors = []
        added = 0
        dataAdded = []
        with self.dbConnect(auto=False) as conn:
            with conn.cursor() as cur:
                currentWeek = self.parseWeekInput(week)
                print(f"Current Week: {currentWeek}")
                for d in data:
                    try:
                        print("=====================================")
                        ign = d[0]
                        score = int(d[-2])
                        cur.execute("SELECT substring_similarity(%s, ign) as sim, id, ign FROM characters ORDER BY sim DESC", (ign, ))
                        sim, charId, ign2 = cur.fetchone()
                        print(sim, charId, ign2, d)
                        if ign2.lower() != ign.lower():
                            if sim < 0.1:
                                error = f"Couldn't find `{ign}` in database. Are they on the sheet?"
                                errors.append(error)
                                print(error)
                                continue
                            else:
                                warn = f"Using closest match `{ign2}` for `{ign}` ({round(sim, 2)})"
                                warnings.append(warn)
                                print(warn)
                        dataAdded.append([ign2, ign, sim, "{:,}".format(score)])
                        cur.execute("INSERT INTO scores (charid, week, score) VALUES (%s, %s, %s) ON CONFLICT (charid, week) DO UPDATE SET score = %s", (charId, currentWeek, score, score))
                        added += 1
                    except Exception as e:
                        print(f"Exception adding data: {e}")
                        print(traceback.print_exc())
                conn.commit()
        return(added, warnings, errors, dataAdded)

    
    def parseWeekInput(self, week):
        if week == None:
            return(self.getCurrentWeek())
        else:
            ## Turn date header into an object
            date = datetime.datetime.strptime(week, "%y%m%d").date()
            return(date)


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


    def updateCharacterTable2(self, users, archived = False):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                for user in users:
                    if len(user) > 0:
                        cur.execute("INSERT INTO characters (ign, archived) VALUES (%s, %s) ON CONFLICT (ign) DO UPDATE set archived = %s", (user[0], archived, archived))


    async def getUserScores(self, ign):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM characters ORDER BY substring_similarity(ign, %s) DESC LIMIT 1;", (ign,))
                charId = cur.fetchone()[0]
                
                cur.execute("SELECT * FROM SCORES WHERE charid = %s ORDER BY week ASC", (charId, ))
                scores = cur.fetchall()
                return(scores)


    async def getRankingInfo(self, ign):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM characters ORDER BY substring_similarity(ign, %s) DESC LIMIT 1", (ign,))
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


    async def getTopTotalScores(self):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT charid, sum(score) FROM scores GROUP BY charid ORDER BY sum(score) DESC")
                scores = cur.fetchall()
                return(scores)


    async def dropLatestWeek(self):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM scores WHERE week in (SELECT DISTINCT week FROM scores ORDER BY week DESC LIMIT 1)")
                return


    async def getLatestWeek(self):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT week FROM scores ORDER BY week DESC LIMIT 1")
                latest = cur.fetchone()
                return(latest)


    ## Needs optimization so it isn't inserting every score every single sync
    def updateTableFromSheet(self, data, archived = False):
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
                    if len(row) < 8:
                        continue
                    ## idx: 1-ign 2-avg 3-max 4-attended 5-missed 6-total 7+ scores
                    ign = row[1]
                    cur.execute("SELECT * FROM characters ORDER BY substring_similarity(ign, %s) DESC LIMIT 1;", (ign,))
                    charId, ign, klass, level, arch = cur.fetchone()
                    
                    firstScore = False

                    ## Start at 8 because that is where the scores start
                    for date, score in zip(dates[8:], row[8:]):
                        ## In case we have whitespace as a score
                        score = score.strip()
                        ## Skip leading empty fields, as those indicate the user was not in the guild at that time
                        if not firstScore and score.strip() == '':
                            continue
                        else:
                            ## Found a real score, set flag so we don't skip any more empty
                            firstScore = True
                            ## Turn date header into an object
                            date = datetime.datetime.strptime(date, config.STRPTIME_FMT).date()
                            scoreNum = 0
                            try:
                                if score.strip() == "":
                                    continue
                                ## Attempt to parse score here, if it can't be parsed there is bad data
                                scoreNum = int(score.replace(",", ""))
                            except Exception as e:
                                print(f"Unable to parse score '{score}' for {ign} on {date}")
                            ## Update that score
                            cur.execute("INSERT INTO scores (charid, week, score) VALUES (%s, %s, %s) ON CONFLICT (charid, week) DO UPDATE SET score = %s", (charId, date, scoreNum, scoreNum))
                    conn.commit()


    def updateSheetFromTable(self, data, archived = False, force = False):
        values = data["values"]
        dates = values[0]

        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                insertData = []

                ## Get all characters
                cur.execute("SELECT * FROM characters WHERE archived = %s", (archived, ))
                charRes = cur.fetchall()

                ## Iterate over each character
                for char in charRes:
                    charId, ign, klass, level, arch = char

                    ## Get all that characters scores
                    cur.execute("SELECT * FROM SCORES WHERE charid = %s ORDER BY week ASC", (charId, ))
                    scoresRes = cur.fetchall()
                    if(scoresRes == []):
                        #print(f"User {ign} has no scores recorded")
                        continue

                    ## Get the users first and last week of running
                    row = self.getUserRow(values, ign)
                    if(row == None):
                        ##TODO: add user to table? 
                        #print(f"User {ign} is not in table")
                        continue

                    needUpdate, merged = self.mergeScores(scoresRes, values[row][8:], dates[8:])

                    # This means we have new info in the DB, likely from OCR
                    if(needUpdate or force):
                        mergedTupleList = [(k, v) for k, v in merged.items()]
                        sortedMergedTupleList = sorted(mergedTupleList, key=lambda x : datetime.datetime.strptime(x[0], config.STRPTIME_FMT))
                        print(f"{ign} len {len(sortedMergedTupleList)}")
                        #print(sortedMergedTupleList)
                        for d, s in sortedMergedTupleList:
                            if d not in dates:
                                print("Date {0} not found in dates".format(d))
                        valList = [x[1] for x in sortedMergedTupleList]
                        insertData.append(
                            {
                                "range" : f"{'Culvert' if not archived else 'Archived Members'}!{self.getColFromDate(dates, sortedMergedTupleList[0][0])}{row + 1}:{self.getColFromDate(dates, sortedMergedTupleList[-1][0])}{row + 1}",
                                "values" : [valList]
                            }
                        )
                
                ## Check if we found any new data to insert
                if len(insertData) > 0:
                    #print(insertData)
                    body = {
                        'valueInputOption': "USER_ENTERED",
                        'data' : insertData
                    }
                    result = self.sheet.values().batchUpdate(spreadsheetId=config.GPQ_SHEET, body=body).execute()
                    print(f"Update sheet result: {result}")


    def mergeScores(self, dbScores, sheetScores, dates):
        f = "#" if os.name == "nt" else "-"
        dbScoresDict = {s[2].strftime(config.STRFTIME_FMT) : s[3] for s in dbScores}
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

    def __getWholeArchivedSheet(self):
        return(self.sheet.values().get(spreadsheetId=config.GPQ_SHEET, range="Archived Members", majorDimension="ROWS").execute())


    def getAllUsers2(self):
        resp = self.sheet.values().get(spreadsheetId=config.GPQ_SHEET, range="Culvert!{0}:{0}".format("B"), majorDimension="ROWS").execute()
        values = resp.get("values")[1:]
        return(values)

    
    def getArchivedUsers(self):
        resp = self.sheet.values().get(spreadsheetId=config.GPQ_SHEET, range="Archived Members!{0}:{0}".format("B"), majorDimension="ROWS").execute()
        values = resp.get("values")[1:]
        return(values)


    ## Since the sheet is gospel, we update first the DB based on sheet information
    ## Next, we update the sheet based on the table for **new** information the bot adds (OCR)
    ## This way, we can update the sheet to correct OCR errors the bot might encounter
    async def syncData(self, force = False):
        async with self.syncLock:
            print("Getting users")
            users = self.getAllUsers2()
            archivedUsers = self.getArchivedUsers()
            print("Updating characters")
            self.updateCharacterTable2(users)
            self.updateCharacterTable2(archivedUsers, archived=True)
            
            print("Getting data")
            data = self.__getWholeSheet()
            dataArch = self.__getWholeArchivedSheet()
            print("Updating Table from Sheet")
            self.updateTableFromSheet(data)
            self.updateTableFromSheet(dataArch, archived=True)
            print("Updating Sheet from Table")
            self.updateSheetFromTable(data, force = force)
            self.updateSheetFromTable(dataArch, archived=True, force = force)

            print("Updating IGN list")
            out = await self.getAllUsersGlobal()
            self.ignList = list(out.values())
            self.ignListLower = list([x.lower() for x in out.values()])


    ## Gets all users for autocomplete
    async def getAllUsersGlobal(self, archived = False):
        with self.dbConnect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, ign FROM characters WHERE archived = %s", (archived, ))
                resp = cur.fetchall()
                out = {id : ign for id, ign in resp}
                return(out)


    async def getIgnLists(self):
        return(self.ignList, self.ignListLower)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GPQ_Sync(bot))

## https://stackoverflow.com/questions/43156987/postgresql-trigrams-and-similarity 
"""
CREATE OR REPLACE FUNCTION substring_similarity(string_a TEXT, string_b TEXT) RETURNS FLOAT4 AS $$
DECLARE
  a_trigrams TEXT[];
  b_trigrams TEXT[];
  a_tri_len INTEGER;
  b_tri_len INTEGER;
  common_trigrams TEXT[];
  max_common INTEGER;
BEGIN
  a_trigrams = SHOW_TRGM(string_a);
  b_trigrams = SHOW_TRGM(string_b);
  a_tri_len = ARRAY_LENGTH(a_trigrams, 1);
  b_tri_len = ARRAY_LENGTH(b_trigrams, 1);
  IF (NOT (a_tri_len > 0) OR NOT (b_tri_len > 0)) THEN
    IF (string_a = string_b) THEN
      RETURN 1;
    ELSE
      RETURN 0;
    END IF;
  END IF;
  common_trigrams := ARRAY(SELECT UNNEST(a_trigrams) INTERSECT SELECT UNNEST(b_trigrams));
  max_common = LEAST(a_tri_len, b_tri_len);
  RETURN COALESCE(ARRAY_LENGTH(common_trigrams, 1), 0)::FLOAT4 / max_common::FLOAT4;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION corrected_similarity(string_a TEXT, string_b TEXT) 
RETURNS FLOAT4 AS $$
DECLARE
  base_score FLOAT4;
BEGIN
  base_score := substring_similarity(string_a, string_b);
  -- a good standard similarity score can raise the base_score
  RETURN base_score + ((1.0 - base_score) * SIMILARITY(string_a, string_b));
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION is_minimally_substring_similar(string_a TEXT, string_b TEXT) RETURNS BOOLEAN AS $$
BEGIN
  RETURN corrected_similarity(string_a, string_b) >= 0.5;
END;
$$ LANGUAGE plpgsql;

CREATE OPERATOR %%% (
  leftarg = TEXT,
  rightarg = TEXT,
  procedure = is_minimally_substring_similar,
  commutator = %%%
);
"""
