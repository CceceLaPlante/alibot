# cogs/screen.py
import discord
from discord.ext import commands
import logging
import asyncio

logger = logging.getLogger(__name__)

# Assuming id_card.py is in the parent directory or accessible for save functions
try:
    import sys
    import os
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.append(parent_dir)
    import id_card
    logger.info("Successfully imported id_card for saving.")
except ImportError as e:
    logger.critical(f"CRITICAL: Failed to import id_card module from {parent_dir}: {e}. Saving will fail.")
    id_card = None

# Import screen processing modules
try:
    from screen.traitement import from_link_to_result
    from screen.EndScreen import EndScreen
except ImportError as e:
     logger.critical(f"CRITICAL: Failed to import screen processing modules: {e}. Screen command will fail.")
     from_link_to_result = None
     EndScreen = None

logger = logging.getLogger(__name__)

class ScreenCog(commands.Cog):
    """Cog for processing screen attachments and modifying results."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending_results: dict[int, EndScreen] = {}
        self.user_locks: dict[int, asyncio.Lock] = {}

        # Check if required attributes exist on the bot object upon initialization
        required_attrs = ['known_names', 'hashes', 'ids_data']
        missing_attrs = [attr for attr in required_attrs if not hasattr(self.bot, attr)]
        if missing_attrs:
            logger.error(f"ScreenCog initialized, but bot object is missing attributes: {missing_attrs}. Ensure they are loaded in main bot script.")
            # Depending on severity, you might prevent the cog from loading fully

    async def get_user_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]

    @commands.command(name='screen', aliases=['process'], help="Traite une image attachée. Ne sauvegarde pas avant '!confirm'.")
    async def screen_command(self, ctx: commands.Context):
        if from_link_to_result is None or EndScreen is None:
             await ctx.send(embed=discord.Embed(description="❌ Le module de traitement d'image n'est pas chargé.", color=discord.Color.red()))
             return
        if not hasattr(self.bot, 'known_names'):
             await ctx.send(embed=discord.Embed(description="❌ Erreur: La liste `known_names` n'a pas été chargée dans le bot.", color=discord.Color.red()))
             logger.error("Bot object missing 'known_names' attribute in screen_command.")
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

            # --- Get known_names from the bot instance ---
            known_names = self.bot.known_names
            # hashes and ids_data are only needed for !confirm
            # ---

            aggregated_screen_result = None
            processed_count = 0
            error_count = 0

            attachments_to_process = [a for a in ctx.message.attachments if a.content_type and a.content_type.startswith('image/')]
            if not attachments_to_process:
                 await ctx.send(embed=discord.Embed(description="❌ Aucun fichier image valide trouvé.", color=discord.Color.orange()))
                 return

            async with ctx.typing():
                # --- (Attachment processing loop remains the same as previous version) ---
                try:
                    logger.info(f"Processing {len(attachments_to_process)} attachments for {ctx.author}...")
                    current_result = None
                    for i, attachment in enumerate(attachments_to_process):
                        logger.info(f"Processing attachment {i+1}/{len(attachments_to_process)}: {attachment.filename}")
                        try:
                            # Pass known_names from bot instance
                            screen_part_result = from_link_to_result(attachment.url, known_names)
                            processed_count += 1
                            if current_result is None:
                                current_result = screen_part_result
                            else:
                                try:
                                    current_result.concat(screen_part_result)
                                    logger.info(f"Successfully concatenated results from {attachment.filename}")
                                except ValueError as e:
                                    error_count += 1
                                    logger.error(f"Error concatenating results from {attachment.filename}: {e}")
                                    await ctx.send(embed=discord.Embed(title="⚠️ Erreur de Fusion", description=f"Impossible de fusionner `{attachment.filename}`: `{e}`. Traitement arrêté.", color=discord.Color.orange()))
                                    return # Stop processing
                        except Exception as e:
                            error_count += 1
                            logger.exception(f"Error processing attachment {attachment.filename}: {e}")
                            await ctx.send(embed=discord.Embed(title=f"❌ Erreur Traitement: {attachment.filename}", description=f"```{type(e).__name__}: {e}```", color=discord.Color.dark_red()))
                            return # Stop processing
                    aggregated_screen_result = current_result
                except Exception as e:
                    error_count += 1
                    logger.exception(f"Critical error during screen processing for {ctx.author}: {e}")
                    await ctx.send(embed=discord.Embed(title="❌ Erreur Critique", description=f"Erreur majeure: ```{type(e).__name__}: {e}```", color=discord.Color.dark_red()))
                    return
                # --- (End attachment processing loop) ---

            # --- Send Result and Store Pending ---
            if aggregated_screen_result and error_count == 0:
                timestamp_str = ctx.message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                result_embed = aggregated_screen_result.to_embed(timestamp_str=timestamp_str)
                result_embed.title = "🔎 Résultat Détecté (Non Confirmé)"
                result_embed.description = (f"{result_embed.description}\n\n"
                                           f"Modifiez avec `{ctx.prefix}addwinner <nom>`, `{ctx.prefix}addloser <nom>`, `{ctx.prefix}removeplayer <nom>`.\n"
                                           f"Confirmez avec `{ctx.prefix}confirm` pour sauvegarder.")
                result_embed.color = discord.Color.blue()

                self.pending_results[ctx.author.id] = aggregated_screen_result
                logger.info(f"Stored pending result for user {ctx.author.id}. Hash (pre-confirm): {aggregated_screen_result.hash()}")
                await ctx.send(embed=result_embed)

            elif error_count > 0:
                await ctx.send(embed=discord.Embed(description=f"⚠️ Traitement terminé avec {error_count} erreur(s). Aucun résultat en attente.", color=discord.Color.orange()))
            else:
                 await ctx.send(embed=discord.Embed(description="❓ Aucune donnée n'a pu être extraite des images.", color=discord.Color.light_grey()))

        # End of user lock block

    async def _handle_modification(self, ctx: commands.Context, action: str, name: str):
        """Helper function to handle add/remove operations."""
        if not hasattr(self.bot, 'known_names'):
             await ctx.send(embed=discord.Embed(description="❌ Erreur: La liste `known_names` n'a pas été chargée dans le bot.", color=discord.Color.red()))
             logger.error("Bot object missing 'known_names' attribute in _handle_modification.")
             return

        user_lock = await self.get_user_lock(ctx.author.id)
        async with user_lock:
            if ctx.author.id not in self.pending_results:
                await ctx.send(embed=discord.Embed(description=f"❌ Pas de résultat en attente. Utilisez `{ctx.prefix}screen`.", color=discord.Color.orange()))
                return

            screen_result = self.pending_results[ctx.author.id]
            modified = False

            # Perform action
            if action == "add_winner": modified = screen_result.add_winner(name)
            elif action == "add_loser": modified = screen_result.add_loser(name)
            elif action == "remove": modified = screen_result.remove_player(name)

            if modified:
                # --- Get known_names from bot instance for re-evaluation ---
                known_names = self.bot.known_names
                screen_result.re_evaluate_wewon(known_names)
                # ---

                self.pending_results[ctx.author.id] = screen_result # Update stored result

                result_embed = screen_result.to_embed()
                result_embed.title = "🔄 Résultat Modifié (Non Confirmé)"
                result_embed.description = (f"{result_embed.description}\n\n"
                                           f"Confirmez avec `{ctx.prefix}confirm`.")
                result_embed.color = discord.Color.blue()
                await ctx.send(embed=result_embed)
                logger.info(f"User {ctx.author.id} performed '{action}' on name '{name}'. New hash (pre-confirm): {screen_result.hash()}")
            else:
                # Send appropriate message if nothing changed
                if action == "remove":
                     await ctx.send(embed=discord.Embed(description=f"❓ Joueur `{name}` non trouvé.", color=discord.Color.light_grey()))
                else:
                     await ctx.send(embed=discord.Embed(description=f"❓ Action '{action}' pour `{name}` n'a rien changé.", color=discord.Color.light_grey()))

    @commands.command(name='addwinner', aliases=['aw'], help="Ajoute un joueur aux gagnants (avant !confirm).")
    async def add_winner_command(self, ctx: commands.Context, *, name: str):
        logger.info(f"'!addwinner' command invoked by {ctx.author} for name '{name}'")
        await self._handle_modification(ctx, "add_winner", name.strip())

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

    @commands.command(name='addloser', aliases=['al'], help="Ajoute un joueur aux perdants (avant !confirm).")
    async def add_loser_command(self, ctx: commands.Context, *, name: str):
        logger.info(f"'!addloser' command invoked by {ctx.author} for name '{name}'")
        await self._handle_modification(ctx, "add_loser", name.strip())

    @commands.command(name='removeplayer', aliases=['rp'], help="Retire un joueur des listes (avant !confirm).")
    async def remove_player_command(self, ctx: commands.Context, *, name: str):
        logger.info(f"'!removeplayer' command invoked by {ctx.author} for name '{name}'")
        await self._handle_modification(ctx, "remove", name.strip())

    @commands.command(name='confirm', help="Confirme et sauvegarde le dernier résultat traité.")
    async def confirm_command(self, ctx: commands.Context):
        logger.info(f"'!confirm' command invoked by {ctx.author}")

        # --- Check required bot attributes for saving ---
        if not all(hasattr(self.bot, attr) for attr in ['hashes', 'ids_data']):
            await ctx.send(embed=discord.Embed(description="❌ Erreur: Les données (`hashes`, `ids_data`) n'ont pas été chargées dans le bot.", color=discord.Color.red()))
            logger.error("Bot object missing 'hashes' or 'ids_data' attribute in confirm_command.")
            return
        if id_card is None:
            await ctx.send(embed=discord.Embed(description="❌ Erreur critique: Le module `id_card` n'a pas pu être chargé pour la sauvegarde.", color=discord.Color.red()))
            return
        # ---

        user_lock = await self.get_user_lock(ctx.author.id)
        async with user_lock:
            if ctx.author.id not in self.pending_results:
                await ctx.send(embed=discord.Embed(description=f"❌ Pas de résultat en attente. Utilisez `{ctx.prefix}screen`.", color=discord.Color.orange()))
                return

            screen_result = self.pending_results[ctx.author.id]
            final_hash = screen_result.hash()

            # --- Get data from bot instance ---
            hashes = self.bot.hashes # This is the list stored on the bot
            ids_data = self.bot.ids_data # This is the data structure stored on the bot
            # ---

            if final_hash in hashes:
                await ctx.send(embed=discord.Embed(description="🤔 Ce résultat a déjà été sauvegardé.", color=discord.Color.blue()))
                logger.info(f"Duplicate hash found on confirm: {final_hash}. Submitted by {ctx.author}.")
                del self.pending_results[ctx.author.id] # Clear pending result
            else:
                try:
                    # 1. Update the bot's in-memory data structure (ids_data)
                    screen_result.save(ids_data) # Assumes this modifies ids_data in-place or returns the modified version if needed

                    # 2. Update the bot's in-memory hash list
                    hashes.append(final_hash) # Modify the list held by the bot

                    # 3. Save the updated structures to files using id_card functions
                    #    Pass the lists/data held by the bot instance
                    id_card.save_saved_hash(self.bot.hashes)
                    id_card.save_card(self.bot.ids_data)

                    logger.info(f"Confirmed and saved result for {ctx.author.id}. Hash: {final_hash}.")

                    # Send final confirmation embed
                    final_embed = screen_result.to_embed()
                    final_embed.title = "✅ Résultat Confirmé et Sauvegardé"
                    final_embed.color = discord.Color.green()
                    final_embed.description = f"{final_embed.description}\n\nStats mises à jour."
                    await ctx.send(embed=final_embed)

                    # 4. Clear the pending result AFTER successful save
                    del self.pending_results[ctx.author.id]

                except AttributeError as e:
                     # Specifically catch if save functions don't exist in id_card
                     logger.exception(f"Failed to save confirmed data - id_card module might be missing save functions: {e}")
                     await ctx.send(embed=discord.Embed(description=f"❌ Erreur de sauvegarde: La fonction nécessaire (`{e.name}`) manque dans `id_card.py`.", color=discord.Color.red()))
                     # Important: Revert in-memory changes if save fails?
                     # For simplicity, we don't revert here, but a robust solution might.
                     if final_hash in self.bot.hashes: # Remove hash if added prematurely
                        self.bot.hashes.remove(final_hash)
                     # We don't easily revert the changes made by screen_result.save(ids_data)

                except Exception as e:
                    logger.exception(f"Failed to save confirmed data (hash: {final_hash}): {e}")
                    await ctx.send(embed=discord.Embed(description=f"❌ Erreur lors de la sauvegarde: ```{e}```", color=discord.Color.red()))
                    # Revert hash addition
                    if final_hash in self.bot.hashes:
                         self.bot.hashes.remove(final_hash)
                    # Clear pending result even on error? Or let user retry confirm? Let's clear for now.
                    if ctx.author.id in self.pending_results:
                        del self.pending_results[ctx.author.id]


async def setup(bot: commands.Bot):
    # Check dependencies before adding cog
    if id_card is not None and from_link_to_result is not None and EndScreen is not None:
        # Check if bot has required attributes loaded BEFORE adding the cog
        if all(hasattr(bot, attr) for attr in ['known_names', 'hashes', 'ids_data']):
            await bot.add_cog(ScreenCog(bot))
            logger.info("ScreenCog loaded.")
        else:
            logger.error("ScreenCog NOT loaded because bot object is missing required data attributes (known_names, hashes, ids_data). Load them in your main script.")
    else:
        logger.error("ScreenCog NOT loaded due to missing dependencies (id_card or screen processing modules).")