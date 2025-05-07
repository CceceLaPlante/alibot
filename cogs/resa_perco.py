# cogs/resa_perco.py
import discord
from discord.ext import commands
import logging
import os
import emoji
import perco 

from utils.helpers import clean_name

logger = logging.getLogger(__name__)

# Constants
MAX_TABLEAU_WIDTH = 1950 # Max chars for tableau in one message (leave room for ```) - Adjust if needed
MAX_NAME_DISPLAY_LEN = 12 # Max length for names in the tableau display
MAX_NAMES_TO_LIST = 15 # Max names to show directly in add/remove reports (if applicable, not used here currently)

# --- Role ID Check Setup ---
try:
    # Using a distinct role ID for perco admin might be better,
    # but using PAY_COMMAND_ROLE_ID for now as requested previously.
    # Ensure PAY_COMMAND_ROLE_ID is set in your .env file
    PERCO_ADMIN_ROLE_ID = int(os.getenv('PAY_COMMAND_ROLE_ID'))
    if PERCO_ADMIN_ROLE_ID is None:
         logger.error("PAY_COMMAND_ROLE_ID (used for Perco Admin) not found in .env file.")
         PERCO_ADMIN_ROLE_ID = 0
    else:
        logger.info(f"PERCO_ADMIN_ROLE_ID loaded: {PERCO_ADMIN_ROLE_ID}")
except (TypeError, ValueError):
    logger.error("PAY_COMMAND_ROLE_ID (used for Perco Admin) in .env file is not a valid integer.")
    PERCO_ADMIN_ROLE_ID = 0

