# utils/ui.py (or place in cogs/data_management.py)

import discord
import asyncio

class PaginationView(discord.ui.View):
    """
    A View for paginating through a list of data represented by embeds.

    Attributes:
        data (list): The list of items to paginate through.
        create_embed_func (callable): A function that takes an item from `data`
                                       and the current page/total pages, and returns a discord.Embed.
        author_id (int): The ID of the user who initiated the command.
        current_page (int): The current page index (0-based).
        message (discord.Message): The message this view is attached to. Set after sending.
    """
    def __init__(self, data: list, create_embed_func: callable, author_id: int, timeout=180.0):
        """
        Initializes the PaginationView.

        Args:
            data (list): The list of items to paginate.
            create_embed_func (callable): Function to create an embed for an item.
                                           Signature: func(item, current_page, total_pages) -> discord.Embed
            author_id (int): The ID of the user who can interact with the buttons.
            timeout (float, optional): How long the view should wait for interaction before timing out. Defaults to 180.0.
        """
        super().__init__(timeout=timeout)
        if not data:
            raise ValueError("PaginationView received empty data list.")

        self.data = data
        self.create_embed_func = create_embed_func
        self.author_id = author_id
        self.current_page = 0
        self.total_pages = len(data)
        self.message = None # Will be set later

        # Initialize button states
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Checks if the interacting user is the one who initiated the command."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Tu ne peux pas contrôler ce menu.", ephemeral=True)
            return False
        return True

    def _update_buttons(self):
        """Enables/disables buttons based on the current page."""
        self.children[0].disabled = self.current_page == 0 # Disable previous on first page
        self.children[1].disabled = self.current_page == self.total_pages - 1 # Disable next on last page

    async def _update_message(self, interaction: discord.Interaction):
        """Edits the original message with the new embed and updated buttons."""
        self._update_buttons()
        embed = self.create_embed_func(self.data[self.current_page], self.current_page + 1, self.total_pages)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⬅️ Précédent", style=discord.ButtonStyle.primary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self._update_message(interaction)
        else:
             # Should not happen if button is disabled, but good practice
             await interaction.response.defer() # Acknowledge interaction silently

    @discord.ui.button(label="Suivant ➡️", style=discord.ButtonStyle.primary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self._update_message(interaction)
        else:
             # Should not happen if button is disabled, but good practice
             await interaction.response.defer() # Acknowledge interaction silently

    @discord.ui.button(label="⏹️ Arrêter", style=discord.ButtonStyle.danger, row=0)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Stops the pagination view and disables buttons."""
        self.stop() # Stop listening for interactions
        for child in self.children:
            child.disabled = True
        # Edit the message one last time to show disabled buttons
        await interaction.response.edit_message(view=self)
        self.message = None # Clear message reference

    async def on_timeout(self):
        """Disables buttons when the view times out."""
        if self.message: # Check if message still exists
            try:
                for item in self.children:
                    item.disabled = True
                # Edit the message with disabled buttons if possible
                await self.message.edit(view=self)
            except discord.NotFound:
                pass # Message might have been deleted
            except discord.HTTPException as e:
                 print(f"Failed to edit message on timeout: {e}") # Log error if needed
        self.stop() # Ensure the view is stopped

    async def start(self, ctx):
        """Sends the initial message with the first page and the view."""
        embed = self.create_embed_func(self.data[self.current_page], self.current_page + 1, self.total_pages)
        self.message = await ctx.send(embed=embed, view=self)