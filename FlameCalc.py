from enum import Enum, auto
import math
import time
import itertools
import difflib

class FlameCalc():

    def __init__(self):
        pass

    
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