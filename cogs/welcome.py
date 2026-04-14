import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("fpvgate-bot.welcome")


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.bot.config.get("welcome", {})
        if not cfg.get("enabled", True):
            return

        title = cfg.get("title", "Welcome!")
        message = cfg.get("message", "Welcome to the server!").replace("{member}", member.display_name)
        color = int(cfg.get("embed_color", "0x00BFFF"), 16)

        # Add link to rules/roles message if available
        roles_url = self.bot.config.get("reaction_roles", {}).get("roles_message_url")
        if roles_url:
            message += f"\n\n**Read the rules and react to gain access:** {roles_url}"

        embed = discord.Embed(title=title, description=message, color=color)
        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else "")
        embed.set_footer(text=member.guild.name)

        try:
            await member.send(embed=embed)
            log.info(f"Sent welcome DM to {member} ({member.id})")
        except discord.Forbidden:
            log.warning(f"Could not DM {member} ({member.id}) - DMs are disabled.")

    @app_commands.command(name="set_welcome", description="Update the welcome message settings.")
    @app_commands.describe(
        enabled="Enable or disable welcome DMs",
        title="Embed title",
        message="Welcome message body. Use {member} for the member's name.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_welcome(
        self,
        interaction: discord.Interaction,
        enabled: bool = True,
        title: str = None,
        message: str = None,
    ):
        cfg = self.bot.config.setdefault("welcome", {})
        cfg["enabled"] = enabled
        if title is not None:
            cfg["title"] = title
        if message is not None:
            cfg["message"] = message

        from bot import save_config
        save_config(self.bot.config)

        await interaction.response.send_message("Welcome settings updated.", ephemeral=True)

    @app_commands.command(name="test_welcome", description="Send yourself a preview of the welcome DM.")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_welcome(self, interaction: discord.Interaction):
        cfg = self.bot.config.get("welcome", {})
        title = cfg.get("title", "Welcome!")
        message = cfg.get("message", "Welcome to the server!").replace("{member}", interaction.user.display_name)
        color = int(cfg.get("embed_color", "0x00BFFF"), 16)

        roles_url = self.bot.config.get("reaction_roles", {}).get("roles_message_url")
        if roles_url:
            message += f"\n\n**Read the rules and react to gain access:** {roles_url}"

        embed = discord.Embed(title=title, description=message, color=color)
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else "")
        embed.set_footer(text=interaction.guild.name)

        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("Welcome DM preview sent! Check your DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Could not send you a DM. Check your privacy settings.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
