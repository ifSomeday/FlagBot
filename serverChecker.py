import discord
from discord.ext import commands, tasks

from bs4 import BeautifulSoup

import asyncio
import aiohttp
import traceback
import concurrent
import time
import os
import pickle

class ServerChecker(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.servers = [["34.215.62.60", "8484"], ["35.167.153.201", "8484"], ["52.37.193.138", "8484"]]
        self.news = "https://maplestory.nexon.net/news/update#news-filter"

        self.lastLink = None

        self.channels = []

        self.up = True
        self.downDuration = 0
        self.checker.start()
        self.patchNotes.start()

    async def checkServer(self, ip, port):
        timeout = aiohttp.ClientTimeout(total=5)
        start = 0
        end = 0
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                start = time.time()
                async with session.get("http://{0}:{1}".format(ip, port)) as response:
                    
                    end = time.time()
                    pass
            except concurrent.futures.TimeoutError as e:
                ## Server is down
                return(False)
            except aiohttp.ClientConnectionError as e:
                ## Server is up
                end = time.time()
                pass
            except Exception as e:
                ## ????
                end = time.time()
                pass
        ##print("Response is {0}".format(end-start))
        return(True)
    
    @tasks.loop(seconds=10.0)
    async def checker(self):
        ##TODO: put this in a pool and execute all checks at once
        ##      use .gather()
        ##      For now, our down check should be a multiple of 3, since the check is per server, not per iteration
        for i, server in enumerate(self.servers):
            status = await self.checkServer(*server)
            if(not status):
                self.downDuration = min(self.downDuration+1, 36)
            if(not self.up == status):
                if(status):
                    print("up!")
                    ##36 is 10 loops of checks, 5 seconds apart, for a downtime of 60s
                    if(self.downDuration >= 36):
                        await self.serverUpPing()
                    self.downDuration = 0
                else:
                    print("down!")
                    pass
                self.up = status
            if(not self.downDuration in [0, 36]):
                print("Server failed check #{0}".format(self.downDuration))

            
    @tasks.loop(seconds=15.0)
    async def patchNotes(self, ctx=None):
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
             async with session.get(self.news) as response:
                text = await response.text()
                soup = BeautifulSoup(text)

                featuredNews = soup.find_all("div", {"class" : "component component-featured-news"})[0]

                newsList = featuredNews.find("ul").find_all("li")
                latestNews = newsList[0]

                newsLink = latestNews.find("a")["href"]

                if(self.lastLink == None):
                    self.lastLink = newsLink
                    return

                ## Verify its an update
                latestNewsType = latestNews.find("div", {"class" : "label"}).getText().strip()
                if(not latestNewsType == "FEATURED UPDATE"):
                    return

                ## Verify its not a preview
                latestNewsHeader = latestNews.find("h3").find("a").getText()
                if("preview" in latestNewsHeader.lower()):
                    print("would skip")
                    return

                if(not self.lastLink == newsLink):
                    self.lastLink = newsLink
                    if(ctx == None):
                        ch = await self.bot.fetch_channel(641483284244725776)
                        everyone = ch.guild.default_role
                        await ch.send("PATCH NOTES OUT {1}\n{0}".format("https://maplestory.nexon.net{0}".format(newsLink), everyone))
                    else:
                        await ctx.reply("PATCH NOTES OUT\n{0}".format("https://maplestory.nexon.net{0}".format(newsLink)))
                    


    @checker.before_loop
    async def before_checker(self):
        print("Checker waiting for bot.")
        await self.bot.wait_until_ready()
        print("Checker ready")


    @patchNotes.before_loop
    async def before_patchNotes(self):
        print("patchNotes waiting for bot.")
        await self.bot.wait_until_ready()
        print("patchNotes ready")

    async def serverUpPing(self):
        for chId in [794756750472773632]:
            ch = await self.bot.fetch_channel(chId)##834175696627564567)
            role = ch.guild.get_role(911085497210798100)
            await ch.send("{0}\nLogin servers are back online!".format(role.mention))
        ##Drowsy
        ch = await self.bot.fetch_channel(682405078451355681)
        role = ch.guild.get_role(986797775134031872)
        await ch.send("{0}\nLogin servers are back online!".format(role.mention))

    @commands.command()
    @commands.is_owner()
    async def news(self, ctx):
        await self.patchNotes(ctx=ctx)

    @commands.command()
    @commands.is_owner()
    async def roleTest(self, ctx):
        ch = await self.bot.fetch_channel(682405078451355681)
        await ctx.send(str(ch))
        role = ch.guild.roles
        print("\n".join(["{0} - {1}".format(x.name, x.id) for x in role]))


def setup(bot):
    bot.add_cog(ServerChecker(bot))