def has_perco_admin_role():
    """Check if the user has the required role for Perco admin commands."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None: return False # Cannot check roles in DMs
        if PERCO_ADMIN_ROLE_ID == 0: return False # Cannot check if role ID is invalid/not configured
        # Ensure the author is a Member object to access roles
        if not isinstance(ctx.author, discord.Member): return False
        # Check if any of the member's roles matches the required ID
        required_role = discord.utils.get(ctx.author.roles, id=PERCO_ADMIN_ROLE_ID)
        return required_role is not None
    return commands.check(predicate)


# --- Cog Definition ---
class ResaPercoCog(commands.Cog, name="Réservations Perco"):
    """Commandes pour gérer les réservations de percepteurs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize Perco manager (it now handles its own loading)
        self.perco_manager = perco.Perco()
        logger.info("Perco manager initialized (data loading attempted within).")

        # Ensure bot has the send_long_message helper method
        if not hasattr(bot, 'send_long_message'):
            logger.error("Bot instance is missing 'send_long_message' helper method!")
            # Define a basic fallback if the method is missing
            async def _send_long_message_fallback(channel, content):
                 if len(content) <= 2000: await channel.send(content)
                 else: await channel.send(content[:1990] + "...") # Basic truncation
            bot.send_long_message = _send_long_message_fallback
            logger.warning("Added fallback send_long_message to bot instance.")


    # --- Reservation Commands ---

    @commands.command(name='reserver', aliases=['resa', 'book'], help="Réserve un emplacement perco. Usage: `!reserver <localisation> <jour (1-7)>`")
    async def reserver_perco(self, ctx: commands.Context, localisation: str, jour: str):
        """Reserves a spot for the command author."""
        user_name_cleaned = clean_name(ctx.author.display_name)
        if not user_name_cleaned:
            await ctx.send("❌ Impossible de déterminer votre nom d'utilisateur (après nettoyage).")
            return

        user_name_to_reserve = user_name_cleaned
        loc_input = localisation.lower() # For case-insensitive comparison

        # Find the actual case-sensitive location name stored in the manager
        actual_localisation = discord.utils.find(lambda l: l.lower() == loc_input, self.perco_manager.localisations)

        # If not found directly, double check ignoring case before declaring invalid
        if not actual_localisation:
             if not any(loc.lower() == loc_input for loc in self.perco_manager.localisations):
                 await ctx.send(f"❌ Localisation `{localisation}` invalide. Utilisez `!perco_locs` pour voir la liste.")
                 return
             else:
                 # Should ideally not happen if utils.find works correctly, but handle edge case
                 logger.warning(f"Location casing issue? Input '{localisation}' seems valid but wasn't found by utils.find. Using input casing.")
                 actual_localisation = localisation # Fallback

        logger.info(f"'!reserver {actual_localisation} {jour}' invoked by {ctx.author.display_name} ({user_name_to_reserve})")

        try:
            # Call the manager's reserve method (now uses lists internally)
            success, code = self.perco_manager.reserve(actual_localisation, user_name_to_reserve, jour)

            if success:
                await ctx.send(f"✅ **{ctx.author.display_name}**, ta réservation pour **{actual_localisation}** le jour **{jour}** est confirmée !")
                logger.info(f"Reservation success for {user_name_to_reserve} at {actual_localisation} day {jour}.")
            else:
                # Determine number of days dynamically for error message
                num_days_str = "?"
                if self.perco_manager.tableau and isinstance(self.perco_manager.tableau, list):
                    num_days_str = str(len(self.perco_manager.tableau))

                # Updated Error Messages based on new codes in refactored perco.py
                error_messages = {
                    1: f"❌ Jour `{jour}` invalide. Le jour doit être un nombre entre 1 et {num_days_str}.",
                    2: f"❌ Limite de réservation atteinte (maximum 2 réservations au total par personne).",
                    3: f"❌ Localisation `{actual_localisation}` invalide.", # Should be caught above
                    5: f"❌ Cet emplacement est déjà réservé par quelqu'un d'autre ce jour-là.",
                   -1: f"❌ Une erreur système est survenue durant la réservation (ex: sauvegarde impossible)."
                }
                error_msg = error_messages.get(code, f"❌ Erreur inconnue ({code}) lors de la réservation.")
                await ctx.send(error_msg)
                logger.warning(f"Reservation failed for {user_name_to_reserve} at {actual_localisation} day {jour}. Code: {code}, Message: {error_msg}")

        except Exception as e:
            logger.exception(f"Unexpected error during !reserver execution for {user_name_to_reserve}: {e}")
            await ctx.send(f"❌ Une erreur interne imprévue est survenue lors de la tentative de réservation.")


    @commands.command(name='annuler', aliases=['cancel', 'unbook'], help="Annule votre réservation perco. Usage: `!annuler <localisation> <jour (1-7)>`")
    async def annuler_perco(self, ctx: commands.Context, localisation: str, jour: str):
        """Cancels the command author's reservation."""
        user_name_cleaned = clean_name(ctx.author.display_name)
        if not user_name_cleaned:
            await ctx.send("❌ Impossible de déterminer votre nom d'utilisateur (après nettoyage).")
            return

        user_name_to_cancel_for = user_name_cleaned
        loc_input = localisation.lower()

        # Find actual location name
        actual_localisation = discord.utils.find(lambda l: l.lower() == loc_input, self.perco_manager.localisations)
        if not actual_localisation:
             if not any(loc.lower() == loc_input for loc in self.perco_manager.localisations):
                 await ctx.send(f"❌ Localisation `{localisation}` invalide. Utilisez `!perco_locs`.")
                 return
             else:
                  actual_localisation = localisation # Fallback

        logger.info(f"'!annuler {actual_localisation} {jour}' invoked by {ctx.author.display_name} ({user_name_to_cancel_for})")

        try:
            # Call the manager's cancel method
            success, code = self.perco_manager.cancel(actual_localisation, user_name_to_cancel_for, jour)

            if success:
                await ctx.send(f"✅ **{ctx.author.display_name}**, ta réservation pour **{actual_localisation}** le jour **{jour}** a été annulée.")
                logger.info(f"Cancellation success for {user_name_to_cancel_for} at {actual_localisation} day {jour}.")
            else:
                # Get number of days dynamically
                num_days_str = "?"
                if self.perco_manager.tableau and isinstance(self.perco_manager.tableau, list):
                    num_days_str = str(len(self.perco_manager.tableau))

                # Updated Error Messages
                error_messages = {
                    1: f"❌ Jour `{jour}` invalide. Le jour doit être un nombre entre 1 et {num_days_str}.",
                    2: f"❌ Localisation `{actual_localisation}` invalide.", # Should be caught above
                    3: "❌ Aucune réservation n'existe pour cet emplacement ce jour-là.",
                    4: "❌ Cette réservation n'a pas été faite par toi.",
                   -1: f"❌ Une erreur système est survenue durant l'annulation (ex: sauvegarde impossible)."
                }
                error_msg = error_messages.get(code, f"❌ Erreur inconnue ({code}) lors de l'annulation.")
                await ctx.send(error_msg)
                logger.warning(f"Cancellation failed for {user_name_to_cancel_for} at {actual_localisation} day {jour}. Code: {code}, Message: {error_msg}")

        except Exception as e:
            logger.exception(f"Unexpected error during !annuler execution for {user_name_to_cancel_for}: {e}")
            await ctx.send(f"❌ Une erreur interne imprévue est survenue lors de la tentative d'annulation.")


    # --- Viewing Commands ---

    @commands.command(name='tableau', aliases=['planning', 'schedule'], help="Affiche le planning des réservations.")
    async def tableau_perco(self, ctx: commands.Context):
        """Displays the current reservation schedule using lists."""
        logger.info(f"'!tableau' command invoked by {ctx.author}")

        locations = self.perco_manager.localisations
        schedule: list[list[str]] | None = self.perco_manager.tableau

        # Validate that data seems usable
        if schedule is None or not isinstance(schedule, list):
            logger.error("!tableau cannot execute: perco_manager.tableau is not loaded or not a list.")
            await ctx.send("❌ Erreur : Les données du planning ne sont pas chargées correctement. Contactez un admin ou essayez `!perco_refresh`.")
            return

        if not locations:
            await ctx.send("ℹ️ Aucune localisation n'est configurée. Le tableau ne peut pas être affiché.")
            return
        if not schedule: # Empty list of days
             await ctx.send("ℹ️ Le planning est actuellement vide.")
             return

        # --- Determine dimensions and validate basic structure ---
        try:
            num_days = len(schedule)
            num_locs = len(locations)
            # Check if first row matches expected location count (if rows exist)
            if num_days > 0 and isinstance(schedule[0], list) and len(schedule[0]) != num_locs:
                 logger.error(f"Data inconsistency: Locations count ({num_locs}) != schedule day 1 length ({len(schedule[0])}).")
                 await ctx.send("❌ Erreur : Incohérence interne détectée dans les données du planning (nombre de colonnes). Essayez `!perco_refresh`.")
                 return
            if num_days != 7:
                 logger.warning(f"Tableau has {num_days} days in memory, expected 7. Displaying available days.")

        except Exception as e:
            logger.exception(f"!tableau error getting dimensions or basic validation: {e}")
            await ctx.send("❌ Erreur : Format interne des données du planning invalide.")
            return
        # --- End Validation ---

        try:
            # --- Formatting Logic (Using list indexing) ---
            # Calculate max width needed for each column
            loc_widths = [len(loc) for loc in locations]
            name_widths = [[min(len(str(schedule[d][l])), MAX_NAME_DISPLAY_LEN)
                            if d < len(schedule) and isinstance(schedule[d], list) and l < len(schedule[d])
                            else 0
                            for l in range(num_locs)]
                           for d in range(num_days)]

            col_widths = [max(loc_widths[l] if l < len(loc_widths) else 0,
                            max(name_widths[d][l] for d in range(num_days)) if num_days > 0 and l < len(name_widths[0]) else 0)
                          for l in range(num_locs)]
            day_col_width = 4 # Width for "Jour" column

            # Build Header Row
            header = f"{'Jour':<{day_col_width}} |"
            for i, loc in enumerate(locations):
                # Ensure index is valid for col_widths
                width = col_widths[i] if i < len(col_widths) else len(loc)
                header += f" {loc:<{width}} |"

            # Build Separator Row
            separator_widths = [col_widths[i] if i < len(col_widths) else len(locations[i]) for i in range(num_locs)]
            separator = f"{'-'*day_col_width}-+-" + "-+-".join(['-'*w for w in separator_widths]) + "-+"

            # Build Data Rows
            rows = []
            for day_idx in range(num_days): # Iterate only available days
                day_num_str = f"  {day_idx+1:<{day_col_width-2}}" # Format day number
                row = f"{day_num_str} |"
                for loc_idx in range(num_locs):
                    # Safely access name using list indexing
                    name = ""
                    if day_idx < len(schedule) and isinstance(schedule[day_idx], list) and loc_idx < len(schedule[day_idx]):
                         name = str(schedule[day_idx][loc_idx]) # Ensure it's a string

                    # Truncate if necessary for display
                    display_name = name[:MAX_NAME_DISPLAY_LEN] if len(name) > MAX_NAME_DISPLAY_LEN else name
                    # Get width, defaulting if needed
                    width = col_widths[loc_idx] if loc_idx < len(col_widths) else len(locations[loc_idx]) if loc_idx < len(locations) else 0
                    row += f" {display_name:<{width}} |"
                rows.append(row)

            # Combine into final string within a code block
            tableau_str = "```\n" + header + "\n" + separator + "\n" + "\n".join(rows) + "\n```"
            # --- End Formatting Logic ---

            # Send using the bot's helper for potentially long messages
            await self.bot.send_long_message(ctx.channel, tableau_str)

        except IndexError as ie:
             logger.exception(f"IndexError during !tableau formatting (List of Lists). Data shape/consistency issue? {ie}")
             await ctx.send("❌ Une erreur d'index est survenue lors de la génération du tableau. Les données sont peut-être corrompues. Essayez `!perco_refresh`.")
        except Exception as e:
            logger.exception("Unexpected error formatting !tableau output.")
            await ctx.send("❌ Une erreur imprévue est survenue lors de la génération du tableau.")


    @commands.command(name='perco_locs', aliases=['locations'], help="Liste les localisations perco disponibles.")
    async def perco_locations(self, ctx: commands.Context):
        """Lists the available Perco locations."""
        logger.info(f"'!perco_locs' command invoked by {ctx.author}")
        locations = self.perco_manager.localisations
        if not locations:
            await ctx.send("ℹ️ Aucune localisation n'est configurée pour le moment.")
            return

        # Sort locations alphabetically for display
        loc_list_str = "\n".join(f"- `{loc}`" for loc in sorted(locations))
        # Send using the bot's helper function
        await self.bot.send_long_message(ctx.channel, f"📍 **Localisations Perco Disponibles**\n{loc_list_str}")


    @commands.command(name='mesresa', aliases=['mybookings'], help="Affiche vos réservations actuelles.")
    async def mes_reservations(self, ctx: commands.Context):
        """Shows the current user's reservations."""
        user_name_cleaned = clean_name(ctx.author.display_name)
        if not user_name_cleaned:
            await ctx.send("❌ Impossible de déterminer votre nom d'utilisateur (après nettoyage).")
            return

        logger.info(f"'!mesresa' command invoked by {ctx.author.display_name} ({user_name_cleaned})")

        locations = self.perco_manager.localisations
        schedule: list[list[str]] | None = self.perco_manager.tableau
        my_reservations = []

        # Check if data is valid before iterating
        if schedule and isinstance(schedule, list) and locations:
            num_locs = len(locations)
            try:
                for day_idx, day_list in enumerate(schedule):
                    # Ensure the day's data is a list and has the expected number of locations
                    if isinstance(day_list, list) and len(day_list) == num_locs:
                        for loc_idx in range(num_locs):
                            # Check if the slot matches the user's cleaned name
                            if day_list[loc_idx] == user_name_cleaned:
                                my_reservations.append(f"Jour {day_idx + 1} - `{locations[loc_idx]}`")
                    elif isinstance(day_list, list): # Log if a row has an unexpected length
                         logger.warning(f"Row {day_idx+1} length mismatch in !mesresa (Expected {num_locs}, got {len(day_list)})")

            except Exception as e:
                 logger.exception(f"Error processing schedule in !mesresa for {user_name_cleaned}: {e}")

        # Report findings
        if not my_reservations:
            await ctx.send(f"ℹ️ **{ctx.author.display_name}**, tu n'as aucune réservation enregistrée actuellement.")
        else:
            # Sort reservations for consistent display (e.g., by day, then location)
            # Current format "Jour X - `Location`" sorts reasonably well
            resa_list_str = "\n".join(f"- {resa}" for resa in sorted(my_reservations))
            await self.bot.send_long_message(ctx.channel, f"🗓️ **Tes Réservations Actuelles** ({ctx.author.display_name})\n{resa_list_str}")


    # --- Admin Commands ---

    @commands.command(name='perco_refresh', help="Recharge les données perco depuis les fichiers (Rôle requis).", hidden=True)
    @has_perco_admin_role()
    @commands.guild_only()
    async def perco_refresh(self, ctx: commands.Context):
        """Reloads Perco data from files."""
        logger.warning(f"'!perco_refresh' command invoked by {ctx.author}")
        msg = await ctx.send("🔄 Rechargement des données Perco en cours...")
        try:
            success = self.perco_manager.refresh() # refresh now calls load_data
            if success:
                await msg.edit(content="✅ Données Perco rechargées depuis les fichiers (`localisations.txt`, `tableau.txt`).")
                logger.info("Perco data refreshed successfully via command.")
            else:
                 await msg.edit(content="⚠️ Le rechargement des données Perco a rencontré des problèmes (voir les logs du bot). Les données actuelles peuvent être incomplètes ou vides.")
                 logger.warning("Perco data refresh via command completed with issues.")

        except Exception as e: # Catch any unexpected error during refresh call
            logger.exception("Unexpected error during !perco_refresh.")
            await msg.edit(content=f"❌ Une erreur imprévue est survenue lors du rechargement: ```{e}```")


    @commands.command(name='perco_raz', help="Réinitialise le planning perco (Rôle requis). ATTENTION: Efface tout!", hidden=True)
    @has_perco_admin_role()
    @commands.guild_only()
    async def perco_reset(self, ctx: commands.Context):
        """Resets the Perco schedule."""
        logger.warning(f"'!perco_raz' command invoked by {ctx.author}. This will clear the schedule.")

        msg = await ctx.send("⏳ Réinitialisation du planning Perco en cours...")
        try:
            success = self.perco_manager.raz()
            if success:
                await msg.edit(content="✅ Planning Perco réinitialisé et sauvegardé (vide).")
                logger.info("Perco data reset successfully via command.")
            else:
                await msg.edit(content="❌ La réinitialisation a échoué. Vérifiez que `localisations.txt` existe et que le bot peut écrire `tableau.txt` (voir les logs).")
                logger.error("Perco data reset via command failed.")
        except Exception as e: # Catch any unexpected error during raz call
            logger.exception("Unexpected error during !perco_raz.")
            await msg.edit(content=f"❌ Une erreur imprévue est survenue lors de la réinitialisation: ```{e}```")

    # --- Error Handlers for Admin Commands ---
    @perco_refresh.error
    async def perco_refresh_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande.")
        else:
            await ctx.send(f"Erreur inattendue avec la commande !perco_refresh: ```{error}```")
            logger.error(f"Unexpected error caught by !perco_refresh handler: {error}")

    @perco_reset.error
    async def perco_reset_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("Désolé, tu n'as pas le rôle requis pour utiliser cette commande.")
        else:
            await ctx.send(f"Erreur inattendue avec la commande !perco_raz: ```{error}```")
            logger.error(f"Unexpected error caught by !perco_raz handler: {error}")


# --- Async Setup Function ---
async def setup(bot: commands.Bot):
    """Loads the ResaPercoCog."""
    # Check for essential configuration file at startup
    if not os.path.exists("localisations.txt"):
         logger.error("CRITICAL: 'localisations.txt' not found. ResaPercoCog cannot function without it.")
         # Optionally prevent loading if the file is absolutely mandatory
         # raise commands.ExtensionFailed("ResaPercoCog", "Missing required file: localisations.txt")

    # Add the cog to the bot
    await bot.add_cog(ResaPercoCog(bot))
    logger.info("ResaPercoCog loaded successfully.")