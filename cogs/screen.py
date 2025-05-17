# cogs/screen.py
import discord
from discord.ext import commands
import logging
import asyncio

logger = logging.getLogger(__name__)

try:
    import id_card # Assumes id_card.py is accessible
    logger.info("ScreenCog: Successfully imported id_card.")
except ImportError as e:
    logger.critical(f"ScreenCog: CRITICAL - Failed to import id_card module: {e}. Saving will fail.")
    id_card = None

try:
    from screen.traitement import from_link_to_result
    from screen.EndScreen import EndScreen # Assuming EndScreen is your class
except ImportError as e:
     logger.critical(f"ScreenCog: CRITICAL - Failed to import screen processing modules (traitement or EndScreen): {e}. Screen command will fail.")
     from_link_to_result = None
     EndScreen = None


class ScreenCog(commands.Cog):
    """Cog for processing screen attachments and modifying results, using aliases."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending_results: dict[int, EndScreen] = {} # Make sure EndScreen is defined or imported
        self.user_locks: dict[int, asyncio.Lock] = {}

        # Ensure core data attributes used by confirm exist on the bot object
        # These should ideally be loaded in the main bot script before cogs.
        if not hasattr(self.bot, 'ids_data'):
            logger.error("ScreenCog: Bot is missing 'ids_data' attribute. Confirm may fail or use empty list.")
            # self.bot.ids_data = [] # Avoid modifying bot state directly here if main script handles it
        if not hasattr(self.bot, 'hashes'):
            logger.error("ScreenCog: Bot is missing 'hashes' attribute. Confirm may misbehave or use empty list.")
            # self.bot.hashes = []

    async def get_user_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]

    def _get_effective_known_names_for_screen_processing(self) -> list[str]:
        """
        Gets all primary names and all aliases from DataManagementCog for screen processing.
        Falls back to an empty list if DataManagementCog or its method is not available.
        """
        data_management_cog = self.bot.get_cog('DataManagementCog')
        if data_management_cog and hasattr(data_management_cog, 'get_all_recognizable_names'):
            names = data_management_cog.get_all_recognizable_names()
            logger.debug(f"ScreenCog: Using {len(names)} recognizable names (primary + aliases) from DataManagementCog.")
            return names
        else:
            logger.warning("ScreenCog: DataManagementCog or get_all_recognizable_names not found. Screen processing might be less effective. Falling back to empty list for known names.")
            # Fallback to self.bot.known_names if it exists and DataManagementCog doesn't
            # This provides a degraded mode if DataManagementCog isn't loaded but old known_names exist
            if hasattr(self.bot, 'known_names'):
                logger.warning("ScreenCog: Falling back to self.bot.known_names.")
                return self.bot.known_names
            return []

    @commands.command(name='screen', aliases=['process'], help="Traite une image attachée. Utilise les alias. Ne sauvegarde pas avant '!confirm'.")
    async def screen_command(self, ctx: commands.Context):
        if from_link_to_result is None or EndScreen is None:
             await ctx.send(embed=discord.Embed(description="❌ Le module de traitement d'image n'est pas chargé.", color=discord.Color.red()))
             return
        
        logger.info(f"'!screen' command invoked by {ctx.author} in channel {ctx.channel.id}")

        if not ctx.message.attachments:
            await ctx.send(embed=discord.Embed(description="❌ Pas d'image attachée.", color=discord.Color.orange()))
            return

        user_lock = await self.get_user_lock(ctx.author.id)
        async with user_lock:
            if ctx.author.id in self.pending_results:
                await ctx.send(embed=discord.Embed(description=f"⚠️ Vous avez déjà un résultat en attente (`{ctx.prefix}confirm`).", color=discord.Color.orange()))
                return

            # --- Get effective known names (primary + aliases) ---
            effective_names_for_ocr = self._get_effective_known_names_for_screen_processing()
            if not effective_names_for_ocr:
                logger.info("ScreenCog: No recognizable names available for OCR processing. Results may be limited.")
            # ---

            # ... (rest of the attachment processing loop remains the same, but passes effective_names_for_ocr)
            aggregated_screen_result = None
            # ... (same logic as before) ...
            async with ctx.typing():
                # (Attachment processing loop from your original code)
                # Key change is inside the loop:
                # screen_part_result = from_link_to_result(attachment.url, effective_names_for_ocr) # Pass comprehensive list
                # ... (rest of loop)
                try:
                    logger.info(f"Processing {len(ctx.message.attachments)} attachments for {ctx.author} using {len(effective_names_for_ocr)} recognizable names.")
                    current_result = None
                    processed_count = 0
                    error_count = 0
                    attachments_to_process = [a for a in ctx.message.attachments if a.content_type and a.content_type.startswith('image/')]

                    if not attachments_to_process:
                        await ctx.send(embed=discord.Embed(description="❌ Aucun fichier image valide trouvé.", color=discord.Color.orange()))
                        return

                    for i, attachment in enumerate(attachments_to_process):
                        logger.info(f"Processing attachment {i+1}/{len(attachments_to_process)}: {attachment.filename}")
                        try:
                            screen_part_result = from_link_to_result(attachment.url, effective_names_for_ocr) # USE THE NEW LIST
                            processed_count += 1
                            if current_result is None:
                                current_result = screen_part_result
                            else:
                                current_result.concat(screen_part_result) # Assuming EndScreen.concat exists
                        except ValueError as e: # Example: EndScreen.concat fails
                            error_count +=1
                            logger.error(f"Error concatenating results from {attachment.filename}: {e}")
                            await ctx.send(embed=discord.Embed(title="⚠️ Erreur de Fusion", description=f"Impossible de fusionner `{attachment.filename}`: `{e}`.", color=discord.Color.orange()))
                            # Decide if to stop all processing or just skip this attachment
                        except Exception as e:
                            error_count += 1
                            logger.exception(f"Error processing attachment {attachment.filename}: {e}")
                            await ctx.send(embed=discord.Embed(title=f"❌ Erreur Traitement: {attachment.filename}", description=f"```{type(e).__name__}: {e}```", color=discord.Color.dark_red()))
                            # Decide if to stop all processing
                    aggregated_screen_result = current_result
                except Exception as e:
                    error_count +=1 # Should be caught by inner try-except, this is a fallback
                    logger.exception(f"Critical error during screen processing loop for {ctx.author}: {e}")
                    await ctx.send(embed=discord.Embed(title="❌ Erreur Critique de Boucle", description=f"Erreur majeure: ```{type(e).__name__}: {e}```", color=discord.Color.dark_red()))
                    return # Stop processing

            # --- Send Result and Store Pending (same as before) ---
            if aggregated_screen_result and error_count == 0 :
                # ... (same logic)
                timestamp_str = ctx.message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                result_embed = aggregated_screen_result.to_embed(timestamp_str=timestamp_str) # Assuming EndScreen.to_embed
                result_embed.title = "🔎 Résultat Détecté (Non Confirmé)"
                result_embed.description = (f"{result_embed.description or ''}\n\n"
                                           f"Modifiez avec `{ctx.prefix}addwinner <nom>`, etc.\n"
                                           f"Confirmez avec `{ctx.prefix}confirm`.")
                result_embed.color = discord.Color.blue()
                self.pending_results[ctx.author.id] = aggregated_screen_result
                logger.info(f"Stored pending result for user {ctx.author.id}. Hash: {aggregated_screen_result.hash()}")
                await ctx.send(embed=result_embed)
            # ... (error/no data messages)
            elif error_count > 0:
                await ctx.send(embed=discord.Embed(description=f"⚠️ Traitement terminé avec {error_count} erreur(s). Aucun résultat en attente.", color=discord.Color.orange()))
            else: # No result and no errors usually means no data extracted
                 await ctx.send(embed=discord.Embed(description="❓ Aucune donnée n'a pu être extraite des images.", color=discord.Color.light_grey()))


    async def _handle_modification(self, ctx: commands.Context, action: str, name: str):
        # ... (user lock logic) ...
        user_lock = await self.get_user_lock(ctx.author.id)
        async with user_lock:
            if ctx.author.id not in self.pending_results:
                await ctx.send(embed=discord.Embed(description=f"❌ Pas de résultat en attente. Utilisez `{ctx.prefix}screen`.", color=discord.Color.orange()))
                return

            screen_result = self.pending_results[ctx.author.id] # This is an EndScreen object
            modified = False
            # Name is passed as is, EndScreen methods should handle matching
            if action == "add_winner": modified = screen_result.add_winner(name.strip())
            elif action == "add_loser": modified = screen_result.add_loser(name.strip())
            elif action == "remove": modified = screen_result.remove_player(name.strip())

            if modified:
                # --- Get effective known names for re-evaluation ---
                effective_names = self._get_effective_known_names_for_screen_processing()
                screen_result.re_evaluate_wewon(effective_names) # Pass all recognizable names
                # ---
                self.pending_results[ctx.author.id] = screen_result # Update stored result
                # ... (send embed, same logic)
                result_embed = screen_result.to_embed()
                result_embed.title = "🔄 Résultat Modifié (Non Confirmé)"
                result_embed.description = (f"{result_embed.description or ''}\n\n"
                                           f"Confirmez avec `{ctx.prefix}confirm`.")
                result_embed.color = discord.Color.blue()
                await ctx.send(embed=result_embed)
                logger.info(f"User {ctx.author.id} performed '{action}' on name '{name.strip()}'. New hash: {screen_result.hash()}")

            else:
                # ... (no change message, same logic)
                 await ctx.send(embed=discord.Embed(description=f"❓ Action '{action}' pour `{name.strip()}` n'a rien changé.", color=discord.Color.light_grey()))


    # addwinner, addloser, removeplayer, cancel commands are unchanged in their call to _handle_modification

    @commands.command(name='addwinner', aliases=['aw'], help="Ajoute un joueur aux gagnants (avant !confirm).")
    async def add_winner_command(self, ctx: commands.Context, *, name: str):
        logger.info(f"'!addwinner' invoked by {ctx.author} for name '{name}'")
        await self._handle_modification(ctx, "add_winner", name)

    @commands.command(name='addloser', aliases=['al'], help="Ajoute un joueur aux perdants (avant !confirm).")
    async def add_loser_command(self, ctx: commands.Context, *, name: str):
        logger.info(f"'!addloser' invoked by {ctx.author} for name '{name}'")
        await self._handle_modification(ctx, "add_loser", name)

    @commands.command(name='removeplayer', aliases=['rp'], help="Retire un joueur des listes (avant !confirm).")
    async def remove_player_command(self, ctx: commands.Context, *, name: str):
        logger.info(f"'!removeplayer' invoked by {ctx.author} for name '{name}'")
        await self._handle_modification(ctx, "remove", name)
        
    @commands.command(name='cancel', aliases=['c'], help="Annule le dernier résultat traité.")
    async def cancel_command(self, ctx: commands.Context):
        logger.info(f"'!cancel' command invoked by {ctx.author}")
        user_lock = await self.get_user_lock(ctx.author.id)
        async with user_lock:
            if ctx.author.id in self.pending_results:
                del self.pending_results[ctx.author.id]
                await ctx.send(embed=discord.Embed(description="✅ Résultat annulé.", color=discord.Color.green()))
            else:
                await ctx.send(embed=discord.Embed(description="❌ Pas de résultat en attente.", color=discord.Color.orange()))


    @commands.command(name='confirm', help="Confirme et sauvegarde le dernier résultat traité.")
    async def confirm_command(self, ctx: commands.Context):
        logger.info(f"'!confirm' command invoked by {ctx.author}")
        # --- Prerequisite checks ---
        if not hasattr(self.bot, 'ids_data') or not hasattr(self.bot, 'hashes'):
            await ctx.send(embed=discord.Embed(description="❌ Erreur: Les listes de données (`ids_data`, `hashes`) ne sont pas chargées dans le bot.", color=discord.Color.red()))
            logger.error("Bot object missing 'ids_data' or 'hashes' attribute in confirm_command.")
            return
        if id_card is None:
            await ctx.send(embed=discord.Embed(description="❌ Erreur critique: Le module `id_card` n'est pas chargé pour la sauvegarde.", color=discord.Color.red()))
            return
        # ---

        user_lock = await self.get_user_lock(ctx.author.id)
        async with user_lock:
            if ctx.author.id not in self.pending_results:
                await ctx.send(embed=discord.Embed(description=f"❌ Pas de résultat en attente. Utilisez `{ctx.prefix}screen`.", color=discord.Color.orange()))
                return

            screen_result = self.pending_results[ctx.author.id] # This is an EndScreen object
            final_hash = screen_result.hash()

            if final_hash in self.bot.hashes:
                await ctx.send(embed=discord.Embed(description="🤔 Ce résultat a déjà été sauvegardé.", color=discord.Color.blue()))
                del self.pending_results[ctx.author.id] # Clear pending if duplicate
                return

            try:
                # CRUCIAL: screen_result.save() MUST be able to find IdCards in self.bot.ids_data
                # by checking both IdCard.name AND IdCard.ingame_aliases against its detected names.
                # This logic is internal to your EndScreen.save() method.
                screen_result.save(self.bot.ids_data) # Modifies IdCard objects in the list

                self.bot.hashes.append(final_hash)

                id_card.save_saved_hash(self.bot.hashes)
                id_card.save_card(self.bot.ids_data) # Persists the modified IdCard objects

                logger.info(f"Confirmed and saved result for {ctx.author.id}. Hash: {final_hash}.")
                # ... (send final embed, same logic)
                final_embed = screen_result.to_embed()
                final_embed.title = "✅ Résultat Confirmé et Sauvegardé"
                final_embed.color = discord.Color.green()
                final_embed.description = f"{final_embed.description or ''}\n\nStats mises à jour."
                await ctx.send(embed=final_embed)

                del self.pending_results[ctx.author.id] # Clear after successful save

            # ... (error handling for save, same as before)
            except AttributeError as e:
                 logger.exception(f"Failed to save confirmed data - id_card or EndScreen module might be missing methods: {e}")
                 await ctx.send(embed=discord.Embed(description=f"❌ Erreur de sauvegarde: La fonction/attribut nécessaire (`{e.name}`) manque.", color=discord.Color.red()))
                 if final_hash in self.bot.hashes: self.bot.hashes.remove(final_hash) # Revert hash if added
            except Exception as e:
                logger.exception(f"Failed to save confirmed data (hash: {final_hash}): {e}")
                await ctx.send(embed=discord.Embed(description=f"❌ Erreur lors de la sauvegarde: ```{e}```", color=discord.Color.red()))
                if final_hash in self.bot.hashes: self.bot.hashes.remove(final_hash) # Revert hash


async def setup(bot: commands.Bot):
    if id_card is not None and from_link_to_result is not None and EndScreen is not None:
        # Ensure required bot attributes are present before adding cog.
        # Ideally, main bot script loads data (ids_data, hashes) before loading cogs.
        if not hasattr(bot, 'ids_data'):
            logger.error("ScreenCog setup: bot.ids_data not found. Cog might not function correctly.")
        if not hasattr(bot, 'hashes'):
            logger.error("ScreenCog setup: bot.hashes not found. Cog might not function correctly.")
            
        await bot.add_cog(ScreenCog(bot))
        logger.info("ScreenCog loaded, will use aliases via DataManagementCog if available.")
    else:
        logger.error("ScreenCog NOT loaded due to missing dependencies (id_card, screen.traitement, or screen.EndScreen).")