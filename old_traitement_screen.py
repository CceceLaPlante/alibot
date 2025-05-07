import cv2 
import numpy as np
import matplotlib.pyplot as plt
import os
import jellyfish
from screen.autocrop_sift import autocrop
import easyocr 
from scipy.cluster.vq import kmeans, vq
import urllib3

import discord


reader = easyocr.Reader(['fr'], gpu=False)
from id_card import VOCABULARY
DEBUG  = False

def isnumber (word) :
    return word.replace('.','',1).replace(",",'',1).replace("-",'',1).replace(":",'',1).isdigit()

def isvalidname(word) : 
    return word != " " and word != "" and not(word[0].isdigit()) and (not "%" in word)

class EndScreen : 

    def __init__ (self) : 
        self.img = None
        self.raw_result = None
        self.winners = []
        self.losers = []
        self.alliance = None
        self.prism = None 
        self.perco = None
        self.time = -1 
        self.wewon = None

    def concat (self, other) : 
        if set(self.winners) & set(other.winners) and self.time == other.time : 
            self.winners = list(set(self.winners) | set(other.winners))
            self.losers = list(set(self.losers) | set(other.losers))
        else : 
            raise ValueError("Cannot concatenate two different results")
            

    def parse (self, processed_text,positions,KNOWN_NAMES) : 
        names = []
        name_positions = []

        noname = []
        noname_positions = []

        for idx, word in enumerate(processed_text) : 
            if word not in VOCABULARY and not isnumber(word) and isvalidname(word): 
                names.append(word)
                name_positions.append(positions[idx])

            else :
                noname.append(word)
                noname_positions.append(positions[idx])
                
        if len(names) == 0 :
            raise ValueError("No names found")
        
        allYs = [pos[0][1] for pos in name_positions]
        allXs = [pos[0][0] for pos in name_positions]

        print("---------------")
        print("names : ", names)
        print("positions : ", name_positions)
        print("---------------")

        meanposrobust = 0
        nb_known = 0
        for idx, name in enumerate(names) :
            if name in KNOWN_NAMES : 
                meanposrobust += allXs[idx]
                nb_known += 1

        if nb_known > 0 :
            meanposrobust /= nb_known
            print("MEAN POS ROBUST : ", meanposrobust)
        else :
            raise ValueError("No known names found")
        
        good_names = []
        good_positions = []
        good_y = []

        for idx, name in enumerate(names) :
            if np.abs(allXs[idx] - meanposrobust) < 50 : 
                good_names.append(name)
                good_positions.append(name_positions[idx])
                good_y.append(float(allYs[idx]))

        frontiere = -1 

        print("-"*20)
        print("good names : ",good_names)   
        print("-"*20)

        # kmeans with 2 clusters to separate winners and losers
        if not "perdants" in processed_text : 
            means = kmeans(good_y,2)[0]
            means = np.sort(means)

            for idx, names in enumerate(good_names) : 
                if np.abs(good_y[idx] - means[0]) > np.abs(good_y[idx] - means[1]) : 
                    self.losers.append(names)
                else :
                    self.winners.append(names)
        else : 
            print("perdants trouvé !!!!")
            frontiere = noname_positions[noname.index("perdants")][0][1]
            for idx, name in enumerate(good_names): 
                if good_y[idx] > frontiere : 
                    self.losers.append(name)
                else :
                    self.winners.append(name)

        if len(set(list(self.winners)) & set(KNOWN_NAMES)) > 0 : 
            self.wewon = True
        else :
            self.wewon = False

        if 'prisme' in processed_text : 
            self.prism = True
        else :
            self.prism = False
            self.perco = True


        for idx, word in enumerate(noname) : 
            if word == 'statistiques' : 
                if isnumber(noname[idx+1]) : 
                    self.time = float(noname[idx+1].replace(',','.').replace("-",'.',1).replace(":",'.',1))
        

    def __str__ (self) : 
        to_print = ""  
        if self.wewon : 
            to_print += "**On a gagné ! Bravo**\n"
        else :
            to_print += "**On a perdu ... tanpis**\n"

        to_print += "\n"
        to_print += "## Gagnants : \n"
        for name in self.winners :
            to_print += f"**{name}**\n"
        to_print += "\n"
        to_print += "## Perdants : \n"
        for name in self.losers :
            to_print += f"**{name}**\n" 
        to_print += "\n"
        if self.prism : 
            to_print += "c'était contre un prisme !\n"
        else :
            to_print += "c'était contre un percepteur !\n"
        to_print += "\n"
        to_print += "le combat a duré pendant : `"+str(self.time)+" minutes`\n"
        to_print += "\n"

        return to_print

    def save(self, IDs,timestamp) : 
        for ids in IDs : 
            if ids.name in self.winners : 
                if self.prism : 
                    ids.prisme_fight_win += 1
                    ids.prisme_fight_total += 1
                    ids.prisme_won_unpaid += 1

                else :
                    ids.perco_fight_win += 1
                    ids.perco_fight_total += 1
                    ids.perco_won_unpaid += 1

                ids.time.append(timestamp)
                ids.haschanged = True

            elif ids.name in self.losers :
                if self.prism : 
                    ids.prisme_fight_loose += 1
                    ids.prisme_fight_total += 1
                    ids.prisme_loose_unpaid += 1

                else :
                    ids.perco_fight_loose += 1
                    ids.perco_fight_total += 1
                    ids.perco_loose_unpaid += 1

                ids.time.append(timestamp)
                ids.haschanged = True

    def to_embed(self, timestamp_str=None) -> discord.Embed:
        """Creates a Discord Embed representation of the screen result."""

        # Determine color based on win/loss
        embed_color = discord.Color.green() if self.wewon else discord.Color.red()
        result_emoji = "✅" if self.wewon else "❌"
        result_text = "Victoire !" if self.wewon else "Défaite..."

        # Determine target type
        target_emoji = "💎" if self.prism else "💰"
        target_text = "Prisme" if self.prism else "Percepteur"

        # Create the embed instance
        embed = discord.Embed(
            title=f"{result_emoji} Résultat du Combat ({target_text})",
            description=f"**{result_text}** contre un {target_text.lower()}.\nDurée: `{self.time} minutes`",
            color=embed_color
        )

        # Add Winners Field
        winner_list = "\n".join(f"👤 {name}" for name in self.winners) if self.winners else "*(Aucun)*"
        embed.add_field(name="🏆 Gagnants", value=winner_list, inline=True)

        # Add Losers Field
        loser_list = "\n".join(f"👤 {name}" for name in self.losers) if self.losers else "*(Aucun)*"
        embed.add_field(name="💀 Perdants", value=loser_list, inline=True)

        # Add a footer with timestamp if provided
        if timestamp_str:
            embed.set_footer(text=f"Message reçu à: {timestamp_str}")
        # You could also add a thumbnail or image if desired
        # embed.set_thumbnail(url="URL_TO_WIN_ICON" if self.wewon else "URL_TO_LOSS_ICON")

        return embed

    def hash (self) : 
        return str(self.winners)+str(self.losers)+str(self.prism)+str(self.perco)+str(self.time)+str(self.wewon)


