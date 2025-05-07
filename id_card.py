import os
import json 

VOCABULARY = ['combat',
              'resume', 
              'kamas',
              'butin',
              'xp', 
              'alliance', 
              'combat', 
              'termine', 
              'victoire', 
              'defaite',
              'statistiques',
              'lvl',
              'personnage',
              'gagnants', 
              'gagne',
              'perdants',
              'gagne', 
              'score',
              'nom', 
              'de', 
              'niveau',
              'experience',
              'vulnerable', 
              ]

    

class IdCard () : 
    def __init__ (self, name) : 
        self.name = name

        self.perco_fight_win = 0
        self.perco_fight_loose = 0

        self.perco_loose_unpaid = 0
        self.perco_won_unpaid = 0

        self.perco_fight_total = 0

        self.prisme_loose_unpaid = 0
        self.prisme_won_unpaid = 0

        self.prisme_fight_win = 0
        self.prisme_fight_loose = 0

        self.prisme_fight_total = 0

        self.haschanged = False

        self.time = [] 

    def todict (self) : 
        return {
            "perco_fight_win" : self.perco_fight_win,
            "perco_fight_loose" : self.perco_fight_loose,
            "perco_fight_total" : self.perco_fight_total,
            "prisme_fight_win" : self.prisme_fight_win,
            "prisme_fight_loose" : self.prisme_fight_loose,
            "prisme_fight_total" : self.prisme_fight_total,
            "haschanged" : bool(self.haschanged),
            "perco_loose_unpaid" : self.perco_loose_unpaid,
            "perco_won_unpaid" : self.perco_won_unpaid,
            "prisme_loose_unpaid" : self.prisme_loose_unpaid,
            "prisme_won_unpaid" : self.prisme_won_unpaid,
            "time" :  ",".join([str(t) for t in self.time])
        },self.name
    
    def fromdict (self, dico) : 
        self.perco_fight_win = dico["perco_fight_win"]
        self.perco_fight_loose = dico["perco_fight_loose"]
        self.perco_fight_total = dico["perco_fight_total"]
        self.prisme_fight_win = dico["prisme_fight_win"]
        self.prisme_fight_loose = dico["prisme_fight_loose"]
        self.prisme_fight_total = dico["prisme_fight_total"]
        self.haschanged = bool(dico["haschanged"])
        self.perco_loose_unpaid = dico["perco_loose_unpaid"]
        self.perco_won_unpaid = dico["perco_won_unpaid"]
        self.prisme_loose_unpaid = dico["prisme_loose_unpaid"]
        self.prisme_won_unpaid = dico["prisme_won_unpaid"]
        self.time = [float(t) for t in dico["time"].split(",") if t != ""]

    def __str__ (self) :
        if self.name == "prisme" or self.name == "percepteur" :
            return ""
        txt_to_send = f"## Nom : {self.name}\n"
        txt_to_send += f"    Perco : `{self.perco_fight_win} / {self.perco_fight_loose} ({self.perco_fight_total})`\n"
        txt_to_send += f"    Prisme : `{self.prisme_fight_win} / {self.prisme_fight_loose} ({self.prisme_fight_total})`\n"
        txt_to_send += f"--------------- \n"
        txt_to_send += f"    Perco non payé : `{self.perco_loose_unpaid} (perdu) {self.perco_won_unpaid} (gagne)`\n"
        txt_to_send += f"    Prisme non payé : `{self.prisme_loose_unpaid} (perdu) {self.prisme_won_unpaid} (gagne)`\n"
        txt_to_send += f"--------------- \n"
        txt_to_send += f"temps (heure) des combats : `{self.time}`\n"
        txt_to_send += f"faut payer : **{self.haschanged}**\n"
        txt_to_send += f"--------------- \n"
        return txt_to_send

def cards_from_file () :
    if os.path.exists("cards.json") : 
        with open("cards.json", "r") as f :
            txt = f.read()
            if txt == "" :
                return []

        with open("cards.json", "r") as f : 
            dico = json.load(f)
            cards = []
            for name, values in dico.items() : 
                card = IdCard(name)
                card.fromdict(values)
                cards.append(card)
            return cards
    else :
        raise FileNotFoundError("cards.json not found. Please create the file first.")
    
def save_card (cards) :
    dico = {}
    for card in cards : 
        dico[card.name] = card.todict()[0]
    with open("cards.json", "w") as f : 
        json.dump(dico, f, indent=4)

def init_from_list (names) : 
    cards = []
    for name in names : 
        card = IdCard(name)
        cards.append(card)
    return cards

def open_known_names () : 
    if os.path.exists("known_names.txt") : 
        with open("known_names.txt", "r") as f : 
            names = f.read().splitlines()
            return names
    else :
        raise FileNotFoundError("known_names.txt not found. Please create the file first.")
    
def save_known_names (names) :
    with open("known_names.txt", "w") as f : 
        f.write("\n".join(names))

def open_saved_hash () : 
    hashes = []
    if os.path.exists("saved_hash.txt") : 
        with open("saved_hash.txt", "r") as f : 
            hashes = f.read().splitlines()
            print("open saved_hash : ", hashes)
            return hashes
            
    else :
        raise FileNotFoundError("saved_hash.txt not found. Please create the file first.")
    
def save_saved_hash (hash) :
    with open("saved_hash.txt", "w") as f : 
        f.write("\n".join([str(h) for h in hash]))
