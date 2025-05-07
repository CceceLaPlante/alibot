# cogs/info.py
import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class InfoCog(commands.Cog):
    """Cog for basic informational commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='info', help="Affiche des informations sur Alibot.")
    async def info_command(self, ctx: commands.Context):
        """Provides basic information about the bot."""
        logger.info(f"'!info' command invoked by {ctx.author}")
        await ctx.send("Coucou je suis Alibot, j'ai été créé par World-Timer et je sert à save les sreens !")

    @commands.command(name='test', help="Affiche les données internes (pour le debug).")
    async def test_command(self, ctx: commands.Context):
        """Displays internal data structures for debugging."""
        logger.info(f"'!test' command invoked by {ctx.author} (Debug command)")
        # Access data stored in the bot instance
        hashes_str = f"Hashes ({len(self.bot.hashes)}): {self.bot.hashes}"
        known_names_str = f"Known Names ({len(self.bot.known_names)}): {self.bot.known_names}"
        ids_str = f"IDs ({len(self.bot.ids_data)}):\n" + "\n".join([str(ids) for ids in self.bot.ids_data])

        await self.bot.send_long_message(ctx.channel, hashes_str)
        await self.bot.send_long_message(ctx.channel, known_names_str)
        await self.bot.send_long_message(ctx.channel, ids_str)

    # You can create a more elaborate help command if needed,
    # or rely on the default one provided by discord.ext.commands
    @commands.command(name='aled', aliases=[ 'aide'], help="Affiche ce message d'aide détaillé.")
    async def info_command(self, ctx: commands.Context):
        """Provides a detailed list of available commands grouped by category (Cog)."""
        logger.info(f"'!info' command invoked by {ctx.author}")

        embed = discord.Embed(
            title="📜 Aide du Bot Alibot 📜",
            description=f"Liste des commandes disponibles. Utilisez `{self.bot.command_prefix}<commande>` pour les exécuter.",
            color=discord.Color.blurple() # Or any color you prefer
        )

        # Group commands by Cog
        cogs_commands = {}
        for command in self.bot.commands:
            if command.hidden:
                continue # Skip hidden commands

            cog = command.cog
            if cog is None:
                cog_name = "🔧 Commandes Générales" # Category for commands without a cog
            else:
                cog_name = f"⚙️ {cog.qualified_name}" # Use Cog name as category

            if cog_name not in cogs_commands:
                cogs_commands[cog_name] = {
                    "description": cog.description if cog else "Commandes de base du bot.",
                    "commands": []
                 }

            # Format the command signature and help text
            signature = f"`{self.bot.command_prefix}{command.qualified_name}"
            if command.signature: # Add arguments if they exist
                 signature += f" {command.signature}`"
            else:
                 signature += "`"

            # Add aliases if they exist
            if command.aliases:
                aliases_str = ", ".join(f"`{self.bot.command_prefix}{alias}`" for alias in command.aliases)
                signature += f" (Alias: {aliases_str})"

            help_text = command.help or "Pas d'aide disponible pour cette commande."
            cogs_commands[cog_name]["commands"].append(f"{signature}\n* {help_text}")

        # Add fields to the embed for each Cog
        if not cogs_commands:
             embed.description += "\n\nAucune commande disponible n'a été trouvée."
        else:
            for cog_name, data in sorted(cogs_commands.items()): # Sort categories alphabetically
                commands_list_str = "\n\n".join(data['commands'])
                # Check if the field value exceeds the limit
                if len(commands_list_str) > 1024:
                     logger.warning(f"Command list for cog '{cog_name}' exceeds 1024 chars, truncating.")
                     # Truncate safely
                     commands_list_str = commands_list_str[:1020] + "..."

                if commands_list_str: # Only add field if there are commands listed
                    embed.add_field(
                        name=f"**{cog_name}**",
                        value=f"*{data['description']}*\n{commands_list_str}",
                        inline=False
                    )

        embed.set_footer(text="Bot développé par Céleste / World-timer")
        await ctx.send(embed=embed)


# This setup function is required for the cog to be loaded by the bot
async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCog(bot))
    logger.info("InfoCog loaded.")