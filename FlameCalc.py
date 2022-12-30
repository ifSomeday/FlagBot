from enum import Enum, auto
import math
import time
import itertools
import pickle
import os
import difflib

class FlameCalc():

    def __init__(self):
        ## Generate initial flame array
        self.loadGenDistribution()
        pass


    def loadGenDistribution(self):
        filePath = "{0}/assets/dist.pickle".format(os.getcwd())
        if os.path.exists(filePath):
            with open(filePath, "rb") as f:
                self.flameDist = pickle.load(f)
        else:
            self.flameDist = self.generateAllPossibleFlames(200, 0, 0)

            start = time.time()
            self.flameDist.sort(key=lambda t: t[0])
            end = time.time()
            print(f"Sorting dist took {round(end-start, 4)} seconds")

            with open(filePath, "wb") as f:
                pickle.dump(self.flameDist, f)

    
    def calcFlame(self, flames, baseStats, level):
        
        baseAtk = baseStats.get(Stats.ATTACK, 0)
        baseMatk = baseStats.get(Stats.MAGIC_ATTACK, 0)

        statsBoosted = flames.keys()

        possibleFlames = self.generatePossibleFlames(statsBoosted, level, baseAtk, baseMatk)

        combos1 = []
        ##Itertools
        totalCombos = 0
        start = time.time()
        validFlames = []
        for i in range(1, 5):
            for combo in itertools.combinations(possibleFlames, i):
                d = {}
                for flame in combo:
                    for stat in flame.stats:
                        d[stat] = d.get(stat, 0) + flame.value
                if(d == flames):
                    tmp = [tuple(x.stats) for x in combo]
                    if(len(tmp) == len(set(tmp))):
                        print(combo)
                        validFlames.append(combo)
        end = time.time()
        print("{0} Flames found in {1}s".format(len(validFlames), end - start))
        return(validFlames)


        """
        start = time.time()
        combos2 = self.search(possibleFlames, [], [], 0)
        possibleCombos2 = []
        for combo in combos2:
            d = {}
            for flame in combo:
                for stat in flame.stats:
                    d[stat] = d.get(stat, 0) + flame.value
            if(d == flames):
                print(combo)
                possibleCombos2.append(combo)
        end = time.time()
        print(end - start)
        print(len(combos2))
        """
        #print(possibleCombos1)
        #print(possibleCombos2)
        


        ##print(possibleFlames)

    
    ##Python tail recursion sucks
    ##TODO: change to iterative? >50% reduction in search space
    def search(self, possibleFlames, combos, currentFlames, currDepth, maxDepth = 4):
        if(currDepth > maxDepth):
            return(combos)
        if(not currentFlames == []):
            combos.append(currentFlames)
        for i in range(0, len(possibleFlames)):
            if any(possibleFlames[i] == x for x in currentFlames):
                continue
            else:
                combos = self.search(possibleFlames[i+1:], combos, [*currentFlames, possibleFlames[i]], currDepth + 1, maxDepth=maxDepth)
        return(combos)


    def gen(self, pool, allStatR = 10, secR = 1/15, atkR = 2.5):
        res = []
        for i, f1 in enumerate(pool):
            for j, f2 in enumerate(pool[i+1:]):
                for k, f3 in enumerate(pool[i + 2 + j:]):
                    for l, f4 in enumerate(pool[i + j + k + 3:]):
                        res += [self.score(flame, Stats.MAIN, Stats.SEC, Stats.ATTACK,secR=secR, allStatR=allStatR, atkR=atkR) for flame in itertools.product(f1, f2, f3, f4)]
                        #res += [itertools.product(f1, f2, f3, f4)]
        return(res)




    def generatePossibleFlames(self, stats, level, baseAtk, baseMatk):
        flames = []

        flatStats = [Stats.STR, Stats.DEX, Stats.INT, Stats.LUK]
        attacks = [Stats.ATTACK, Stats.MAGIC_ATTACK]
        
        ##Flat Stats
        for stat in flatStats:
            if stat in stats:
                flames += self.generateSingleStatFlames(stat, level)
        
        ##Combination stats
        for combination in itertools.combinations(flatStats, 2):
            if(all(x in stats for x in combination)):
                flames += self.generateDoubleStatFlames(combination, level)

        ##Attack
        if(Stats.ATTACK in stats):
            flames += self.generateAllAttacks(Stats.ATTACK, baseAtk, level)
        
        ##Magic Attack
        if(Stats.MAGIC_ATTACK in stats):
            flames += self.generateAllAttacks(Stats.MAGIC_ATTACK, baseMatk, level)

        ##Def
        if(Stats.DEF in stats):
            flames += self.generateSingleStatFlames(Stats.DEF, level)
        
        ##HP/MP
        for stat in [Stats.HP, Stats.MP]:
            if stat in stats:
                flames += self.generateHPMPFlame(stat, level)

        ##Speed/Jump/All Stat/Damage
        for stat in [Stats.SPEED, Stats.JUMP, Stats.ALL_STAT, Stats.DMG]:
            if stat in stats:
                flames += self.generateNonWeaponAttack(stat) ##lol
        
        ##Boss DMG
        if Stats.BOSS in stats:
            flames += [Flame(x.stats, 2*x.value, x.tier) for x in self.generateNonWeaponAttack(Stats.BOSS)] ##lol
        
        return flames

    def generateSingleStatFlames(self, stat, level):
        flames = []
        for tier in range(1, 8):
            flames.append(Flame([stat], ((level // 20) + 1) * tier, tier))
        return(flames)

    def generateDoubleStatFlames(self, stats, level):
        flames = []
        for tier in range(1, 8):
            flames.append(Flame(stats, ((level // 40) + 1) * tier, tier))
        return(flames)

    def generateNonWeaponAttack(self, stat):
        flames = []
        for tier in range(1, 8):
            flames.append(Flame([stat], tier, tier))
        return(flames)

    def generateWeaponAttack(self, stat, base, level, advantaged=True):
        flames = []
        minTier = 3 if advantaged else 1
        for tier in range(minTier, 8):
            a = math.ceil(base * ((((level // 40) + 1)) * (1.1 ** min(tier - (3 if advantaged else 1), 4)) * tier) / 100)
            flames.append(Flame([stat], a, tier))
        return(flames)

    def generateAllAttacks(self, stat, base, level):
        flames = []
        flames += self.generateNonWeaponAttack(stat)
        flames += self.generateWeaponAttack(stat, base, level, advantaged=False)
        flames += self.generateWeaponAttack(stat, base, level)
        return(flames)

    def generateHPMPFlame(self, stat, level):
        flames = []
        for tier in range(1, 8):
            flames.append(Flame([stat], max(((level // 10)) * 10, 1) * (tier * 3), tier))
        return(flames)

    def generateAllPossibleFlames(self, level, baseAtk, baseMatk, weapon=False, adv=True):
        
        flamePools = []
        for stat in [Stats.MAIN, Stats.SEC, Stats.NONE, Stats.NONE]:
            flamePools.append(self.generateSingleStatFlames(stat, level)[2:7])

        for c in itertools.combinations([Stats.MAIN, Stats.SEC, Stats.NONE, Stats.NONE], 2):
            flamePools.append(self.generateDoubleStatFlames(c, level)[2:7])
        
        flamePools.append(self.generateHPMPFlame(Stats.HP, level)[2:7])
        flamePools.append(self.generateHPMPFlame(Stats.MP, level)[2:7])

        flamePools.append(self.generateNonWeaponAttack(Stats.SPEED)[2:7])
        flamePools.append(self.generateNonWeaponAttack(Stats.JUMP)[2:7])

        flamePools.append(self.generateSingleStatFlames(Stats.DEF, level)[2:7])

        flamePools.append(self.generateNonWeaponAttack(Stats.LEVEL)[2:7]) ## Doesnt generate correct numbers, but we do not really care, just that there are 5 flames in the pool

        flamePools.append(self.generateNonWeaponAttack(Stats.ALL_STAT)[2:7])

        if(weapon):
            flamePools.append(self.generateNonWeaponAttack(Stats.DMG)[2:7])
            flamePools.append([Flame(x.stats, 2*x.value, x.tier) for x in self.generateNonWeaponAttack(Stats.BOSS)][2:7])

            flamePools.append(self.generateWeaponAttack(Stats.ATTACK, baseAtk, level, advantage=adv)[2:7])
            flamePools.append(self.generateWeaponAttack(Stats.MAGIC_ATTACK, baseMatk, level, advantage=adv)[2:7])
        else:
            flamePools.append(self.generateNonWeaponAttack(Stats.ATTACK)[2:7])
            flamePools.append(self.generateNonWeaponAttack(Stats.MAGIC_ATTACK)[2:7])

        #for pool in flamePools:
        #    print(pool)

        start = time.time()
        allFlames = self.gen(flamePools)
        end = time.time()
        print(f"Took {round(end - start, 4)} seconds to generate all flames")
        print(f"Generated {len(allFlames)} flames")

        return(allFlames)
        

    def score(self, flames, mainStat, secStat, atkStat, secR=1/15, allStatR=10, atkR=2.5):
        total = 0
        terms = []
        prob = 1/3876
        probs = [1, 1, 0.558, 0.325,0.065, 0.032, 0.02]
        for flame in flames:
            prob *= probs[flame.tier-1]
            if atkStat in flame.stats:
                total += (atkR * flame.value)
                terms.append(f"{flame.value}a")
                
            elif Stats.ALL_STAT in flame.stats:
                total += (allStatR * flame.value)
                terms.append(f"{flame.value}l")
            else:
                if secStat in flame.stats:
                    total += (secR * flame.value)
                    terms.append(f"({flame.value})s")
                if mainStat in flame.stats:
                    total += flame.value
                    terms.append(f"{flame.value}")
        return(total, " + ".join(terms), 0, prob)


    def getIdxTupleFast(self, i, v):
        idx = int(len(self.flameDist) / 2)
        segSize = int(len(self.flameDist) / 2)
        val = math.floor(self.flameDist[idx][i]) 
        while(val != v and segSize > 1):
            segSize = int(segSize/2)
            #print(segSize, val)
            if val < v:
                idx = min(idx + segSize, len(self.flameDist))
            else:
                idx = max(idx - segSize, 0)
            val = math.floor(self.flameDist[idx][i])
        while self.flameDist[idx][i] >= v and idx > 0:
            idx -= 1
        return(idx)

    def getIdxTuple(self, arr, i, v):
        for idx, t in enumerate(arr):
            if t[i] >= v:
                return(idx)

    def scoreOver(self, score):
        start = self.getIdxTuple(self.flameDist, 0, score)
        cum = sum([t[3] for t in self.flameDist[:start-1]])
        return(1 / (1 - cum))


    def scoreOverFast(self, score):
        start = self.getIdxTupleFast(0, score)
        cum = sum([t[3] for t in self.flameDist[:start]])
        return(1 / (1 - cum))


class Flame():

    def __init__(self, stats, value, tier):
        self.stats = list(stats)
        self.value = value
        self.tier = tier

    def __repr__(self):
        return("{0} T{2}: {1}".format(str([str(x) for x in self.stats]), self.value, self.tier))

    def __eq__(self, other):
        if isinstance(other, Flame):
            if other.stats == self.stats:
                return(True)
        return(False) 

class Stats(str, Enum):
    STR = "STR"
    DEX = "DEX"
    INT = "INT"
    LUK = "LUK"

    MAIN = "MAIN"
    NONE = "NONE"
    SEC = "SEC"

    ATTACK = "Attack Power"
    MAGIC_ATTACK = "Magic Attack"
    DEF = "Defense"
    HP = "Max HP"
    MP = "Max MP"
    SPEED = "Speed"
    JUMP = "Jump"

    ALL_STAT = "All Stats"
    BOSS = "Boss Damage"
    DMG = "Damage"
    LEVEL = "n/a"

    def __repr__(self):
        return self.name

    def __str__(self):
        return(self.value)



if __name__ == "__main__":
    calc = FlameCalc()
