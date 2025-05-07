import cv2
import numpy as np
import os
import jellyfish
from screen.autocrop_sift import autocrop
from paddleocr import PaddleOCR 

from scipy.cluster.vq import kmeans, vq
import urllib3
import time 

import discord

# --- Initialize PaddleOCR ---
# Done globally once to load models into memory. Adjust path if needed.
# use_angle_cls=False might speed things up slightly if text is always horizontal
print("Initializing PaddleOCR Engine...")
start_init = time.time()
try:
    ocr_engine = PaddleOCR(use_angle_cls=True, lang='fr', use_gpu=False, show_log=False)
    print(f"PaddleOCR Engine initialized in {time.time() - start_init:.2f}s")
except Exception as e:
    print(f"FATAL: Failed to initialize PaddleOCR. Installation correct? Error: {e}")
    # Handle exit or raise exception depending on desired bot behavior
    exit()
# ---------------------------

# Assuming id_card.py contains your VOCABULARY list
try:
    from id_card import VOCABULARY
except ImportError:
    print("WARN: id_card.py not found or VOCABULARY not defined. Using empty list.")
    VOCABULARY = []

DEBUG = False

# --- Helper functions (isnumber, isvalidname, distance, preprocess, word_to_known) remain unchanged ---
def isnumber (word) :
    return word.replace('.','',1).replace(",",'',1).replace("-",'',1).replace(":",'',1).isdigit()

def isvalidname(word) :
    return word != " " and word != "" and word != "-" and word != "_"and len(word) > 1 and not(word[0].isdigit()) and (not "%" in word)

def distance(text1, text2) :
    return jellyfish.levenshtein_distance(text1, text2)

def preprocess (word) :
    no_accent = {"é":"e", "è":"e", "ê":"e", "à":"a", "â":"a", "î":"i", "ï":"i", "ô":"o", "ù":"u", "û":"u", "ç":"c"}
    word = word.lower()
    for key in no_accent.keys() :
        word = word.replace(key, no_accent[key])
    return word

