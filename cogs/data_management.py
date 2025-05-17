# cogs/data_management.py
import discord
from discord.ext import commands
import logging
import os

import id_card  # Uses modified id_card.py

from utils.helpers import clean_name, has_pay_role, create_id_card_embed

logger = logging.getLogger(__name__)

try:
    from utils.ui import PaginationView
except ImportError:
    logger.warning("PaginationView not found. Pagination features will be unavailable.")
    PaginationView = None

MAX_NAMES_TO_LIST = 15

try:
    PAY_ROLE_ID = int(os.getenv('PAY_COMMAND_ROLE_ID'))
    logger.info(f"PAY_COMMAND_ROLE_ID loaded: {PAY_ROLE_ID}")
except (TypeError, ValueError):
    logger.error("PAY_COMMAND_ROLE_ID not found or not a valid integer in .env file. Role-restricted commands might fail or be open.")
    PAY_ROLE_ID = 0 # Effectively makes has_pay_role() fail if role not found

class DataManagementCog(commands.Cog):
    """Cog for viewing and managing stored data (IDs, payments, users, aliases)."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, 'send_long_message'): # Fallback for send_long_message
            logger.error("Bot instance is missing 'send_long_message' helper method!")
            async def _send_long_message_fallback(channel, content):
                 if len(content) <= 2000: await channel.send(content)
                 else: await channel.send(content[:1990] + "...")
            bot.send_long_message = _send_long_message_fallback

        # Ensure core data attributes exist on the bot object
        if not hasattr(self.bot, 'ids_data'):
            logger.warning("Bot is missing 'ids_data' attribute, initializing as empty list for DataManagementCog.")
            self.bot.ids_data = [] # This should be loaded by main bot script ideally
        if not hasattr(self.bot, 'known_names'):
            logger.warning("Bot is missing 'known_names' attribute, initializing as empty list for DataManagementCog.")
            self.bot.known_names = [] # This should be loaded by main bot script ideally

    # --- Helper to find IdCard for a Discord Member ---
    def _find_id_card_for_member(self, member: discord.Member) -> id_card.IdCard | None:
        """Finds the IdCard associated with a Discord member based on their cleaned display name."""
        if not member: return None
        cleaned_member_display_name = clean_name(member.display_name)
        
        # Primary lookup: by cleaned display name (consistent with scrap/refresh)
        found_card = discord.utils.find(lambda card: card.name == cleaned_member_display_name, self.bot.ids_data)
        
        # Secondary lookup (fallback): by cleaned username if display name didn't match
        # This might be useful if an IdCard was created with member.name directly at some point.
        if not found_card:
            cleaned_member_username = clean_name(member.name)
            if cleaned_member_username != cleaned_member_display_name: # Avoid redundant search
                found_card = discord.utils.find(lambda card: card.name == cleaned_member_username, self.bot.ids_data)
        return found_card

    def _find_id_card_by_name_or_alias(self, name_or_alias: str) -> id_card.IdCard | None:
        """Finds an IdCard by its primary name or one of its in-game aliases."""
        cleaned_input = clean_name(name_or_alias)
        for card_obj in self.bot.ids_data:
            if card_obj.name == cleaned_input:
                return card_obj
            # Ensure ingame_aliases attribute exists and is iterable
            if hasattr(card_obj, 'ingame_aliases') and isinstance(card_obj.ingame_aliases, list):
                if cleaned_input in card_obj.ingame_aliases:
                    return card_obj
        return None

    def get_all_recognizable_names(self) -> list[str]:
        """Returns a list of all primary IdCard names and all their in-game aliases, all cleaned."""
        names = set()
        for card_obj in self.bot.ids_data:
            if card_obj.name: # card.name should already be cleaned
                names.add(card_obj.name)
            if hasattr(card_obj, 'ingame_aliases') and isinstance(card_obj.ingame_aliases, list):
                for alias in card_obj.ingame_aliases: # aliases should also be stored cleaned
                    if alias: names.add(alias)
        return list(names)

    @commands.command(name='names', help="Liste les noms connus (et alias) et leur statut de paiement.")
    async def names_command(self, ctx: commands.Context):
        logger.info(f"'!names' command invoked by {ctx.author}")
        ids_data = self.bot.ids_data
        if not ids_data:
            await ctx.send(embed=discord.Embed(description="ℹ️ Je n'ai aucune donnée de nom pour le moment.", color=discord.Color.blue()))
            return
        
        name_list = []
        sorted_ids_data = sorted(ids_data, key=lambda item: getattr(item, 'name', '').lower())
        
        for item in sorted_ids_data:
            try:
                status_emoji = "❌" if getattr(item, 'haschanged', True) else "✅"
                primary_name = getattr(item, 'name', '`Inconnu`')
                display_entry = f"{status_emoji} **{discord.utils.escape_markdown(primary_name)}**"
                
                aliases = getattr(item, 'ingame_aliases', [])
                if aliases:
                    alias_str = ", ".join(f"`{discord.utils.escape_markdown(a)}`" for a in aliases)
                    display_entry += f" (Alias: {alias_str})"
                name_list.append(display_entry)
            except Exception as e:
                 logger.warning(f"Error processing item in ids_data for !names: {item} - {e}")
                 name_list.append(f"⚠️ `Erreur: Donnée invalide pour un item.`")
        
        description = "\n".join(name_list)
        await self.bot.send_long_message(ctx.channel, f"📊 **Statut des Paiements**\n{description}")

    @commands.group(name='show', invoke_without_command=True, help="Affiche les données (utilise !show unpaid, !show all, !show name <nom_ou_alias>).")
    async def show_group(self, ctx: commands.Context):
        logger.info(f"'!show' command invoked by {ctx.author} without subcommand.")
        embed = discord.Embed(title="Commande `!show`", color=discord.Color.blurple())
        embed.add_field(name="`!show unpaid`", value="Affiche les entrées non payées.", inline=False)
        embed.add_field(name="`!show all`", value="Affiche toutes les entrées.", inline=False)
        embed.add_field(name="`!show name <nom_ou_alias>`", value="Affiche les détails pour un nom ou alias spécifique.", inline=False)
        await ctx.send(embed=embed)

    @show_group.command(name='unpaid', help="Affiche les entrées non payées.")
    async def show_unpaid(self, ctx: commands.Context):
        # ... (implementation mostly unchanged, ensure sorting)
        logger.info(f"'!show unpaid' command invoked by {ctx.author}")
        if PaginationView is None:
             await ctx.send("Erreur: La fonctionnalité de pagination n'est pas disponible.")
             return
        ids_data = self.bot.ids_data
        unpaid_items = [item for item in ids_data if getattr(item, 'haschanged', False)]
        if not unpaid_items:
            await ctx.send(embed=discord.Embed(description="🎉 Tu as déjà tout payé !", color=discord.Color.green()))
            return
        sorted_unpaid_items = sorted(unpaid_items, key=lambda item: getattr(item, 'name', '').lower())
        view = PaginationView(sorted_unpaid_items, create_id_card_embed, ctx.author.id)
        await view.start(ctx)

    @show_group.command(name='all', help="Affiche toutes les entrées (navigable).")
    async def show_all(self, ctx: commands.Context):
        # ... (implementation mostly unchanged, ensure sorting)
        logger.info(f"'!show all' command invoked by {ctx.author}")
        if PaginationView is None:
             await ctx.send("Erreur: La fonctionnalité de pagination n'est pas disponible.")
             return
        ids_data = self.bot.ids_data
        if not ids_data:
            await ctx.send(embed=discord.Embed(description="ℹ️ Je n'ai aucune donnée à afficher !", color=discord.Color.blue()))
            return
        sorted_ids_data = sorted(ids_data, key=lambda item: getattr(item, 'name', '').lower())
        view = PaginationView(sorted_ids_data, create_id_card_embed, ctx.author.id)
        await view.start(ctx)

    @show_group.command(name='name', help="Affiche les détails pour un nom ou alias spécifique.")
    async def show_name(self, ctx: commands.Context, *, target_name_or_alias: str):
        logger.info(f"'!show name {target_name_or_alias}' command invoked by {ctx.author}")
        found_item = self._find_id_card_by_name_or_alias(target_name_or_alias) # Uses new helper
        
        if found_item:
             # create_id_card_embed will use the IdCard.__str__ method which now includes aliases
             item_embed = create_id_card_embed(found_item, page_num=1, total_pages=1)
             await ctx.send(embed=item_embed)
        else:
             not_found_embed = discord.Embed(description=f"❓ Je ne trouve pas d'entrée pour le nom/alias : `{discord.utils.escape_markdown(target_name_or_alias)}`", color=discord.Color.red())
             await ctx.send(embed=not_found_embed)

    @commands.command(name='pay', help="Marque toutes les entrées comme payées (Rôle requis).")
    @has_pay_role()
    async def pay_command(self, ctx: commands.Context):
        # ... (implementation unchanged, id_card.save_card will handle new alias field)
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
                await ctx.send(embed=discord.Embed(description=f"⚠️ J'ai marqué {changed_count} élément(s) comme payé(s) en mémoire, mais une **erreur est survenue lors de la sauvegarde**.", color=discord.Color.orange()).add_field(name="Erreur", value=f"```{e}```"))
        elif something_was_unpaid: # This case means items were unpaid but couldn't be set to paid.
             await ctx.send(embed=discord.Embed(description="⚠️ Une erreur est survenue lors du traitement des paiements. Aucune donnée n'a été modifiée ou sauvegardée.", color=discord.Color.orange()))
        else:
            await ctx.send(embed=discord.Embed(description="✅ Tout était déjà marqué comme payé. Rien à faire.", color=discord.Color.green()))
    
    @pay_command.error
    async def pay_command_error(self, ctx: commands.Context, error): # Unchanged
        if isinstance(error, commands.CheckFailure):
            await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande." if PAY_ROLE_ID != 0 else "Désolé, la configuration du rôle pour cette commande est incorrecte.")
        elif isinstance(error, commands.CommandInvokeError): await ctx.send(f"Une erreur est survenue: ```{error.original}```")
        else: await ctx.send(f"Une erreur inattendue: ```{error}```")

    # --- !scrap, !refresh, !add, !remove primarily manage IdCards by their main 'name' (Discord display name) ---
    # They create IdCards with empty alias lists. Aliases are managed by !alias commands.

    @commands.command(name='scrap', aliases=['adduser', 'scan'], help="Ajoute les nouveaux utilisateurs du serveur (par nom d'affichage) à la liste des cartes d'ID (Rôle requis).")
    @has_pay_role()
    @commands.guild_only()
    async def scrap_users(self, ctx: commands.Context):
        # Logic remains to add IdCards based on *new* cleaned Discord display names.
        # New IdCards will have empty ingame_aliases.
        logger.info(f"'!scrap' command invoked by {ctx.author} in guild {ctx.guild.id}")
        msg = await ctx.send("🔄 Recherche de nouveaux utilisateurs (par nom d'affichage) sur le serveur...")

        current_server_cleaned_display_names = set()
        try:
            async for member in ctx.guild.fetch_members(limit=None):
                 if not member.bot:
                    name_cleaned = clean_name(member.display_name) # Key for IdCard
                    if name_cleaned:
                        current_server_cleaned_display_names.add(name_cleaned)
        except discord.Forbidden:
             logger.error(f"Bot lacks permissions (Members Intent?) to fetch members in guild {ctx.guild.id}.")
             await msg.edit(content="❌ Erreur : Le bot n'a pas les permissions pour lister les membres.")
             return
        except Exception as e:
            logger.exception(f"Failed to fetch/process server members for !scrap.")
            await msg.edit(content=f"❌ Erreur lors de la récupération des membres: ```{e}```")
            return
        
        existing_id_card_names = set(card.name for card in self.bot.ids_data)
        names_to_add_as_cards = sorted(list(current_server_cleaned_display_names - existing_id_card_names))

        if not names_to_add_as_cards:
            await msg.edit(content="✅ Aucun nouvel utilisateur (par nom d'affichage) trouvé pour ajouter une carte d'ID.")
            return

        for name in names_to_add_as_cards:
            self.bot.ids_data.append(id_card.IdCard(name)) # Creates card with empty aliases
        
        self.bot.ids_data.sort(key=lambda card: card.name.lower())
        # Sync self.bot.known_names with primary IdCard names
        self.bot.known_names = sorted([card.name for card in self.bot.ids_data])

        save_errors = []
        try: id_card.save_known_names(self.bot.known_names)
        except Exception as e: logger.exception("Failed to save known_names.txt"); save_errors.append("known_names.txt")
        try: id_card.save_card(self.bot.ids_data)
        except Exception as e: logger.exception("Failed to save cards.json"); save_errors.append("cards.json")

        # Report
        embed = discord.Embed(title="✅ Scan Utilisateurs (Noms d'Affichage) Terminé", color=discord.Color.green())
        embed.add_field(name="Nouvelles Cartes d'ID Créées", value=str(len(names_to_add_as_cards)), inline=True)
        embed.add_field(name="Total Cartes d'ID", value=str(len(self.bot.ids_data)), inline=True)
        # ... (rest of reporting logic for added names is similar)
        if 0 < len(names_to_add_as_cards) <= MAX_NAMES_TO_LIST:
             embed.add_field(name="Noms d'Affichage Ajoutés", value="\n".join(f"- `{name}`" for name in names_to_add_as_cards), inline=False)
        elif len(names_to_add_as_cards) > MAX_NAMES_TO_LIST:
             embed.add_field(name="Noms d'Affichage Ajoutés", value=f"({len(names_to_add_as_cards)} noms - trop long)", inline=False)
        if save_errors:
            embed.color = discord.Color.orange()
            embed.add_field(name="⚠️ Erreurs de Sauvegarde", value=f"Échec sauvegarde: {', '.join(save_errors)}", inline=False)
        await msg.edit(content=None, embed=embed)


    @commands.command(name='refresh', aliases=['syncusers'], help="Synchronise les cartes d'ID avec les noms d'affichage du serveur (Rôle requis).")
    @has_pay_role()
    @commands.guild_only()
    async def refresh_users(self, ctx: commands.Context):
        # Synchronizes IdCards based on current server member display names.
        # Adds new IdCards for new display names, removes IdCards for display names no longer on server.
        # Preserves aliases on existing cards.
        logger.info(f"'!refresh' command invoked by {ctx.author} in guild {ctx.guild.id}")
        msg = await ctx.send("🔄 Synchronisation des cartes d'ID avec les noms d'affichage du serveur...")

        current_server_cleaned_display_names = set()
        try:
            async for member in ctx.guild.fetch_members(limit=None):
                 if not member.bot:
                    name_cleaned = clean_name(member.display_name)
                    if name_cleaned:
                        current_server_cleaned_display_names.add(name_cleaned)
        # ... (error handling as in !scrap) ...
        except discord.Forbidden:
             logger.error(f"Bot lacks permissions (Members Intent?) to fetch members in guild {ctx.guild.id}.")
             await msg.edit(content="❌ Erreur : Le bot n'a pas les permissions pour lister les membres.")
             return
        except Exception as e:
            logger.exception(f"Failed to fetch/process server members for !refresh.")
            await msg.edit(content=f"❌ Erreur lors de la récupération des membres: ```{e}```")
            return

        existing_id_card_map = {card.name: card for card in self.bot.ids_data}
        
        names_to_add_as_cards = sorted(list(current_server_cleaned_display_names - set(existing_id_card_map.keys())))
        names_to_remove_cards_for = sorted(list(set(existing_id_card_map.keys()) - current_server_cleaned_display_names))

        new_ids_data = []
        # Keep existing cards if their primary name is still on the server
        for name_on_server in current_server_cleaned_display_names:
            if name_on_server in existing_id_card_map:
                new_ids_data.append(existing_id_card_map[name_on_server]) # Keep existing card with its aliases
            else: # This case is covered by names_to_add_as_cards
                pass 
        
        # Add new cards
        for name_to_add in names_to_add_as_cards:
            new_ids_data.append(id_card.IdCard(name_to_add)) # New card, empty aliases

        self.bot.ids_data = sorted(new_ids_data, key=lambda card: card.name.lower())
        self.bot.known_names = sorted([card.name for card in self.bot.ids_data]) # Sync known_names

        save_errors = []
        try: id_card.save_known_names(self.bot.known_names)
        except Exception as e: logger.exception("Failed to save known_names.txt"); save_errors.append("known_names.txt")
        try: id_card.save_card(self.bot.ids_data)
        except Exception as e: logger.exception("Failed to save cards.json"); save_errors.append("cards.json")

        # Report
        embed = discord.Embed(title="✅ Synchro Cartes d'ID (Noms d'Affichage) Terminée", color=discord.Color.green())
        embed.add_field(name="Cartes Ajoutées", value=str(len(names_to_add_as_cards)), inline=True)
        embed.add_field(name="Cartes Supprimées", value=str(len(names_to_remove_cards_for)), inline=True)
        # ... (reporting for added/removed names as in !scrap, but using names_to_add_as_cards and names_to_remove_cards_for)
        if 0 < len(names_to_add_as_cards) <= MAX_NAMES_TO_LIST:
             embed.add_field(name="Noms d'Affichage Ajoutés (Nouvelles Cartes)", value="\n".join(f"- `{name}`" for name in names_to_add_as_cards), inline=False)
        # ... similar for removed
        if save_errors:
            embed.color = discord.Color.orange()
            embed.add_field(name="⚠️ Erreurs de Sauvegarde", value=f"Échec sauvegarde: {', '.join(save_errors)}", inline=False)
        await msg.edit(content=None, embed=embed)

    @commands.command(name='add', help="Ajoute manuellement une carte d'ID pour un nom principal (Rôle requis).")
    @has_pay_role()
    async def add_user(self, ctx: commands.Context, *, user_name: str):
        # Adds an IdCard with 'user_name' as its primary IdCard.name. Aliases are empty.
        logger.info(f"'!add {user_name}' command invoked by {ctx.author}")
        name_cleaned = clean_name(user_name)
        if not name_cleaned:
            await ctx.send(f"❌ Nom invalide: `{user_name}`.")
            return

        if discord.utils.find(lambda card: card.name == name_cleaned, self.bot.ids_data):
            await ctx.send(f"ℹ️ Une carte d'ID pour `{name_cleaned}` existe déjà.")
            return
        try:
            new_card = id_card.IdCard(name_cleaned) # Empty aliases
            self.bot.ids_data.append(new_card)
            self.bot.ids_data.sort(key=lambda card: card.name.lower())
            if name_cleaned not in self.bot.known_names: # Sync known_names
                self.bot.known_names.append(name_cleaned)
                self.bot.known_names.sort()
                id_card.save_known_names(self.bot.known_names)
            id_card.save_card(self.bot.ids_data)
            await ctx.send(f"✅ Carte d'ID pour `{name_cleaned}` ajoutée.")
        except Exception as e:
            logger.exception(f"Failed to manually add IdCard for '{name_cleaned}'.")
            await ctx.send(f"❌ Erreur ajout carte pour `{name_cleaned}`: ```{e}```")

    @add_user.error
    async def add_user_error(self, ctx: commands.Context, error): # Unchanged
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Usage: `!add <nom_principal_pour_carte>`")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("Désolé, tu n'as pas le rôle requis." if PAY_ROLE_ID !=0 else "Config rôle incorrecte.")
        else:
            await ctx.send(f"Erreur: ```{error}```")

    @commands.command(name='remove', aliases=['deluser', 'delete'], help="Supprime manuellement une carte d'ID par son nom principal (Rôle requis).")
    @has_pay_role()
    async def remove_user(self, ctx: commands.Context, *, user_name: str):
        # Removes an IdCard based on its primary IdCard.name.
        logger.info(f"'!remove {user_name}' command invoked by {ctx.author}")
        name_cleaned = clean_name(user_name)
        if not name_cleaned:
            await ctx.send(f"❌ Nom invalide: `{user_name}`.")
            return

        card_to_remove = discord.utils.find(lambda card: card.name == name_cleaned, self.bot.ids_data)
        if not card_to_remove:
            await ctx.send(f"ℹ️ Carte d'ID pour `{name_cleaned}` non trouvée.")
            return
        try:
            self.bot.ids_data.remove(card_to_remove)
            if name_cleaned in self.bot.known_names: # Sync known_names
                 self.bot.known_names.remove(name_cleaned)
                 id_card.save_known_names(self.bot.known_names)
            id_card.save_card(self.bot.ids_data)
            await ctx.send(f"✅ Carte d'ID pour `{name_cleaned}` supprimée.")
        except Exception as e:
            logger.exception(f"Failed to manually remove IdCard for '{name_cleaned}'.")
            await ctx.send(f"❌ Erreur suppression carte pour `{name_cleaned}`: ```{e}```")

    @remove_user.error
    async def remove_user_error(self, ctx: commands.Context, error): # Unchanged
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Usage: `!remove <nom_principal_de_carte>`")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("Désolé, tu n'as pas le rôle requis." if PAY_ROLE_ID !=0 else "Config rôle incorrecte.")
        else:
            await ctx.send(f"Erreur: ```{error}```")


    # --- NEW ALIAS MANAGEMENT COMMANDS ---
    @commands.group(name='alias', invoke_without_command=True, help="Gère les alias en jeu pour les utilisateurs Discord.")
    @has_pay_role()
    async def alias_group(self, ctx: commands.Context):
        embed = discord.Embed(title="Gestion des Alias en Jeu", color=discord.Color.teal())
        base_cmd = f"{ctx.prefix}alias"
        embed.add_field(name=f"`{base_cmd} add <@utilisateur_discord> <alias_en_jeu>`", value="Ajoute un alias à un utilisateur.", inline=False)
        embed.add_field(name=f"`{base_cmd} remove <@utilisateur_discord> <alias_en_jeu>`", value="Supprime un alias.", inline=False)
        embed.add_field(name=f"`{base_cmd} list <@utilisateur_discord>`", value="Liste les alias d'un utilisateur.", inline=False)
        embed.set_footer(text="L'<@utilisateur_discord> peut être une mention, un ID, ou nom#discrim.")
        await ctx.send(embed=embed)

    @alias_group.command(name='add', help="Ajoute un alias en jeu à un utilisateur Discord.")
    @has_pay_role()
    async def alias_add(self, ctx: commands.Context, member: discord.Member, *, ingame_alias: str):
        logger.info(f"'!alias add' for {member} with alias '{ingame_alias}' by {ctx.author}")
        card = self._find_id_card_for_member(member)
        if not card:
            await ctx.send(f"❌ L'utilisateur `{member.display_name}` n'a pas de carte d'ID. Créez-en une avec `{ctx.prefix}add {clean_name(member.display_name)}` ou via `{ctx.prefix}scrap`/`{ctx.prefix}refresh`.")
            return

        cleaned_alias = clean_name(ingame_alias)
        if not cleaned_alias:
            await ctx.send("❌ Nom d'alias invalide après nettoyage.")
            return

        if cleaned_alias == card.name:
            await ctx.send(f"ℹ️ L'alias `{cleaned_alias}` est identique au nom principal de la carte.")
            return
        
        # Check for global uniqueness of the alias (not primary name of another card, not alias of another card)
        for other_card in self.bot.ids_data:
            if other_card.name == cleaned_alias: # Alias is a primary name of another card
                await ctx.send(f"⚠️ L'alias `{cleaned_alias}` est déjà le nom principal de la carte de `{other_card.name}`. Choisissez un autre alias.")
                return
            if hasattr(other_card, 'ingame_aliases') and cleaned_alias in other_card.ingame_aliases and other_card.name != card.name:
                 await ctx.send(f"⚠️ L'alias `{cleaned_alias}` est déjà utilisé par la carte de `{other_card.name}`. Les alias doivent être uniques.")
                 return

        if cleaned_alias in card.ingame_aliases:
            await ctx.send(f"ℹ️ L'alias `{cleaned_alias}` existe déjà pour `{card.name}`.")
            return
        try:
            card.ingame_aliases.append(cleaned_alias)
            card.ingame_aliases.sort()
            id_card.save_card(self.bot.ids_data)
            logger.info(f"Alias '{cleaned_alias}' added to '{card.name}' ({member.display_name}).")
            await ctx.send(f"✅ Alias `{cleaned_alias}` ajouté à `{card.name}` (pour `{member.display_name}`).")
        except Exception as e:
            logger.exception(f"Failed to add alias '{cleaned_alias}' to '{card.name}'.")
            if cleaned_alias in card.ingame_aliases: card.ingame_aliases.remove(cleaned_alias) # Attempt revert
            await ctx.send(f"❌ Erreur ajout alias: ```{e}```")

    @alias_group.command(name='remove', help="Supprime un alias en jeu d'un utilisateur Discord.")
    @has_pay_role()
    async def alias_remove(self, ctx: commands.Context, member: discord.Member, *, ingame_alias: str):
        logger.info(f"'!alias remove' for {member} alias '{ingame_alias}' by {ctx.author}")
        card = self._find_id_card_for_member(member)
        if not card:
            await ctx.send(f"❌ L'utilisateur `{member.display_name}` n'a pas de carte d'ID.")
            return

        cleaned_alias = clean_name(ingame_alias)
        if not cleaned_alias:
            await ctx.send("❌ Nom d'alias invalide.")
            return

        if cleaned_alias not in card.ingame_aliases:
            await ctx.send(f"ℹ️ L'alias `{cleaned_alias}` n'est pas trouvé pour `{card.name}`.")
            return
        try:
            card.ingame_aliases.remove(cleaned_alias)
            id_card.save_card(self.bot.ids_data)
            logger.info(f"Alias '{cleaned_alias}' removed from '{card.name}' ({member.display_name}).")
            await ctx.send(f"✅ Alias `{cleaned_alias}` supprimé de `{card.name}` (pour `{member.display_name}`).")
        except Exception as e:
            logger.exception(f"Failed to remove alias '{cleaned_alias}'.")
            await ctx.send(f"❌ Erreur suppression alias: ```{e}```")

    @alias_group.command(name='list', help="Liste les alias en jeu d'un utilisateur Discord.")
    @has_pay_role() # Or remove role check if listing is fine
    async def alias_list(self, ctx: commands.Context, member: discord.Member):
        logger.info(f"'!alias list' for {member} by {ctx.author}")
        card = self._find_id_card_for_member(member)
        if not card:
            await ctx.send(f"❌ L'utilisateur `{member.display_name}` n'a pas de carte d'ID.")
            return

        embed = discord.Embed(title=f"Alias pour {member.display_name} (Carte: `{card.name}`)", color=discord.Color.blue())
        if card.ingame_aliases:
            embed.description = "\n".join(f"- `{alias}`" for alias in sorted(card.ingame_aliases))
        else:
            embed.description = "Aucun alias en jeu n'est défini pour cet utilisateur."
        await ctx.send(embed=embed)

    @alias_add.error
    @alias_remove.error
    @alias_list.error
    async def alias_commands_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Argument manquant. Usage: `{ctx.prefix}help {ctx.command.full_parent_name}`")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"❌ Membre Discord non trouvé: `{error.argument}`.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("Désolé, tu n'as pas le rôle requis." if PAY_ROLE_ID !=0 else "Config rôle incorrecte.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Argument invalide. Pour `@utilisateur_discord`, essayez une mention, un ID, ou nom#tag.")
        else:
            logger.error(f"Unexpected error in alias command '{ctx.command.name}': {error}")
            await ctx.send(f"Erreur inattendue: ```{error}```")
            
    @scrap_users.error
    @refresh_users.error
    async def scrap_refresh_error(self, ctx: commands.Context, error): # Combined error handler
        if isinstance(error, commands.CheckFailure):
            await ctx.send("Désolé, tu n'as pas le rôle requis." if PAY_ROLE_ID !=0 else "Config rôle incorrecte.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("Cette commande doit être utilisée sur un serveur.")
        elif isinstance(error, commands.CommandInvokeError):
            logger.exception(f"Error executing {ctx.command.name}: {error.original}")
            await ctx.send(f"Une erreur est survenue: ```{error.original}```")
        else:
            logger.error(f"Unexpected error in {ctx.command.name}: {error}")
            await ctx.send(f"Erreur inattendue: ```{error}```")


async def setup(bot: commands.Bot):
    try: import emoji; logger.info("Emoji library found (optional for clean_name).")
    except ImportError: logger.info("Emoji library not found (optional for clean_name).")

    if not bot.intents.members:
        logger.critical("CRITICAL: 'Members' intent IS REQUIRED for !scrap, !refresh, and alias commands, but is NOT ENABLED!")
    if not bot.intents.guilds:
        logger.warning("Warning: 'Guilds' intent is recommended for guild context.")

    await bot.add_cog(DataManagementCog(bot))
    logger.info("DataManagementCog loaded with alias management.")