import discord
from discord.ext import commands
import emoji
import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    logger.critical("CRITICAL: Discord token not found. Make sure DISCORD_TOKEN is set in your .env file.") # Changed to critical
    exit(1) # Exit with non-zero code

# --- Optional: Check for Pay Role ID at startup ---
PAY_ROLE_ID_STR = os.getenv('PAY_COMMAND_ROLE_ID')
if PAY_ROLE_ID_STR is None:
    logger.warning("PAY_COMMAND_ROLE_ID not found in .env file. The !pay command will require configuration.")
else:
    try:
        int(PAY_ROLE_ID_STR) # Try converting to int to check validity
        logger.info("PAY_COMMAND_ROLE_ID found in .env file.")
        PAY_ROLE_ID = int(PAY_ROLE_ID_STR) # Store as integer for later use
    except (ValueError, TypeError):
         logger.error("PAY_COMMAND_ROLE_ID in .env file is not a valid integer. The !pay command will not function correctly.")


def has_pay_role():
    # ... (implementation remains the same) ...
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            logger.warning(f"Role check failed: Command used outside of a guild by {ctx.author}.")
            return False
        if PAY_ROLE_ID == 0:
             logger.error(f"Role check failed: PAY_COMMAND_ROLE_ID is not configured correctly. Denying command for {ctx.author}.")
             return False
        if not isinstance(ctx.author, discord.Member):
             logger.warning(f"Role check failed: Could not verify roles for {ctx.author} (not a Member object). Denying command.")
             return False
        required_role = discord.utils.get(ctx.author.roles, id=PAY_ROLE_ID)
        return required_role is not None
    return commands.check(predicate)

# --- Helper function to clean names (emoji removal, lowercase, strip) ---
def clean_name(raw_name: str) -> str:
    """Removes emojis, converts to lowercase, and strips whitespace."""
    if not isinstance(raw_name, str):
        return ""
    name_no_emoji = emoji.replace_emoji(raw_name, replace='').strip()
    # Remove any non-ASCII characters 
    name_no_emoji = ''.join(c for c in name_no_emoji if ord(c) < 128)

    if name_no_emoji == "":
        return "[chelou]" # Return empty if all characters were removed
    return name_no_emoji.lower()

# --- Helper function for list embeds (or use bot.send_long_message) ---
async def send_list_embed(ctx: commands.Context, title: str, items: list[str], empty_message: str, color=discord.Color.blue()):
    if not items:
        await ctx.send(embed=discord.Embed(description=empty_message, color=color))
        return
    # Simple approach: join items for description
    description = "\n".join(f"- `{item}`" for item in items) # Add backticks for clarity
    # Use bot's helper for potentially long lists
    full_content = f"**{title}**\n{description}"
    # Accessing bot instance via ctx.bot
    await ctx.bot.send_long_message(ctx.channel, full_content)


# --- Embed Creator Function ---
def create_id_card_embed(ids_item, page_num: int, total_pages: int) -> discord.Embed:
    try:
        name = getattr(ids_item, 'name', 'Nom Inconnu')
        haschanged = getattr(ids_item, 'haschanged', True)
        perco_fight_win = getattr(ids_item, 'perco_fight_win', 0)
        perco_fight_loose = getattr(ids_item, 'perco_fight_loose', 0)
        perco_fight_total = perco_fight_win + perco_fight_loose
        prisme_fight_win = getattr(ids_item, 'prisme_fight_win', 0)
        prisme_fight_loose = getattr(ids_item, 'prisme_fight_loose', 0)
        prisme_fight_total = prisme_fight_win + prisme_fight_loose
        perco_won_unpaid = getattr(ids_item, 'perco_won_unpaid', 0)
        perco_loose_unpaid = getattr(ids_item, 'perco_loose_unpaid', 0)
        prisme_won_unpaid = getattr(ids_item, 'prisme_won_unpaid', 0)
        prisme_loose_unpaid = getattr(ids_item, 'prisme_loose_unpaid', 0)
        status_emoji = "❌" if haschanged else "✅"
        status_text = "Non Payé" if haschanged else "Payé"
        embed_color = discord.Color.orange() if haschanged else discord.Color.green()
        embed = discord.Embed(title=f"{status_emoji} Fiche: {name}", description=f"Statut: **{status_text}**", color=embed_color)
        embed.set_footer(text=f"Page {page_num}/{total_pages}")
        embed.add_field(name="📊 Statistiques Totales", value=(f"**Percepteurs:** G: `{perco_fight_win}` | P: `{perco_fight_loose}` | Total: `{perco_fight_total}`\n" f"**Prismes:** G: `{prisme_fight_win}` | P: `{prisme_fight_loose}` | Total: `{prisme_fight_total}`"), inline=False)
        if haschanged:
            embed.add_field(name="🚫 Détails Non Payés", value=(f"**Percepteurs:** G: `{perco_won_unpaid}` | P: `{perco_loose_unpaid}`\n" f"**Prismes:** G: `{prisme_won_unpaid}` | P: `{prisme_loose_unpaid}`"), inline=False)
    except Exception as e:
        logger.error(f"Error creating embed for item '{getattr(ids_item, 'name', 'UNKNOWN')}': {e}")
        embed = discord.Embed(title="⚠️ Erreur d'Affichage", description=f"Impossible de générer la fiche pour {getattr(ids_item, 'name', 'cet élément')}.\nErreur: ```{e}```", color=discord.Color.red())
        embed.set_footer(text=f"Page {page_num}/{total_pages}")
    return embed
