# screen/EndScreen.py
import discord
import random
import hashlib # For proper hashing
import logging

# Adjust import path if necessary
# Assuming parsing_pipeline.py is in the same directory or its path is correctly set up
try:
    from .parsing_pipeline import stage0, stage1, stage2, stage3
except ImportError:
    # Fallback for direct execution or different project structure
    try:
        from parsing_pipeline import stage0, stage1, stage2, stage3
        logger.warning("Using fallback import for parsing_pipeline. Ensure structure is correct.")
    except ImportError as e_fallback:
        logger.critical(f"CRITICAL: Failed to import parsing_pipeline: {e_fallback}. Parsing will fail.")
        stage0, stage1, stage2, stage3 = None, None, None, None


logger = logging.getLogger(__name__)

class EndScreen :

    def __init__ (self) :
        self.img = None
        self.raw_result = None
        self.winners = []
        self.losers = []
        self.alliance = None
        self.prism = None
        self.perco = None
        self.wewon = None
        self.hash_code = None
        self.time = -1

    def concat (self, other: 'EndScreen'):
        if (self.prism is not None and other.prism is not None and self.prism != other.prism) or \
           (self.perco is not None and other.perco is not None and self.perco != other.perco):
            raise ValueError("Cannot concatenate: Fight types (Prism/Perco) conflict.")

        self.winners = sorted(list(set(self.winners) | set(other.winners)))
        self.losers = sorted(list(set(self.losers) | set(other.losers)))

        if self.wewon is None:
            self.wewon = other.wewon
        elif other.wewon is not None and self.wewon != other.wewon:
            logger.warning(f"Conflicting 'wewon' status during concatenation. Keeping first: {self.wewon}")

        if self.prism is None: self.prism = other.prism
        elif other.prism is True: self.prism = True

        if self.perco is None: self.perco = other.perco
        elif other.perco is True: self.perco = True
        
        # if other.time > self.time: self.time = other.time # If time parsing is added
        logger.info("Concatenated EndScreen results.")


    def __str__ (self) :
        details = f"Winners: {self.winners}, Losers: {self.losers}, Prism: {self.prism}, Perco: {self.perco}, WeWon: {self.wewon}, Hash: {self.hash() if self.hash_code else 'Not Set'}"
        return f"<EndScreen Object - {details}>"

    def save(self, id_card_list):
        """
        Updates statistics for players involved in the fight.
        id_card_list: A list of IdCard objects.
                      The method will try to match detected names (self.winners, self.losers)
                      against IdCard.name or IdCard.ingame_aliases.
        """
        if not id_card_list:
            logger.warning("EndScreen.save called with empty id_card_list.")
            return

        logger.info(f"Saving stats for fight result. Winners: {self.winners}, Losers: {self.losers}. Prism: {self.prism}, Perco: {self.perco}")
        updated_id_cards_primary_names = []

        # Iterate through all IdCard objects provided
        for card_obj in id_card_list:
            if not hasattr(card_obj, 'name') or not hasattr(card_obj, 'ingame_aliases'):
                logger.warning(f"Skipping object in id_card_list: missing 'name' or 'ingame_aliases' attribute. Object: {card_obj}")
                continue

            # Determine if this IdCard (via primary name or alias) was in the fight
            player_primary_name = card_obj.name
            player_aliases = card_obj.ingame_aliases if isinstance(card_obj.ingame_aliases, list) else []
            
            is_winner = False
            is_loser = False

            # Check if primary name is in winners/losers
            if player_primary_name in self.winners:
                is_winner = True
            elif player_primary_name in self.losers:
                is_loser = True
            
            # If not found by primary name, check aliases
            if not is_winner and not is_loser:
                for alias in player_aliases:
                    if alias in self.winners:
                        is_winner = True
                        logger.debug(f"Matched winner '{alias}' to IdCard '{player_primary_name}' via alias.")
                        break
                    elif alias in self.losers:
                        is_loser = True
                        logger.debug(f"Matched loser '{alias}' to IdCard '{player_primary_name}' via alias.")
                        break
            
            # Skip if this IdCard (neither primary name nor any alias) was involved
            if not is_winner and not is_loser:
                continue

            # --- Stat update logic (same as before, but applied to card_obj) ---
            # Ensure stat attributes exist (initialize if first time using your IdCard's defaults)
            # IdCard class already initializes these, so ensure_attr might not be strictly needed if IdCards are always constructed properly.
            # However, it's safer if IdCard objects could come from older data without all fields.
            def ensure_attr(obj, attr_name, default_value=0):
                if not hasattr(obj, attr_name):
                    setattr(obj, attr_name, default_value)
                    logger.debug(f"Initialized missing attribute '{attr_name}' on IdCard '{obj.name}'.")

            ensure_attr(card_obj, 'prisme_fight_win')
            ensure_attr(card_obj, 'prisme_fight_total')
            ensure_attr(card_obj, 'perco_fight_win')
            ensure_attr(card_obj, 'perco_fight_total')
            ensure_attr(card_obj, 'prisme_fight_loose')
            ensure_attr(card_obj, 'perco_fight_loose')
            ensure_attr(card_obj, 'prisme_won_unpaid')
            ensure_attr(card_obj, 'perco_won_unpaid')
            ensure_attr(card_obj, 'prisme_loose_unpaid')
            ensure_attr(card_obj, 'perco_loose_unpaid')
            ensure_attr(card_obj, 'haschanged', False)
            # ---

            card_was_updated_this_fight = False
            if is_winner:
                if self.prism:
                    card_obj.prisme_fight_win += 1
                    card_obj.prisme_fight_total += 1
                    card_obj.prisme_won_unpaid += 1
                    card_was_updated_this_fight = True
                elif self.perco:
                    card_obj.perco_fight_win += 1
                    card_obj.perco_fight_total += 1
                    card_obj.perco_won_unpaid += 1
                    card_was_updated_this_fight = True
                else:
                    logger.warning(f"Winner '{player_primary_name}' but fight type (prism/perco) unknown. Stats not updated for this type.")

            elif is_loser:
                if self.prism:
                    card_obj.prisme_fight_loose += 1
                    card_obj.prisme_fight_total += 1
                    card_obj.prisme_loose_unpaid += 1
                    card_was_updated_this_fight = True
                elif self.perco:
                    card_obj.perco_fight_loose += 1
                    card_obj.perco_fight_total += 1
                    card_obj.perco_loose_unpaid += 1
                    card_was_updated_this_fight = True
                else:
                    logger.warning(f"Loser '{player_primary_name}' but fight type (prism/perco) unknown. Stats not updated for this type.")

            if card_was_updated_this_fight:
                card_obj.haschanged = True # Mark for payment tracking
                updated_id_cards_primary_names.append(player_primary_name)
                logger.debug(f"Updated stats for IdCard: {player_primary_name} (Matched via primary or alias)")

        if updated_id_cards_primary_names:
            logger.info(f"Finished saving stats. IdCards updated: {updated_id_cards_primary_names}")
        else:
            logger.info("Finished saving stats. No matching IdCards were updated for this fight result.")


    def to_embed(self, timestamp_str=None) -> discord.Embed:
        if self.wewon is True:
            embed_color = discord.Color.green()
            result_emoji = "✅"
            result_text = "Victoire !"
        elif self.wewon is False:
            embed_color = discord.Color.red()
            result_emoji = "❌"
            result_text = "Défaite..."
        else:
            embed_color = discord.Color.greyple()
            result_emoji = "❓"
            result_text = "Résultat Indéterminé / Non Concerné"

        if self.prism is True:
            target_emoji = "💎"
            target_text = "Prisme"
        elif self.perco is True:
            target_emoji = "💰"
            target_text = "Percepteur"
        else:
            target_emoji = "❔"
            target_text = "Cible Inconnue"

        embed_desc = f"**{result_text}** contre un(e) **{target_text}**."
        embed = discord.Embed(
            title=f"{result_emoji} Résultat Combat vs {target_text} {result_emoji}",
            description=embed_desc,
            color=embed_color
        )

        winner_list = "\n".join(f"👤 {name}" for name in self.winners) if self.winners else "*(Aucun)*"
        embed.add_field(name="🏆 Gagnants", value=winner_list, inline=True)
        loser_list = "\n".join(f"👤 {name}" for name in self.losers) if self.losers else "*(Aucun)*"
        embed.add_field(name="💀 Perdants", value=loser_list, inline=True)

        if self.time != -1:
             embed.add_field(name="⏱️ Durée", value=f"`{self.time} minutes`", inline=False) # Example, if time is parsed

        if timestamp_str:
            embed.set_footer(text=f"Message reçu à: {timestamp_str} | Hash: {self.hash()}")
        else:
            embed.set_footer(text=f"Hash: {self.hash()}")
        return embed

    def hash (self) -> str:
        """
        Generates a more stable hash based on the content of the EndScreen.
        Concatenates key attributes and hashes the resulting string.
        """
        if self.hash_code: # Return pre-computed hash if available
            return self.hash_code

        # Normalize and sort lists for consistent hashing
        sorted_winners = ",".join(sorted(list(set(self.winners))))
        sorted_losers = ",".join(sorted(list(set(self.losers))))

        # Create a string representation of the core data
        # Including wewon, prism, perco status is important for uniqueness
        data_string = (
            f"winners:{sorted_winners}|"
            f"losers:{sorted_losers}|"
            f"prism:{self.prism}|"
            f"perco:{self.perco}|"
            f"wewon:{self.wewon}"
            # Add other distinguishing features if parsed, e.g., fight duration
            # f"|time:{self.time}"
        )
        
        # Use SHA256 for a robust hash
        self.hash_code = hashlib.sha256(data_string.encode('utf-8')).hexdigest()
        return self.hash_code


    def parse (self, words, positions, raw_ocr_lines, known_names_with_aliases, vocabulary, std_factor=4):
        """
        Parse the OCR words and positions to extract fight details.
        'known_names_with_aliases' is the comprehensive list of primary IdCard names and all their aliases.
        """
        if not all([stage0, stage1, stage2, stage3]):
            logger.error("Parsing pipeline stages not loaded. Cannot parse.")
            self.winners, self.losers, self.wewon = [], [], None
            return

        logger.info(f"Starting EndScreen parsing. Using {len(known_names_with_aliases)} known names (incl. aliases).")

        self.prism = False
        self.perco = False
        found_prism_keyword = False
        if raw_ocr_lines:
            for text_line in raw_ocr_lines:
                if "prisme" in text_line.lower() or "prism" in text_line.lower():
                    found_prism_keyword = True
                    break
        if found_prism_keyword:
            self.prism = True
            logger.info("Detected Prism fight based on raw OCR.")
        else:
            self.perco = True # Default to perco
            logger.info("Defaulting to Percepteur fight (no prism keyword found).")

        if not words:
            logger.warning("Parse called with empty words list.")
            self.winners, self.losers, self.wewon = [], [], None
            self.hash_code = self.hash() # Generate hash even for empty result
            return

        logger.debug("Running Stage 0: Preprocessing")
        processed_words, processed_positions = stage0(words, positions)
        if not processed_words:
             logger.warning("No words remaining after Stage 0 preprocessing.")
             self.winners, self.losers, self.wewon = [], [], None
             self.hash_code = self.hash()
             return

        logger.debug("Running Stage 1: Word to Known")
        mapped_words, final_positions = stage1(processed_words, processed_positions, vocabulary, threshold=3)

        logger.debug("Running Stage 2: Classification (Relaxed)")
        # Pass known_names_with_aliases to stage2
        word_dict = stage2(mapped_words, final_positions, known_names_with_aliases, vocabulary, std_factor=std_factor)

        logger.debug("Running Stage 3: Winner/Loser Extraction")
        winners, losers = stage3(word_dict) # Ensure stage3 returns losers, not loosers

        # Determine if 'we' (any of known_names_with_aliases) won or lost
        known_names_set = set(known_names_with_aliases) # Use the comprehensive list
        winners_set = set(winners)
        losers_set = set(losers)

        we_are_winners = bool(winners_set & known_names_set)
        we_are_losers = bool(losers_set & known_names_set)

        if we_are_winners and not we_are_losers:
            self.wewon = True
        elif we_are_losers and not we_are_winners:
            self.wewon = False
        elif we_are_winners and we_are_losers:
            logger.error("Inconsistent state: Known names/aliases in both winners and losers!")
            self.wewon = None
        else:
            self.wewon = None # Not involved or ambiguous

        self.winners = sorted(list(winners_set))
        self.losers = sorted(list(losers_set))
        self.hash_code = self.hash() # Generate stable hash based on final content
        logger.info(f"Parsing complete. Hash: {self.hash_code}, WeWon: {self.wewon}")
        logger.debug(f"Final parsed: Winners={self.winners}, Losers={self.losers}, Prism={self.prism}, Perco={self.perco}")

    def _update_lists_and_sort(self):
        self.winners = sorted(list(set(self.winners)))
        self.losers = sorted(list(set(self.losers)))

    def add_winner(self, name: str):
        name = name.strip() # Clean input
        if name:
            if name in self.losers: self.losers.remove(name)
            if name not in self.winners: self.winners.append(name)
            self._update_lists_and_sort()
            self.hash_code = None # Invalidate old hash
            logger.info(f"Added '{name}' to winners.")
            return True
        return False

    def add_loser(self, name: str):
        name = name.strip()
        if name:
            if name in self.winners: self.winners.remove(name)
            if name not in self.losers: self.losers.append(name)
            self._update_lists_and_sort()
            self.hash_code = None # Invalidate old hash
            logger.info(f"Added '{name}' to losers.")
            return True
        return False

    def remove_player(self, name: str):
        name = name.strip()
        removed = False
        if name in self.winners:
            self.winners.remove(name)
            removed = True
        if name in self.losers:
            self.losers.remove(name)
            removed = True
        if removed:
            self._update_lists_and_sort()
            self.hash_code = None # Invalidate old hash
            logger.info(f"Removed '{name}' from results.")
        return removed

    def re_evaluate_wewon(self, known_names_with_aliases: list):
        """Updates self.wewon based on current winner/loser lists and the comprehensive known names list."""
        known_names_set = set(known_names_with_aliases)
        winners_set = set(self.winners)
        losers_set = set(self.losers)

        we_are_winners = bool(winners_set & known_names_set)
        we_are_losers = bool(losers_set & known_names_set)

        original_wewon = self.wewon
        if we_are_winners and not we_are_losers:
            self.wewon = True
        elif we_are_losers and not we_are_winners:
            self.wewon = False
        elif we_are_winners and we_are_losers:
            logger.warning("Inconsistent state during re_evaluate_wewon: Known names in both winners and losers!")
            self.wewon = None
        else:
            self.wewon = None

        if original_wewon != self.wewon:
            logger.info(f"Re-evaluated 'wewon' status: {original_wewon} -> {self.wewon}")
            self.hash_code = None # Invalidate hash as wewon status might change it