def distance(text1, text2) : 
    return jellyfish.levenshtein_distance(text1, text2)

def preprocess (word) : 
    no_accent = {"é":"e", "è":"e", "ê":"e", "à":"a", "â":"a", "î":"i", "ï":"i", "ô":"o", "ù":"u", "û":"u", "ç":"c"}
    word = word.lower()
    for key in no_accent.keys() :
        word = word.replace(key, no_accent[key])
    return word

def word_to_known(word,KNOWN_NAMES) : 
    word = preprocess(word)
    min_dist = float("inf")
    known = None
    if isnumber(word) : 
        return word, -1

    for w in VOCABULARY+KNOWN_NAMES : 
        dist = distance(word, preprocess(w))
        if dist < min_dist : 
            min_dist = dist
            known = w

    if min_dist < 3 : 
        return known, min_dist
    else: 
         return word, float("inf")

def from_link_to_result (url,KNOWN_NAMES,nocrop=False) : 
    http = urllib3.PoolManager()
    r = http.request('GET', url)
    
    arr = np.asarray(bytearray(r.data), dtype=np.uint8)
    img = cv2.imdecode(arr, -1)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    if nocrop :
        autocroped = img
    else :
        autocroped = autocrop(img)

    target_width = 1000
    target_height = autocroped.shape[0] * target_width // autocroped.shape[1]

    resized = cv2.resize(autocroped, (target_width, target_height), interpolation=cv2.INTER_AREA)
    autocroped= cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    result = reader.readtext(autocroped)
    
    cv2.imwrite("./last_img.png", autocroped)

    processed_text = []
    positions = []
    for detection in result:
        for word in detection[1].split() : 
            processed_text.append(word_to_known(word,KNOWN_NAMES)[0])
            positions.append(detection[0])

    print("___________")
    print(processed_text)
    print("___________")

    endscreen = EndScreen()
    endscreen.parse(processed_text, positions,KNOWN_NAMES)
    return endscreen

if __name__ == "__main__" : 
    url = 'https://cdn.discordapp.com/attachments/1352249844466581694/1352662057874358383/precroped.png?ex=67ded435&is=67dd82b5&hm=e5d4dce83ca821acac0a618e26ef1fe3955a47dc360c4a7a9882f7c2b9c78804&'
    print(from_link_to_result(url,nocrop=True))
