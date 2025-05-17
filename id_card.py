import os
import json 

VOCABULARY = [
    'combat', 'resume', 'kamas', 'butin', 'xp', 'alliance', 'termine',
    'victoire', 'defaite', 'statistiques', 'lvl', 'personnage',
    'gagnants', 'gagne', 'perdants', 'score', 'nom', 'de', 'niveau',
    'experience', 'vulnerable',
]

class IdCard():
    def __init__(self, name):
        self.name = name  # Primary identifier, often cleaned Discord display name

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
        self.ingame_aliases = []  # NEW: List to store in-game aliases

    def todict(self):
        return {
            "perco_fight_win": self.perco_fight_win,
            "perco_fight_loose": self.perco_fight_loose,
            "perco_fight_total": self.perco_fight_total,
            "prisme_fight_win": self.prisme_fight_win,
            "prisme_fight_loose": self.prisme_fight_loose,
            "prisme_fight_total": self.prisme_fight_total,
            "haschanged": bool(self.haschanged),
            "perco_loose_unpaid": self.perco_loose_unpaid,
            "perco_won_unpaid": self.perco_won_unpaid,
            "prisme_loose_unpaid": self.prisme_loose_unpaid,
            "prisme_won_unpaid": self.prisme_won_unpaid,
            "time": ",".join([str(t) for t in self.time]),
            "ingame_aliases": self.ingame_aliases  # NEW: Serialize aliases
        }, self.name

    def fromdict(self, dico):
        self.perco_fight_win = dico.get("perco_fight_win", 0)
        self.perco_fight_loose = dico.get("perco_fight_loose", 0)
        self.perco_fight_total = dico.get("perco_fight_total", 0)
        self.prisme_fight_win = dico.get("prisme_fight_win", 0)
        self.prisme_fight_loose = dico.get("prisme_fight_loose", 0)
        self.prisme_fight_total = dico.get("prisme_fight_total", 0)
        self.haschanged = bool(dico.get("haschanged", False))
        self.perco_loose_unpaid = dico.get("perco_loose_unpaid", 0)
        self.perco_won_unpaid = dico.get("perco_won_unpaid", 0)
        self.prisme_loose_unpaid = dico.get("prisme_loose_unpaid", 0)
        self.prisme_won_unpaid = dico.get("prisme_won_unpaid", 0)
        self.time = [float(t) for t in dico.get("time", "").split(",") if t.strip()] # Ensure t is not empty string
        self.ingame_aliases = dico.get("ingame_aliases", [])  # NEW: Deserialize, default to empty list

    def __str__(self):
        if self.name == "prisme" or self.name == "percepteur":
            return ""
        txt_to_send = f"## Nom Principal (Discord): {self.name}\n"
        if self.ingame_aliases:
            aliases_str = ", ".join(f"`{alias}`" for alias in self.ingame_aliases)
            txt_to_send += f"    Alias en jeu: {aliases_str}\n"  # NEW: Display aliases
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

def _ensure_file_exists(filepath, default_content_writer):
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            default_content_writer(f)
        return True
    return False

def cards_from_file():
    _ensure_file_exists("cards.json", lambda f: json.dump({}, f))
    with open("cards.json", "r") as f:
        txt = f.read()
        if not txt.strip():
            return []
        dico = json.loads(txt) # Use loaded txt
        cards = []
        for name, values in dico.items():
            card = IdCard(name)
            card.fromdict(values)
            cards.append(card)
        return cards

def save_card(cards):
    dico = {}
    for card in cards:
        card_data, _ = card.todict()
        dico[card.name] = card_data
    with open("cards.json", "w") as f:
        json.dump(dico, f, indent=4)

def init_from_list(names):
    cards = []
    for name in names:
        card = IdCard(name)
        cards.append(card)
    return cards

def open_known_names():
    _ensure_file_exists("known_names.txt", lambda f: f.write(""))
    with open("known_names.txt", "r") as f:
        names = f.read().splitlines()
        return [name for name in names if name.strip()]

def save_known_names(names):
    with open("known_names.txt", "w") as f:
        f.write("\n".join(names))

def open_saved_hash():
    _ensure_file_exists("saved_hash.txt", lambda f: f.write(""))
    with open("saved_hash.txt", "r") as f:
        hashes = f.read().splitlines()
        return [h for h in hashes if h.strip()]

def save_saved_hash(hash_list):
    with open("saved_hash.txt", "w") as f:
        f.write("\n".join([str(h) for h in hash_list]))