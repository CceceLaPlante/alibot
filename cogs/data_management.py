# cogs/data_management.py
import discord
from discord.ext import commands
import logging
import os

import id_card 

from utils.helpers import clean_name, has_pay_role, create_id_card_embed 

logger = logging.getLogger(__name__)

# Assuming PaginationView is in utils.ui or similar
try:
    from utils.ui import PaginationView
except ImportError:
    logger.warning("PaginationView not found. Pagination features will be unavailable.")
    PaginationView = None # Define as None if not found


# --- Constants ---
MAX_NAMES_TO_LIST = 15 # Max names to show directly in add/remove reports


# --- Role ID and Check Function ---
try:
    PAY_ROLE_ID = int(os.getenv('PAY_COMMAND_ROLE_ID'))
    if PAY_ROLE_ID is None:
         logger.error("PAY_COMMAND_ROLE_ID not found in .env file. Commands requiring it will fail.")
         PAY_ROLE_ID = 0
    else:
        logger.info(f"PAY_COMMAND_ROLE_ID loaded: {PAY_ROLE_ID}")
except (TypeError, ValueError):
    logger.error("PAY_COMMAND_ROLE_ID in .env file is not a valid integer. Commands requiring it will fail.")
    PAY_ROLE_ID = 0


# --- Cog Definition ---
class DataManagementCog(commands.Cog):
    """Cog for viewing and managing stored data (IDs, payments, users)."""
    def __init__(self, bot: commands.Bot):
        # Ensure bot has the send_long_message helper or add it here/in utils
        if not hasattr(bot, 'send_long_message'):
            logger.error("Bot instance is missing 'send_long_message' helper method!")
            # Add a fallback or raise error
            async def _send_long_message_fallback(channel, content):
                 if len(content) <= 2000: await channel.send(content)
                 else: await channel.send(content[:1990] + "...") # Basic fallback
            bot.send_long_message = _send_long_message_fallback
        self.bot = bot

    @commands.command(name='names', help="Liste les noms connus et leur statut de paiement.")
    async def names_command(self, ctx: commands.Context):
        # ... (implementation unchanged) ...
        logger.info(f"'!names' command invoked by {ctx.author}")
        ids_data = self.bot.ids_data
        if not ids_data:
            await ctx.send(embed=discord.Embed(description="ℹ️ Je n'ai aucune donnée de nom pour le moment. Essayez `!add`, `!scrap` ou `!refresh`.", color=discord.Color.blue()))
            return
        name_list = []
        sorted_ids_data = sorted(ids_data, key=lambda item: getattr(item, 'name', '').lower())
        for ids_item in sorted_ids_data:
            try:
                status_emoji = "❌" if getattr(ids_item, 'haschanged', True) else "✅"
                name = getattr(ids_item, 'name', '`Inconnu`')
                name_list.append(f"{status_emoji} **{discord.utils.escape_markdown(name)}**")
            except Exception as e:
                 logger.warning(f"Error processing item in ids_data for !names: {ids_item} - {e}")
                 name_list.append(f"⚠️ `Erreur: Donnée invalide pour un item.`")
        # Use the bot's helper for sending potentially long lists
        description = "\n".join(name_list)
        await self.bot.send_long_message(ctx.channel, f"📊 **Statut des Paiements**\n{description}")


    @commands.group(name='show', invoke_without_command=True, help="Affiche les données (utilise !show unpaid, !show all, !show name <nom>).")
    async def show_group(self, ctx: commands.Context):
         # ... (implementation unchanged) ...
        logger.info(f"'!show' command invoked by {ctx.author} without subcommand.")
        embed = discord.Embed(title="Commande `!show`", color=discord.Color.blurple())
        embed.add_field(name="`!show unpaid`", value="Affiche les entrées non payées.", inline=False)
        embed.add_field(name="`!show all`", value="Affiche toutes les entrées.", inline=False)
        embed.add_field(name="`!show name <nom>`", value="Affiche les détails pour un nom spécifique.", inline=False)
        await ctx.send(embed=embed)

    @show_group.command(name='unpaid', help="Affiche les entrées non payées.")
    async def show_unpaid(self, ctx: commands.Context):
        # ... (implementation unchanged) ...
        logger.info(f"'!show unpaid' command invoked by {ctx.author}")
        if PaginationView is None:
             await ctx.send("Erreur: La fonctionnalité de pagination n'est pas disponible.")
             return
        ids_data = self.bot.ids_data
        unpaid_items = [ids for ids in ids_data if getattr(ids, 'haschanged', False)]
        if not unpaid_items:
            await ctx.send(embed=discord.Embed(description="🎉 Tu as déjà tout payé !", color=discord.Color.green()))
            return
        view = PaginationView(unpaid_items, create_id_card_embed, ctx.author.id)
        await view.start(ctx)


    @show_group.command(name='all', help="Affiche toutes les entrées (navigable).")
    async def show_all(self, ctx: commands.Context):
        # ... (implementation unchanged) ...
        logger.info(f"'!show all' command invoked by {ctx.author}")
        if PaginationView is None:
             await ctx.send("Erreur: La fonctionnalité de pagination n'est pas disponible.")
             return
        ids_data = self.bot.ids_data
        if not ids_data:
            await ctx.send(embed=discord.Embed(description="ℹ️ Je n'ai aucune donnée à afficher ! Essayez `!add`, `!scrap` ou `!refresh`.", color=discord.Color.blue()))
            return
        view = PaginationView(ids_data, create_id_card_embed, ctx.author.id)
        await view.start(ctx)

    @show_group.command(name='name', help="Affiche les détails pour un nom spécifique.")
    async def show_name(self, ctx: commands.Context, *, target_name: str):
         # ... (implementation unchanged, uses clean_name implicitly via stored data) ...
        logger.info(f"'!show name {target_name}' command invoked by {ctx.author}")
        ids_data = self.bot.ids_data
        target_name_cleaned = clean_name(target_name)
        if not target_name_cleaned:
            await ctx.send("❓ Nom invalide fourni.")
            return
        found_item = discord.utils.find(lambda item: getattr(item, 'name', '').lower() == target_name_cleaned, ids_data)
        if found_item:
             item_embed = create_id_card_embed(found_item, page_num=1, total_pages=1)
             await ctx.send(embed=item_embed)
        else:
             not_found_embed = discord.Embed(description=f"❓ Je ne trouve pas d'entrée pour le nom : `{discord.utils.escape_markdown(target_name)}`", color=discord.Color.red())
             await ctx.send(embed=not_found_embed)

    @commands.command(name='pay', help="Marque toutes les entrées comme payées (Rôle requis).")
    @has_pay_role()
    async def pay_command(self, ctx: commands.Context):
         # ... (implementation unchanged) ...
        logger.info(f"'!pay' command invoked by {ctx.author}")
        ids_data = self.bot.ids_data
        changed_count = 0
        something_was_unpaid = False
        for item in ids_data:
            try:
                if getattr(item, 'haschanged', False):
                    something_was_unpaid = True
                    item.haschanged = False
                    changed_count += 1
            except Exception as e:
                logger.error(f"Error processing item {getattr(item, 'name', 'N/A')} during !pay: {e}")
        if changed_count > 0:
            try:
                id_card.save_card(ids_data)
                logger.info(f"{changed_count} items marked as paid by {ctx.author}. Data saved.")
                await ctx.send(embed=discord.Embed(description=f"✅ OK, j'ai marqué {changed_count} élément(s) comme payé(s) !", color=discord.Color.green()))
            except Exception as e:
                logger.exception("Failed to save data after !pay command.")
                await ctx.send(embed=discord.Embed(description=f"⚠️ J'ai marqué {changed_count} élément(s) comme payé(s) en mémoire, mais une **erreur est survenue lors de la sauvegarde** des données.", color=discord.Color.orange()).add_field(name="Erreur", value=f"```{e}```"))
        elif something_was_unpaid:
             await ctx.send(embed=discord.Embed(description="⚠️ Une erreur est survenue lors du traitement des paiements. Aucune donnée n'a été sauvegardée.", color=discord.Color.orange()))
        else:
            await ctx.send(embed=discord.Embed(description="✅ Tout était déjà marqué comme payé. Rien à faire.", color=discord.Color.green()))

    @pay_command.error
    async def pay_command_error(self, ctx: commands.Context, error):
        # ... (implementation unchanged) ...
        if isinstance(error, commands.CheckFailure):
            if PAY_ROLE_ID == 0: await ctx.send("Désolé, la configuration du rôle pour cette commande est incorrecte.")
            else: await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande.")
        elif isinstance(error, commands.CommandInvokeError): await ctx.send(f"Une erreur est survenue: ```{error.original}```")
        else: await ctx.send(f"Une erreur inattendue: ```{error}```")

    # --- Modified scrap/refresh Commands (Show names in report) ---
    @commands.command(name='scrap', aliases=['adduser', 'scan'], help="Ajoute les nouveaux utilisateurs du serveur à la liste connue (Rôle requis).")
    @has_pay_role()
    @commands.guild_only()
    async def scrap_users(self, ctx: commands.Context):
        """Fetches server members and adds NEW members (cleaned names) to data."""
        logger.info(f"'!scrap' command invoked by {ctx.author} in guild {ctx.guild.id}")
        msg = await ctx.send("🔄 Recherche de nouveaux utilisateurs sur le serveur...")

        # 1. Get current members and CLEAN names
        current_server_names = set()
        try:
            # Using fetch_members for potentially more up-to-date list
            async for member in ctx.guild.fetch_members(limit=None):
                 if not member.bot:
                    name_cleaned = clean_name(member.display_name)
                    if name_cleaned:
                        current_server_names.add(name_cleaned)
            logger.info(f"Fetched and cleaned {len(current_server_names)} non-bot member names for !scrap.")
        except discord.Forbidden:
             logger.error(f"Bot lacks permissions (Members Intent?) to fetch members in guild {ctx.guild.id}.")
             await msg.edit(content="❌ Erreur : Le bot n'a pas les permissions nécessaires pour lister les membres.")
             return
        except Exception as e:
            logger.exception(f"Failed to fetch/process server members for !scrap in guild {ctx.guild.id}.")
            await msg.edit(content=f"❌ Erreur lors de la récupération/traitement des membres: ```{e}```")
            return

        # 2. Get current known data
        original_known_names_set = set(self.bot.known_names)
        original_cards_map = {card.name.lower(): card for card in self.bot.ids_data}

        # 3. Find only the names that are new
        added_names = sorted(list(current_server_names - original_known_names_set)) # Sort for display
        logger.info(f"{len(added_names)} new users found to add (after cleaning names).")

        if not added_names:
            await msg.edit(content="✅ Aucun nouvel utilisateur trouvé. La liste est à jour.")
            return

        # 4. Prepare updated data (Additive)
        new_known_names_list = sorted(list(original_known_names_set.union(added_names)))
        new_cards_data_list = list(self.bot.ids_data)
        for name in added_names:
            if name not in original_cards_map:
                logger.debug(f"Creating new IdCard for added user: {name}")
                new_cards_data_list.append(id_card.IdCard(name))

        # 5. Update bot's state
        self.bot.known_names = new_known_names_list
        self.bot.ids_data = new_cards_data_list

        # 6. Save updated data to files
        save_errors = []
        try: id_card.save_known_names(self.bot.known_names)
        except Exception as e: logger.exception("Failed to save known_names.txt"); save_errors.append("known_names.txt")
        try: id_card.save_card(self.bot.ids_data)
        except Exception as e: logger.exception("Failed to save cards.json"); save_errors.append("cards.json")

        # 7. Report results (Show added names)
        embed = discord.Embed(title="✅ Scan Utilisateurs Terminé", color=discord.Color.green())
        embed.add_field(name="Nouveaux Noms Ajoutés", value=str(len(added_names)), inline=True)
        embed.add_field(name="Total Noms Connus", value=str(len(self.bot.known_names)), inline=True)

        # List added names if count is reasonable
        if 0 < len(added_names) <= MAX_NAMES_TO_LIST:
             added_names_str = "\n".join(f"- `{name}`" for name in added_names)
             embed.add_field(name="Noms Ajoutés", value=added_names_str, inline=False)
        elif len(added_names) > MAX_NAMES_TO_LIST:
             embed.add_field(name="Noms Ajoutés", value=f"({len(added_names)} noms - trop long pour afficher)", inline=False)
             # Optionally send the full list separately if needed using send_list_embed or bot.send_long_message

        if save_errors:
            embed.color = discord.Color.orange()
            embed.add_field(name="⚠️ Erreurs de Sauvegarde", value=f"Échec sauvegarde: {', '.join(save_errors)}", inline=False)
            embed.description = "Données en mémoire à jour, mais sauvegarde échouée."
        else:
            embed.description = f"{len(added_names)} utilisateur(s) ajouté(s) à la liste."

        await msg.edit(content=None, embed=embed) # Edit the original message


    @commands.command(name='refresh', aliases=['syncusers'], help="Synchronise la liste d'utilisateurs avec le serveur (ajoute/supprime) (Rôle requis).")
    @has_pay_role()
    @commands.guild_only()
    async def refresh_users(self, ctx: commands.Context):
        """Fetches server members, updates data to match server (adds/removes, cleans names)."""
        logger.info(f"'!refresh' command invoked by {ctx.author} in guild {ctx.guild.id}")
        msg = await ctx.send("🔄 Synchronisation complète de la liste des utilisateurs en cours...")

        # 1. Get current members and CLEAN names
        current_server_names = set()
        try:
            # Using fetch_members for potentially more up-to-date list
            async for member in ctx.guild.fetch_members(limit=None):
                 if not member.bot:
                    name_cleaned = clean_name(member.display_name)
                    if name_cleaned:
                        current_server_names.add(name_cleaned)
            logger.info(f"Fetched and cleaned {len(current_server_names)} non-bot member names for !refresh.")
        except discord.Forbidden:
             logger.error(f"Bot lacks permissions (Members Intent?) to fetch members in guild {ctx.guild.id}.")
             await msg.edit(content="❌ Erreur : Le bot n'a pas les permissions nécessaires pour lister les membres.")
             return
        except Exception as e:
            logger.exception(f"Failed to fetch/process server members for !refresh in guild {ctx.guild.id}.")
            await msg.edit(content=f"❌ Erreur lors de la récupération/traitement des membres: ```{e}```")
            return

        # 2. Get current known data
        original_known_names_set = set(name.lower() for name in self.bot.known_names)
        original_cards_map = {card.name.lower(): card for card in self.bot.ids_data}

        # 3. Determine changes
        added_names = sorted(list(current_server_names - original_known_names_set)) # Sort for display
        removed_names = sorted(list(original_known_names_set - current_server_names)) # Sort for display
        logger.info(f"Refresh: Users to add: {len(added_names)}. Users to remove: {len(removed_names)} (after cleaning).")

        # 4. Prepare new data lists (Exact Sync using cleaned names)
        new_known_names_list = sorted(list(current_server_names))
        new_cards_data_list = []
        for name in new_known_names_list:
            if name in original_cards_map: new_cards_data_list.append(original_cards_map[name])
            else: new_cards_data_list.append(id_card.IdCard(name))

        # 5. Update bot's state
        self.bot.known_names = new_known_names_list
        self.bot.ids_data = new_cards_data_list

        # 6. Save updated data to files
        save_errors = []
        try: id_card.save_known_names(self.bot.known_names)
        except Exception as e: logger.exception("Failed to save known_names.txt"); save_errors.append("known_names.txt")
        try: id_card.save_card(self.bot.ids_data)
        except Exception as e: logger.exception("Failed to save cards.json"); save_errors.append("cards.json")

        # 7. Report results (Show added and removed names)
        embed = discord.Embed(title="✅ Synchronisation Utilisateurs Terminée", color=discord.Color.green())
        embed.description = "La liste des utilisateurs a été mise à jour pour correspondre au serveur."
        embed.add_field(name="Membres Actuels Trouvés", value=str(len(current_server_names)), inline=True)
        embed.add_field(name="Noms Ajoutés", value=str(len(added_names)), inline=True)
        embed.add_field(name="Noms Supprimés", value=str(len(removed_names)), inline=True)

        # List added names
        if 0 < len(added_names) <= MAX_NAMES_TO_LIST:
            embed.add_field(name="Noms Ajoutés", value="\n".join(f"- `{name}`" for name in added_names), inline=False)
        elif len(added_names) > MAX_NAMES_TO_LIST:
            embed.add_field(name="Noms Ajoutés", value=f"({len(added_names)} noms - trop long pour afficher)", inline=False)

        # List removed names
        if 0 < len(removed_names) <= MAX_NAMES_TO_LIST:
            embed.add_field(name="Noms Supprimés", value="\n".join(f"- `{name}`" for name in removed_names), inline=False)
        elif len(removed_names) > MAX_NAMES_TO_LIST:
             embed.add_field(name="Noms Supprimés", value=f"({len(removed_names)} noms - trop long pour afficher)", inline=False)

        if save_errors:
            embed.color = discord.Color.orange()
            embed.add_field(name="⚠️ Erreurs de Sauvegarde", value=f"Échec sauvegarde: {', '.join(save_errors)}", inline=False)
            embed.description = "Données en mémoire à jour, mais sauvegarde échouée."

        await msg.edit(content=None, embed=embed) # Edit the original message


    # --- NEW: Manual Add/Remove Commands ---

    @commands.command(name='add', help="Ajoute manuellement un utilisateur (Rôle requis).")
    @has_pay_role()
    async def add_user(self, ctx: commands.Context, *, user_name: str):
        """Manually adds a user with default stats."""
        logger.info(f"'!add {user_name}' command invoked by {ctx.author}")

        name_cleaned = clean_name(user_name)
        if not name_cleaned:
            await ctx.send(f"❌ Nom invalide fourni après nettoyage : `{user_name}`.")
            return

        # Check if already exists
        # Use a set for efficient lookup of known names
        known_names_set = set(self.bot.known_names)
        if name_cleaned in known_names_set:
            await ctx.send(f"ℹ️ L'utilisateur `{name_cleaned}` est déjà dans la liste.")
            return

        # Add the user
        try:
            # Update lists in memory
            self.bot.known_names.append(name_cleaned)
            self.bot.known_names.sort() # Keep it sorted
            new_card = id_card.IdCard(name_cleaned) # Creates default card
            self.bot.ids_data.append(new_card)
            # Optionally sort ids_data by name too
            self.bot.ids_data.sort(key=lambda card: card.name)

            # Save changes
            id_card.save_known_names(self.bot.known_names)
            id_card.save_card(self.bot.ids_data)

            logger.info(f"User '{name_cleaned}' added manually by {ctx.author}.")
            await ctx.send(f"✅ Utilisateur `{name_cleaned}` ajouté avec succès.")

        except Exception as e:
            logger.exception(f"Failed to manually add user '{name_cleaned}'.")
            # Attempt to revert changes in memory if save failed? Might be complex.
            await ctx.send(f"❌ Une erreur est survenue lors de l'ajout de `{name_cleaned}`: ```{e}```")

    @add_user.error
    async def add_user_error(self, ctx: commands.Context, error):
        """Error handler for the add_user command."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Veuillez spécifier le nom de l'utilisateur à ajouter. Usage: `!add <nom>`")
        elif isinstance(error, commands.CheckFailure):
             await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande.")
        else:
            await ctx.send(f"Une erreur inattendue est survenue: ```{error}```")
            logger.error(f"Unexpected error in !add command: {error}")


    @commands.command(name='remove', aliases=['deluser', 'delete'], help="Supprime manuellement un utilisateur (Rôle requis).")
    @has_pay_role()
    async def remove_user(self, ctx: commands.Context, *, user_name: str):
        """Manually removes a user and their data."""
        logger.info(f"'!remove {user_name}' command invoked by {ctx.author}")

        name_cleaned = clean_name(user_name)
        if not name_cleaned:
            await ctx.send(f"❌ Nom invalide fourni après nettoyage : `{user_name}`.")
            return

        # Check if exists
        known_names_set = set(self.bot.known_names)
        if name_cleaned not in known_names_set:
            await ctx.send(f"ℹ️ L'utilisateur `{name_cleaned}` n'a pas été trouvé dans la liste.")
            return

        # Remove the user
        try:
            # Update lists in memory
            if name_cleaned in self.bot.known_names: # Double check before removal
                 self.bot.known_names.remove(name_cleaned)

            # Find and remove the card object
            card_to_remove = discord.utils.find(lambda card: card.name == name_cleaned, self.bot.ids_data)
            if card_to_remove:
                 self.bot.ids_data.remove(card_to_remove)
            else:
                 # This indicates an inconsistency between known_names and ids_data
                 logger.warning(f"User '{name_cleaned}' was in known_names but corresponding card not found in ids_data during removal.")
                 # Proceed with removing from known_names anyway? Yes.

            # Save changes
            id_card.save_known_names(self.bot.known_names)
            id_card.save_card(self.bot.ids_data)

            logger.info(f"User '{name_cleaned}' removed manually by {ctx.author}.")
            await ctx.send(f"✅ Utilisateur `{name_cleaned}` supprimé avec succès.")

        except ValueError: # Should not happen with the 'in' check, but safety
             logger.warning(f"ValueError during manual removal of '{name_cleaned}', likely already removed.")
             await ctx.send(f"ℹ️ L'utilisateur `{name_cleaned}` n'a pas été trouvé (ou déjà supprimé).")
        except Exception as e:
            logger.exception(f"Failed to manually remove user '{name_cleaned}'.")
            await ctx.send(f"❌ Une erreur est survenue lors de la suppression de `{name_cleaned}`: ```{e}```")

    @remove_user.error
    async def remove_user_error(self, ctx: commands.Context, error):
        """Error handler for the remove_user command."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Veuillez spécifier le nom de l'utilisateur à supprimer. Usage: `!remove <nom>`")
        elif isinstance(error, commands.CheckFailure):
             await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande.")
        else:
            await ctx.send(f"Une erreur inattendue est survenue: ```{error}```")
            logger.error(f"Unexpected error in !remove command: {error}")


    # --- scrap_users error handler ---
    @scrap_users.error
    async def scrap_users_error(self, ctx: commands.Context, error):
        # ... (implementation unchanged) ...
        if isinstance(error, commands.CheckFailure):
            if PAY_ROLE_ID == 0: await ctx.send("Désolé, la configuration du rôle pour cette commande est incorrecte.")
            elif isinstance(error, commands.NoPrivateMessage): await ctx.send("Cette commande ne peut être utilisée qu'à l'intérieur d'un serveur.")
            else: await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande.")
        elif isinstance(error, commands.CommandInvokeError): logger.exception(f"Error executing !scrap command logic: {error.original}"); await ctx.send(f"Une erreur est survenue: ```{error.original}```")
        elif isinstance(error, commands.GuildNotFound): logger.error(f"!scrap command failed: Guild not found"); await ctx.send("Erreur : Serveur non trouvé.")
        else: await ctx.send(f"Une erreur inattendue: ```{error}```"); logger.error(f"Unexpected error in !scrap command: {error}")

    # --- refresh_users error handler ---
    @refresh_users.error
    async def refresh_users_error(self, ctx: commands.Context, error):
         # ... (implementation unchanged) ...
        if isinstance(error, commands.CheckFailure):
            if PAY_ROLE_ID == 0: await ctx.send("Désolé, la configuration du rôle pour cette commande est incorrecte.")
            elif isinstance(error, commands.NoPrivateMessage): await ctx.send("Cette commande ne peut être utilisée qu'à l'intérieur d'un serveur.")
            else: await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande.")
        elif isinstance(error, commands.CommandInvokeError): logger.exception(f"Error executing !refresh command logic: {error.original}"); await ctx.send(f"Une erreur est survenue: ```{error.original}```")
        elif isinstance(error, commands.GuildNotFound): logger.error(f"!refresh command failed: Guild not found"); await ctx.send("Erreur : Serveur non trouvé.")
        else: await ctx.send(f"Une erreur inattendue: ```{error}```"); logger.error(f"Unexpected error in !refresh command: {error}")


# --- Async Setup Function ---
async def setup(bot: commands.Bot):
    # ... (setup function remains the same, including emoji lib check and intent check) ...
    try: import emoji; logger.info("Emoji library found.")
    except ImportError: logger.critical("CRITICAL: The 'emoji' library is not installed (pip install emoji). Emoji removal will fail!")
    if not bot.intents.members: logger.critical("CRITICAL: 'Members' intent is required for !scrap, !refresh but is not enabled!")
    elif not bot.intents.guilds: logger.warning("Warning: 'Guilds' intent is recommended.")

    await bot.add_cog(DataManagementCog(bot))
    logger.info("DataManagementCog loaded.")