def word_to_known(word,KNOWN_NAMES) :
    # Check if word is purely punctuation or junk before processing
    # This might need refinement based on typical OCR errors
    import string
    if all(c in string.punctuation or c.isspace() for c in word):
        return word, float('inf') # Treat as invalid/unknown

    processed_word = preprocess(word)
    min_dist = float("inf")
    known = None

    if isnumber(processed_word) : # Use processed_word for isnumber check too
        return word, -1 # Return original number string

    # Combine VOCABULARY and KNOWN_NAMES for matching
    # Ensure KNOWN_NAMES is a list of strings
    if not isinstance(KNOWN_NAMES, list):
        print("WARN: KNOWN_NAMES is not a list. Using empty list.")
        search_names = []
    else:
        search_names = KNOWN_NAMES

    search_space = list(set(VOCABULARY + search_names)) # Use set for efficiency

    best_match_in_space = None
    for w in search_space :
        # Ensure vocab/known names are strings
        if not isinstance(w, str): continue
        dist = distance(processed_word, preprocess(w))
        if dist < min_dist :
            min_dist = dist
            best_match_in_space = w


    match_threshold = 3 

    if min_dist <= match_threshold :
        return best_match_in_space, min_dist
    # Otherwise, return the original word (as processed) only if it's considered valid
    # This prevents returning slightly modified junk
    elif isvalidname(word): # Check original word validity
         return word, float("inf") # Return original word but mark as not a known match
    else:
         return word, float("inf") # Return original word (likely junk)


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
        # Ensure time comparison handles potential float inaccuracies
        if set(self.winners) & set(other.winners) and abs(self.time - other.time) < 0.01 :
            self.winners = list(set(self.winners) | set(other.winners))
            self.losers = list(set(self.losers) | set(other.losers))
        else :
            raise ValueError("Cannot concatenate two different results (namesets or time mismatch)")


    def parse (self, processed_text, positions, KNOWN_NAMES) :
        if not isinstance(KNOWN_NAMES, list):
            print("WARN: KNOWN_NAMES is not a list in parse(). Setting to empty.")
            KNOWN_NAMES = []

        names = []
        name_positions = [] # Stores the boxes associated with detected names

        noname = []
        noname_positions = [] # Stores boxes associated with non-name words

        if not processed_text or len(processed_text) != len(positions):
            raise ValueError("Processed text and positions are misaligned or empty.")

        # This loop categorizes words based on whether they are likely names
        for idx, word in enumerate(processed_text):
            # Check word validity carefully
            if isinstance(word, str) and \
               word not in VOCABULARY and \
               not isnumber(word) and \
               isvalidname(word) :
                _, known_dist = word_to_known(word, KNOWN_NAMES + VOCABULARY) # Check against combined list
                if known_dist == float('inf'): # Only treat as potential name if it didn't match anything known
                    names.append(word)
                    name_positions.append(positions[idx])
                else: # Matched vocab/number/known_name or was invalid
                    noname.append(word)
                    noname_positions.append(positions[idx])

            elif isinstance(word, str): # It's a vocab word, number, known name, or invalid name
                noname.append(word)
                noname_positions.append(positions[idx])
            else:
                # Handle potential non-string entries if necessary
                print(f"WARN: Non-string item in processed_text at index {idx}: {word}")


        if len(names) == 0 :
             print("WARN: No potential new player names identified.")
             # Attempt to use KNOWN_NAMES that were found in `noname` list?
             # This part needs careful thought based on expected input.
             # For now, proceed, but winner/loser lists might be empty.
             # raise ValueError("No potential new player names found") # Maybe too strict

        # --- Position Analysis ---
        # Ensure positions are valid lists/tuples before accessing indices
        valid_name_positions = [pos for pos in name_positions if isinstance(pos, (list, tuple)) and len(pos) == 4]
        if not valid_name_positions:
             if names: # If we had name candidates but no valid positions
                  raise ValueError("Names found but no valid positions associated.")
             else: # No names and no positions, proceed cautiously
                  print("WARN: No names and no valid positions found.")
                  allYs = []
                  allXs = []
        else:
             # Use top-left Y (index 0, sub-index 1) and top-left X (index 0, sub-index 0)
             # Wrap in float() for kmeans later
             allYs = [float(pos[0][1]) for pos in valid_name_positions]
             allXs = [float(pos[0][0]) for pos in valid_name_positions]

        print("---------------")
        print("Potential Names Found: ", names) # Includes only words NOT in KNOWN_NAMES/VOCAB
        print("Associated Ys:", allYs)
        print("Associated Xs:", allXs)
        print("Non-Name Words Found: ", noname)
        print("---------------")

        meanposrobust = 0
        nb_known_in_noname = 0 # Check noname list for known members to find column X

        # Find the X-coordinate based on known names found in the 'noname' list
        for idx, word in enumerate(noname):
             if word in KNOWN_NAMES:
                  # Ensure corresponding position is valid
                  if idx < len(noname_positions) and isinstance(noname_positions[idx], (list, tuple)) and len(noname_positions[idx]) == 4:
                       try:
                           meanposrobust += float(noname_positions[idx][0][0]) # Top-left X
                           nb_known_in_noname += 1
                       except (TypeError, IndexError) as e:
                           print(f"WARN: Error accessing position for known name {word}: {e}")
                  else:
                       print(f"WARN: Invalid or missing position for known name {word}")


        if nb_known_in_noname > 0 :
            meanposrobust /= nb_known_in_noname
            print("MEAN POS ROBUST (based on KNOWN_NAMES found in text): ", meanposrobust)
        # Fallback if no known names found: use median X of potential names if available
        elif len(allXs) > 0:
             meanposrobust = np.median(allXs)
             print(f"WARN: No KNOWN_NAMES found in text, using median X of potential names: {meanposrobust}")
        else:
             # No known names, no potential names with positions - cannot determine alignment
             print("ERROR: Cannot determine name column alignment (no known names, no potential names with X coords).")
             # Handle this case: maybe skip winner/loser assignment or raise error
             # For now, we can't proceed with alignment filtering.
             # Let's just use all found potential names without filtering by X.
             good_names = names
             good_positions = valid_name_positions # Use the positions we have
             good_y = allYs # Use the Ys we have
             meanposrobust = -1 # Indicate alignment wasn't used

             # raise ValueError("Cannot determine name column X position") # Maybe too strict


        # Filter potential names by proximity to the determined X-column if alignment was found
        if meanposrobust != -1:
            good_names = []
            good_positions = []
            good_y = []
            # Adjust threshold? PaddleOCR line boxes might be wider/less precise per word.
            pos_threshold = 100 # Increased further, tune this based on typical column width
            for idx, name in enumerate(names):
                 # Check against the corresponding X position
                 if idx < len(allXs) and np.abs(allXs[idx] - meanposrobust) < pos_threshold :
                     good_names.append(name)
                     good_positions.append(valid_name_positions[idx])
                     good_y.append(allYs[idx])

            print("-"*20)
            print("Names near alignment X: ", good_names)
            print("-"*20)
        else:
             print("WARN: Skipping X-alignment filtering.")


        # --- Winner/Loser Separation ---
        # Combine 'good_names' (potential new names near column) with KNOWN_NAMES found in text
        final_participants = list(set(good_names + [n for n in noname if n in KNOWN_NAMES]))
        final_positions = []
        final_y = []

        # Get positions/Y for the known names added
        known_name_indices = [i for i, word in enumerate(noname) if word in KNOWN_NAMES]
        known_name_positions = [noname_positions[i] for i in known_name_indices if i < len(noname_positions) and isinstance(noname_positions[i], (list, tuple)) and len(noname_positions[i]) == 4]
        known_name_y = [float(pos[0][1]) for pos in known_name_positions]

        # Combine data for all participants (good potential names + known names found)
        combined_names = good_names + [noname[i] for i in known_name_indices]
        combined_y = good_y + known_name_y

        if not combined_names:
             print("WARN: No participants identified after filtering and combining. Cannot assign winners/losers.")
        # Proceed only if we have participants with Y coordinates
        elif combined_y:
            perdants_found = "perdants" in noname
            frontiere = -1

            if perdants_found:
                print("'perdants' keyword found!")
                try:
                    # Find the Y position of 'perdants' - use top Y coordinate
                    perdants_idx = noname.index("perdants")
                    if perdants_idx < len(noname_positions) and isinstance(noname_positions[perdants_idx], (list, tuple)) and len(noname_positions[perdants_idx]) == 4:
                         frontiere = float(noname_positions[perdants_idx][0][1])
                         print(f"Frontier Y based on 'perdants': {frontiere}")
                    else:
                         print("WARN: Found 'perdants' but no valid position. Cannot use for separation.")
                         perdants_found = False # Fallback to KMeans if possible

                except (ValueError, TypeError, IndexError) as e:
                    print(f"Error getting 'perdants' position: {e}. Falling back.")
                    perdants_found = False # Fallback

            # Use 'perdants' frontier if found and valid
            if perdants_found and frontiere != -1:
                for idx, name in enumerate(combined_names):
                    if idx < len(combined_y):
                        if combined_y[idx] > frontiere :
                            self.losers.append(name)
                        else :
                            self.winners.append(name)
                    else: print(f"WARN: Missing Y coord for participant {name}")

            # Fallback to KMeans if 'perdants' not usable and enough distinct Y values exist
            elif len(np.unique(combined_y)) >= 2 :
                print("Using KMeans to separate winners/losers.")
                try:
                    # Ensure combined_y is a numpy array of floats for kmeans
                    combined_y_array = np.array(combined_y, dtype=float).reshape(-1, 1)
                    centroids, _ = kmeans(combined_y_array, 2) # k=2 for winners/losers
                    centroids = np.sort(centroids.flatten())
                    print(f"KMeans centroids: {centroids}")

                    for idx, name in enumerate(combined_names) :
                        if idx < len(combined_y):
                            # Compare distance to the two centroids
                            if np.abs(combined_y[idx] - centroids[0]) > np.abs(combined_y[idx] - centroids[1]) :
                                self.losers.append(name)
                            else :
                                self.winners.append(name)
                        else: print(f"WARN: Missing Y coord for participant {name}")

                except Exception as e:
                    print(f"KMeans failed: {e}. Assigning all participants as winners (fallback).")
                    self.winners.extend(combined_names) # Fallback if KMeans errors

            # Handle case where separation is not possible (e.g., < 2 unique Y values, no 'perdants')
            else:
                 print("WARN: Cannot separate winners/losers (not enough distinct Y values / no 'perdants'). Assigning all as winners (fallback).")
                 self.winners.extend(combined_names)

        # Ensure winners/losers lists contain unique names
        self.winners = sorted(list(set(self.winners)))
        self.losers = sorted(list(set(self.losers)))


        # --- Determine Win/Loss/Target/Time ---
        # Determine wewon based on KNOWN_NAMES intersection with winners/losers
        known_winners = set(self.winners) & set(KNOWN_NAMES)
        known_losers = set(self.losers) & set(KNOWN_NAMES)

        if known_winners:
            self.wewon = True
        elif known_losers:
             self.wewon = False
        else:
             # Ambiguous if KNOWN_NAMES is empty or doesn't match anyone who participated
             self.wewon = None # Indicate uncertainty
             print("WARN: Could not determine win/loss based on KNOWN_NAMES found in participant lists.")


        # Check for Prisme/Percepteur keywords
        if 'prisme' in noname :
            self.prism = True
            self.perco = False # Ensure mutually exclusive
        elif 'percepteur' in noname :
             self.perco = True
             self.prism = False
        else:
             # Default or raise error if neither found?
             self.perco = None # Indicate uncertainty
             self.prism = None
             print("WARN: Could not determine if Percepteur or Prisme based on keywords.")


        # Find Time after 'statistiques'
        try:
            # Find last occurrence of 'statistiques' in case it appears multiple times
            stats_indices = [i for i, x in enumerate(noname) if x == 'statistiques']
            if stats_indices:
                stats_idx = stats_indices[-1] # Use the last one
                # Look for a number immediately after
                if stats_idx + 1 < len(noname) and isnumber(noname[stats_idx+1]):
                    time_str = noname[stats_idx+1].replace(',', '.').replace(":", '.', 1)
                    # Basic handling for potential extra hyphens if isnumber allows them
                    if '-' in time_str and not time_str.startswith('-'):
                         parts = time_str.split('-')
                         if len(parts) == 2 and parts[0].replace('.', '', 1).isdigit():
                              time_str = parts[0] # Take first part if MM-SS like format
                    self.time = float(time_str)
                else:
                     print("WARN: 'statistiques' found, but next word is not a number.")
            else:
                 print("WARN: 'statistiques' keyword not found.")


        except (ValueError, IndexError, TypeError) as e:
            print(f"Could not find/parse time after 'statistiques': {e}")
            self.time = -1 # Keep default if parsing fails


    # --- __str__, save, to_embed, hash methods remain largely unchanged ---
    # (Added checks for None values in __str__ and to_embed)
    def __str__ (self) :
        to_print = ""
        if self.wewon is True :
            to_print += "**On a gagné ! Bravo**\n"
        elif self.wewon is False:
            to_print += "**On a perdu ... tanpis**\n"
        else:
            to_print += "**Résultat indéterminé**\n" # Handle None case

        to_print += "\n"
        to_print += "## Gagnants : \n"
        winner_list = "\n".join(f"**{name}**" for name in self.winners) if self.winners else "*(Aucun)*"
        to_print += winner_list + "\n"

        to_print += "\n"
        to_print += "## Perdants : \n"
        loser_list = "\n".join(f"**{name}**" for name in self.losers) if self.losers else "*(Aucun)*"
        to_print += loser_list + "\n"

        to_print += "\n"
        if self.prism is True :
            to_print += "c'était contre un prisme !\n"
        elif self.perco is True:
            to_print += "c'était contre un percepteur !\n"
        else:
            to_print += "Type de cible indéterminé.\n" # Handle None case

        to_print += "\n"
        if self.time != -1:
             to_print += "le combat a duré pendant : `"+str(self.time)+" minutes`\n"
        else:
             to_print += "Durée du combat non trouvée.\n"
        to_print += "\n"

        return to_print

    def save(self, IDs,timestamp) : # Assumes IDs is a list of objects with attributes like name, etc.
        if not IDs: return # No one to save stats for

        for player_id_obj in IDs :
            # Check if the object has a 'name' attribute
            if not hasattr(player_id_obj, 'name'):
                print(f"WARN: Skipping object in IDs list as it has no 'name' attribute: {player_id_obj}")
                continue

            player_name = player_id_obj.name
            is_winner = player_name in self.winners
            is_loser = player_name in self.losers

            if not is_winner and not is_loser: continue # Player wasn't in this fight result

            # Ensure attributes exist before incrementing (optional, good practice)
            for attr in ['prisme_fight_win', 'prisme_fight_total', 'prisme_won_unpaid',
                         'perco_fight_win', 'perco_fight_total', 'perco_won_unpaid',
                         'prisme_fight_loose', 'prisme_loose_unpaid', 'perco_fight_loose',
                         'perco_loose_unpaid', 'time', 'haschanged']:
                 if not hasattr(player_id_obj, attr):
                      # Initialize if missing (e.g., set counters to 0, time to [], haschanged to False)
                      if attr == 'time': setattr(player_id_obj, attr, [])
                      elif attr == 'haschanged': setattr(player_id_obj, attr, False)
                      else: setattr(player_id_obj, attr, 0)


            if is_winner:
                if self.prism is True:
                    player_id_obj.prisme_fight_win += 1
                    player_id_obj.prisme_fight_total += 1
                    player_id_obj.prisme_won_unpaid += 1
                    player_id_obj.time.append(timestamp)
                    player_id_obj.haschanged = True
                elif self.perco is True:
                    player_id_obj.perco_fight_win += 1
                    player_id_obj.perco_fight_total += 1
                    player_id_obj.perco_won_unpaid += 1
                    player_id_obj.time.append(timestamp)
                    player_id_obj.haschanged = True
                # else: Do nothing if target type unknown but player won

            elif is_loser:
                if self.prism is True:
                    player_id_obj.prisme_fight_loose += 1
                    player_id_obj.prisme_fight_total += 1 # Also increment total on loss
                    player_id_obj.prisme_loose_unpaid += 1
                    player_id_obj.time.append(timestamp)
                    player_id_obj.haschanged = True
                elif self.perco is True:
                    player_id_obj.perco_fight_loose += 1
                    player_id_obj.perco_fight_total += 1 # Also increment total on loss
                    player_id_obj.perco_loose_unpaid += 1
                    player_id_obj.time.append(timestamp)
                    player_id_obj.haschanged = True
                # else: Do nothing if target type unknown but player lost


    def to_embed(self, timestamp_str=None) -> discord.Embed:
        """Creates a Discord Embed representation of the screen result."""

        # Determine color and result text based on win/loss/unknown
        if self.wewon is True:
            embed_color = discord.Color.green()
            result_emoji = "✅"
            result_text = "Victoire !"
        elif self.wewon is False:
            embed_color = discord.Color.red()
            result_emoji = "❌"
            result_text = "Défaite..."
        else:
            embed_color = discord.Color.greyple() # Grey for unknown
            result_emoji = "❓"
            result_text = "Résultat Indéterminé"

        # Determine target type
        if self.prism is True:
            target_emoji = "💎"
            target_text = "Prisme"
        elif self.perco is True:
            target_emoji = "💰"
            target_text = "Percepteur"
        else:
            target_emoji = "❔"
            target_text = "Cible Inconnue"


        # Create the embed instance
        embed_desc = f"**{result_text}** contre un(e) {target_text.lower()}."
        if self.time != -1:
            embed_desc += f"\nDurée: `{self.time} minutes`"
        else:
            embed_desc += f"\nDurée: `Inconnue`"

        embed = discord.Embed(
            title=f"{result_emoji} Résultat du Combat ({target_text})",
            description=embed_desc,
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

        return embed

    def hash (self) :
        # Use sorted lists to ensure hash is consistent regardless of order
        win_sorted = sorted(self.winners)
        los_sorted = sorted(self.losers)
        # Convert None to string 'None' for consistent hashing
        prism_str = str(self.prism)
        perco_str = str(self.perco)
        wewon_str = str(self.wewon)
        time_str = str(self.time)
        return str(win_sorted)+str(los_sorted)+prism_str+perco_str+time_str+wewon_str


# --- Main processing function updated for PaddleOCR ---
def from_link_to_result (url,KNOWN_NAMES,nocrop=False) :
    # Ensure KNOWN_NAMES is a list
    if not isinstance(KNOWN_NAMES, list):
        print("WARN: KNOWN_NAMES passed to from_link_to_result is not a list. Using empty list.")
        KNOWN_NAMES = []

    http = urllib3.PoolManager()
    try:
        r = http.request('GET', url)
        if r.status != 200:
             raise ValueError(f"Failed to download image. Status code: {r.status}")
        print("Image downloaded successfully.")
    except urllib3.exceptions.MaxRetryError as e:
         raise ValueError(f"Network error downloading image: {e}")
    except Exception as e:
         raise ValueError(f"Error downloading image: {e}")


    arr = np.asarray(bytearray(r.data), dtype=np.uint8)
    # Decode as color image
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image.")
    print(f"Image decoded, shape: {img.shape}")

    # --- Image Preprocessing ---
    # 1. Cropping
    autocroped = None # Initialize
    if nocrop :
        autocroped = img
        print("Skipping autocrop.")
    else :
        print("Applying autocrop...")
        try:
            autocroped_result = autocrop(img)
            if isinstance(autocroped_result, np.ndarray) and autocroped_result.size > 0:
                autocroped = autocroped_result
                print(f"Autocrop successful, new shape: {autocroped.shape}")
            else:
                print("WARN: Autocrop did not return a valid NumPy array or was empty. Using original image.")
                autocroped = img # Fallback
        except Exception as e:
             print(f"ERROR during autocrop: {e}. Using original image.")
             autocroped = img


    if autocroped is None or autocroped.size == 0:
         raise ValueError("Image is empty after preprocessing (crop stage).")

    # 2. Resizing
    resized = None # Initialize
    target_width = 1000 # Keep or adjust
    if autocroped.shape[0] > 0 and autocroped.shape[1] > 0:
        target_height = int(autocroped.shape[0] * target_width / autocroped.shape[1])
        # INTER_CUBIC is often a good balance for quality
        resized = cv2.resize(autocroped, (target_width, target_height), interpolation=cv2.INTER_CUBIC)
        print(f"Image resized to: {resized.shape}")
    else:
        print("WARN: Invalid dimensions for resizing. Using image as is after crop.")
        resized = autocroped # Use the result from cropping

    if resized is None or resized.size == 0:
         raise ValueError("Image is empty after preprocessing (resize stage).")

    # 3. Ensure RGB format (PaddleOCR might prefer RGB, OpenCV uses BGR)
    # Although PaddleOCR often handles BGR too, explicit conversion is safer.
    # If your 'resized' image is already RGB (e.g. from PIL), skip cvtColor.
    # Assuming 'resized' is from cv2.resize (so BGR):
    try:
        img_for_ocr = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        print("Converted image to RGB for PaddleOCR.")
    except cv2.error as e:
        print(f"WARN: Could not convert image to RGB (maybe already RGB or grayscale?): {e}. Using as is.")
        img_for_ocr = resized


    # --- PaddleOCR Call ---
    print("Running PaddleOCR...")
    start_ocr = time.time()
    try:
        # Pass the numpy array directly
        # cls=True enables angle classification (might help if text is slightly rotated)
        ocr_result = ocr_engine.ocr(img_for_ocr, cls=True)
    except Exception as e:
        print(f"ERROR: PaddleOCR execution failed: {e}")
        # Depending on the error, you might want to retry or raise
        raise ValueError("PaddleOCR processing failed") from e

    print(f"PaddleOCR finished in {time.time() - start_ocr:.2f}s")

    # --- Process PaddleOCR Output ---
    processed_text = []
    positions = [] # Store the BOXES associated with words

    if not ocr_result or not ocr_result[0]: # Check structure
         print("WARN: PaddleOCR returned no results.")
    else:
        print(f"PaddleOCR detected {len(ocr_result[0])} lines.")
        # Paddle returns list containing one list of results per image
        for line_idx, line_data in enumerate(ocr_result[0]):
            # line_data format: [bounding_box, (text, confidence)]
            # bounding_box: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            # text: string
            # confidence: float
            try:
                box = line_data[0]
                text = line_data[1][0]
                confidence = line_data[1][1]

                # Filter based on confidence (tune this threshold)
                confidence_threshold = 0.5 # Example threshold
                if confidence < confidence_threshold:
                    # print(f"Skipping line {line_idx} due to low confidence ({confidence:.2f}): '{text}'")
                    continue

                # Split the detected line into words
                words = text.split()
                if not words: continue # Skip if line is empty after split

                # Apply word_to_known and store results
                for word in words:
                    known_word, _ = word_to_known(word, KNOWN_NAMES)
                    processed_text.append(known_word)
                    # *** Approximation: Assign the LINE's bounding box to EACH WORD ***
                    # This is necessary because PaddleOCR gives line boxes, but your
                    # parse function expects word-level positions for alignment/separation.
                    # This might affect the accuracy of X/Y coordinate analysis in parse().
                    positions.append(box)

            except (IndexError, TypeError) as e:
                print(f"WARN: Error processing line {line_idx} from PaddleOCR results: {e}. Line data: {line_data}")
                continue


    print("___________ PaddleOCR Processed Text___________")
    print(processed_text)
    # print(positions) # Can be very verbose
    print("___________________________________________")

    # --- Parse using the existing EndScreen class ---
    endscreen = EndScreen()
    try:
        endscreen.parse(processed_text, positions, KNOWN_NAMES)
        print("EndScreen parsing successful.")
    except ValueError as e:
         print(f"Error parsing results: {e}")
         # Handle error - maybe return a default/error EndScreen object?
         raise # Re-raise for now
    except Exception as e:
         print(f"Unexpected error during parsing: {e}")
         # Handle other potential errors during parsing
         raise

    return endscreen

# --- Example Usage ---
if __name__ == "__main__" :
    # Define some dummy KNOWN_NAMES for testing
    # Replace with your actual list loaded from wherever it comes from
    TEST_KNOWN_NAMES = ["Lovova", "Yaafou", "Artisana", "Naicri", "Zz-Floki-Zz", "Kyoriga", "Mojito"] # Example known names from the previous output
    # Define dummy VOCABULARY or ensure id_card.py is correct
    # Example:
    if 'VOCABULARY' not in globals():
         VOCABULARY = ["gagnants", "perdants", "prisme", "percepteur", "statistiques", "combat", "tour", "personnage", "resume", "niveau", "expérience", "gagnée", "kamas", "butin", "terminé"] # Add expected non-name words, including variations if needed


    url = 'https://cdn.discordapp.com/attachments/1352249844466581694/1352662057874358383/precroped.png?ex=67ded435&is=67dd82b5&hm=e5d4dce83ca821acac0a618e26ef1fe3955a47dc360c4a7a9882f7c2b9c78804&'
    try:
        print(f"Processing URL: {url}")
        print(f"Using KNOWN_NAMES: {TEST_KNOWN_NAMES}")
        # Set nocrop=True if the image is already cropped like in the example URL
        result_screen = from_link_to_result(url, TEST_KNOWN_NAMES, nocrop=True)
        print("\n--- Parsed Result (PaddleOCR) ---")
        print(result_screen)

        # Example of creating an embed (requires discord.py)
        # Make sure discord is installed: uv pip install discord.py
        try:
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            embed = result_screen.to_embed(now_str)
            print("\n--- Embed Data ---")
            # print(embed.to_dict()) # Print embed data for verification
        except ImportError:
            print("\nWARN: discord.py not installed, cannot generate embed.")
        except Exception as e:
            print(f"\nERROR generating embed: {e}")


    except ValueError as e:
        print(f"Processing failed: {e}")
    except Exception as e:
        import traceback
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc() # Print full traceback for unexpected errors
