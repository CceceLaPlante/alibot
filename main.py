# bot.py
import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv

# Import your data handling and processing modules
import id_card

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True


# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
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
    except (ValueError, TypeError):
         logger.error("PAY_COMMAND_ROLE_ID in .env file is not a valid integer. The !pay command will not function correctly.")
# ----------------------------------------------------

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True # Needed for roles
intents.members = True # Potentially needed to ensure member cache is populated for role checks


# --- Data Loading ---
# ... (keep data loading as it is) ...
try:
    initial_hashes = id_card.open_saved_hash()
    initial_known_names = id_card.open_known_names()
    initial_ids = id_card.cards_from_file()

    if not initial_ids and initial_known_names:
        logger.info("IDS data is empty, initializing from known names.")
        initial_ids = id_card.init_from_list(initial_known_names)
        id_card.save_card(initial_ids)
    elif not initial_known_names:
         logger.warning("KNOWN_NAMES data is empty. Some features might not work as expected.")

except FileNotFoundError as e:
    logger.error(f"Data file not found: {e}. Creating empty defaults.")
    initial_hashes = []
    initial_known_names = []
    initial_ids = []
    # Consider creating initial empty files here if desired
    try:
        id_card.save_saved_hash([])
        id_card.save_known_names([]) # Or however you save names
        id_card.save_card([])
        logger.info("Created empty data files.")
    except Exception as save_err:
        logger.error(f"Failed to create initial empty data files: {save_err}")
except Exception as e:
    logger.exception(f"An critical error occurred during data loading: {e}")
    exit(1)


# Create the Bot instance
class Alibot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hashes = initial_hashes
        self.known_names = initial_known_names
        self.ids_data = initial_ids

    async def setup_hook(self):
        """Loads extensions (cogs) asynchronously."""
        cog_files = ['cogs.info', 'cogs.screen', 'cogs.data_management'] 
        for extension in cog_files:
            try:
                await self.load_extension(extension)
                logger.info(f'Successfully loaded extension: {extension}')
            except Exception as e: # Catch more general errors during loading
                logger.exception(f'Failed to load extension {extension}.', exc_info=e) # Log full traceback
        logger.info("Attempted to load all cogs.")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')
        logger.info(f'Discord.py version: {discord.__version__}')
        logger.info('Bot is ready and online.')
        # You could sync commands if using slash commands here
        # try:
        #     synced = await self.tree.sync()
        #     logger.info(f"Synced {len(synced)} application commands.")
        # except Exception as e:
        #     logger.exception(f"Failed to sync application commands: {e}")

    # (Optional) on_message can be removed if only using prefix commands in cogs
    # async def on_message(self, message):
    #     if message.author == self.user:
    #         return
    #     # logger.debug(f'Message from {message.author} in {message.channel}: {message.content}')
    #     await self.process_commands(message)

    async def send_long_message(self, channel, content):
       # ... (keep this helper function as it is) ...
        if len(content) <= 2000:
            await channel.send(content)
        else:
            logger.info(f"Message length ({len(content)}) exceeds 2000 chars, splitting.")
            chunks = [content[i:i+1990] for i in range(0, len(content), 1990)] # Split safely
            for chunk in chunks:
                await channel.send(chunk)


# Instantiate and run the bot
bot = Alibot(command_prefix='!', intents=intents)

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.critical("CRITICAL: Login failed: Invalid token provided.") # Changed to critical
    except discord.PrivilegedIntentsRequired:
         logger.critical("CRITICAL: Privileged intents (Guilds, Members) are not enabled for the bot in the developer portal.")
    except Exception as e:
        logger.exception(f"An critical error occurred while running the bot: {e}") # Use exception for traceback
    finally:
        logger.info("Bot process is terminating.")