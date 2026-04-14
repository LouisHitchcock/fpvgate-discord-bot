import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("fpvgate-bot.reaction_roles")


class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _get_role_message_config(self, message_id: int) -> dict | None:
        """Find the config entry for a tracked role message."""
        for entry in self.bot.config["reaction_roles"]["messages"]:
            if entry["message_id"] == message_id:
                return entry
        return None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        entry = self._get_role_message_config(payload.message_id)
        if entry is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(entry["role_id"])
        member = guild.get_member(payload.user_id)
        if role and member and role not in member.roles:
            await member.add_roles(role)
            log.info(f"Gave {member} the {role.name} role")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        entry = self._get_role_message_config(payload.message_id)
        if entry is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(entry["role_id"])
        member = guild.get_member(payload.user_id)
        if role and member and role in member.roles:
            await member.remove_roles(role)
            log.info(f"Removed {role.name} from {member}")

    @app_commands.command(name="post_rules", description="Post the FPVGate rules message with reaction-role access.")
    @app_commands.describe(
        role="The role to assign when someone reacts",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def post_rules(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        rules_text = (
            "**Welcome to the FPVGate Discord server!**\n\n"
            "Be respectful to one another.\n"
            "Conduct yourself appropriately for the situation.\n"
            "Keep content and discussions in the relevant channels where possible.\n"
            "Avoid posting anything offensive, this community includes people from all backgrounds and age groups.\n"
            "Follow Discord's Community Guidelines at all times.\n"
            "If you have any issues, please contact a member of the Committee, Admin, or Moderator team.\n\n"
            "**Enjoy your stay with us**\n\n"
            "Please react to this message to gain access to the rest of the Server"
        )

        await interaction.response.send_message(rules_text)
        msg = await interaction.original_response()

        # Persist to config
        config = self.bot.config
        config["reaction_roles"]["messages"].append(
            {
                "channel_id": interaction.channel_id,
                "message_id": msg.id,
                "role_id": role.id,
            }
        )
        config["reaction_roles"]["roles_message_url"] = msg.jump_url
        self._save()

        log.info(f"Posted rules message for {role.name} in #{interaction.channel.name} (msg {msg.id})")

    @app_commands.command(name="setup_roles", description="Post a reaction-role message in this channel.")
    @app_commands.describe(
        role="The role to assign when someone reacts",
        message="The message to display",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def setup_roles(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        message: str = "React to this message to get your role!",
    ):
        embed = discord.Embed(
            description=message,
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"React with any emoji to get the {role.name} role")

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        # Persist to config
        config = self.bot.config
        config["reaction_roles"]["messages"].append(
            {
                "channel_id": interaction.channel_id,
                "message_id": msg.id,
                "role_id": role.id,
            }
        )

        # Store the message jump URL for the welcome cog
        config["reaction_roles"]["roles_message_url"] = msg.jump_url
        self._save()

        log.info(f"Posted role message for {role.name} in #{interaction.channel.name} (msg {msg.id})")

    def _save(self):
        from bot import save_config
        save_config(self.bot.config)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
