import discord
from discord.ext import commands, tasks

import asyncio
import aiohttp
import traceback
import concurrent
import time

class ServerChecker(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.servers = [["34.215.62.60", "8484"], ["35.167.153.201", "8484"], ["52.37.193.138", "8484"]]

        self.channels = []
        self.chIps = [  "35.155.204.207", "52.26.82.74", "34.217.205.66", "54.148.188.235", "54.218.157.183",
                        "54.68.160.34", "52.25.78.39", "52.33.249.126", "34.218.141.142", "54.148.170.23",
                        "54.191.142.56", "54.201.184.26", "52.13.185.207", "34.215.228.37", "54.187.177.143",
                        "54.203.83.148", "35.161.183.101", "52.43.83.76", "54.69.114.137", "54.148.137.49",
                        "54.212.109.33", "44.230.255.51", "100.20.116.83", "54.188.84.22", "34.215.170.50",
                        "54.184.162.28", "54.185.209.29", "52.12.53.225", "54.189.33.238", "54.188.84.238"  ]
        self.chPort = "8585"

        self.up = True
        self.downDuration = 0

        self.timeout = aiohttp.ClientTimeout(total=5)

        self.checker.start()

    async def checkServer(self, ip, port):
        start = 0
        end = 0
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
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

    async def checkPing(self, session, ip, port):
        end = 0
        start = time.time()
        try:
            async with session.get("http://{0}:{1}".format(ip, port)) as r:
                pass
        except asyncio.TimeoutError as e:
            return(False, 0)
        except aiohttp.ClientResponseError as e:
            pass
        end = time.time()
        return(True, round((end - start)* 1000))

    
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
        if(self.up):
            ##sleep for 1 minute (loop sleeps for 10, so sleep for 50 here)
            await asyncio.sleep(50)

            
    @checker.before_loop
    async def before_checker(self):
        print("Checker waiting for bot.")
        await self.bot.wait_until_ready()
        print("Checker ready")


    @commands.command()
    async def ch(self, ctx, channel : int):
        if(channel > 0 and channel <= 30):
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                ret, ping = await self.checkPing(session, self.chIps[channel - 1], self.chPort)
                if(ret):
                    status = ""
                    if(ping <= 60):
                        status = "Very Good"
                    elif(ping <= 90):
                        status = "Good"
                    elif(ping <= 120):
                        status = "Average"
                    elif(ping <= 180):
                        status = "Poor"
                    else:
                        status = "Probably on fire"
                    print(ping)
                    await ctx.reply("Channel {0} status: {1}".format(channel, status))
                else:
                    await ctx.reply("Channel {0} is offline.".format(channel))


    async def serverUpPing(self):
        ##put channel to ping here
        ch = await self.bot.fetch_channel(834175696627564567)
        await ch.send("{0}\nLogin servers are back online!".format(ch.guild.default_role))


def setup(bot):
    bot.add_cog(ServerChecker(bot))