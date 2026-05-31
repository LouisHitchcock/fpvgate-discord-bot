import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError

log = logging.getLogger("fpvgate-bot.instagram_feed")


class InstagramFeed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_post_ids: set[str] = set()
        self._client: Client | None = None
        self.check_feeds.start()

    def cog_unload(self):
        self.check_feeds.cancel()

    def _get_cfg(self) -> dict:
        return self.bot.config.get("instagram_feeds", {})

    def _ensure_client(self, cfg: dict) -> Client | None:
        if self._client is not None:
            return self._client

        username = cfg.get("ig_username") or self.bot.config.get("instagram_feeds", {}).get("ig_username")
        password = cfg.get("ig_password") or self.bot.config.get("instagram_feeds", {}).get("ig_password")
        if not username or not password:
            return None

        try:
            client = Client()
            client.login(username, password)
            self._client = client
            log.info("Logged into Instagram")
            return client
        except Exception as e:
            log.error(f"Instagram login failed: {e}")
            return None

    @tasks.loop(minutes=10)
    async def check_feeds(self):
        cfg = self._get_cfg()
        accounts = cfg.get("accounts", [])
        if not accounts:
            return

        client = self._ensure_client(cfg)
        if client is None:
            return

        try:
            client.get_timeline_feed()
        except LoginRequired:
            try:
                client.login(cfg.get("ig_username"), cfg.get("ig_password"))
                self._client = client
            except Exception as e:
                log.error(f"Instagram re-login failed: {e}")
                return
        except ClientError:
            pass

        for acct in accounts:
            try:
                await self._check_account(client, acct)
            except Exception:
                log.exception(f"Error checking account {acct.get('username')}")

    async def _check_account(self, client: Client, acct: dict):
        channel_id = acct.get("channel_id")
        username = acct.get("username")
        if not channel_id or not username:
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return

        try:
            user_id = client.user_id_from_username(username)
            medias = client.user_medias(user_id, amount=5)
        except Exception as e:
            log.error(f"Failed to fetch media for {username}: {e}")
            return

        for media in reversed(medias):
            post_id = str(media.id)
            if post_id in self._last_post_ids:
                continue

            await self._post_media(channel, media, acct)
            self._last_post_ids.add(post_id)

    async def _post_media(self, channel: discord.TextChannel, media, acct: dict):
        link = f"https://www.instagram.com/p/{media.code}/"
        caption = (media.caption_text or "")[:4096]
        timestamp = media.taken_at.replace(tzinfo=timezone.utc) if media.taken_at else datetime.now(timezone.utc)

        embed = discord.Embed(
            description=caption or None,
            url=link,
            color=discord.Color.magenta(),
            timestamp=timestamp,
        )
        embed.set_author(name=f"@{acct.get('username')}")
        embed.set_footer(text="Instagram")

        if media.media_type == 1 and media.thumbnail_url:
            embed.set_image(url=media.thumbnail_url)
        elif media.media_type == 8 and media.resources:
            embed.set_image(url=media.resources[0].thumbnail_url)
        elif media.media_type == 2 and media.thumbnail_url:
            embed.set_image(url=media.thumbnail_url)

        try:
            await channel.send(embed=embed)
            log.info(f"Posted Instagram media {media.id} to #{channel.name}")
        except Exception as e:
            log.error(f"Failed to post media {media.id}: {e}")

    @app_commands.command(
        name="add_instagram_account",
        description="Track an Instagram account's posts to a channel.",
    )
    @app_commands.describe(
        username="Instagram username to track (e.g. fpvgate)",
        channel="The channel to post updates to (default: current channel)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add_account(
        self,
        interaction: discord.Interaction,
        username: str,
        channel: discord.TextChannel = None,
    ):
        channel = channel or interaction.channel
        username = username.lstrip("@")

        cfg = self.bot.config.setdefault("instagram_feeds", {})
        cfg.setdefault("accounts", [])

        for acct in cfg["accounts"]:
            if acct["username"].lower() == username.lower() and acct["channel_id"] == channel.id:
                await interaction.response.send_message("This account is already tracked in this channel.", ephemeral=True)
                return

        cfg["accounts"].append({
            "username": username,
            "channel_id": channel.id,
        })

        from bot import save_config
        save_config(self.bot.config)

        embed = discord.Embed(
            title="Instagram Account Added",
            description=f"New posts from **@{username}** will appear in {channel.mention}.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log.info(f"Added Instagram account @{username} -> #{channel.name}")

    @app_commands.command(
        name="remove_instagram_account",
        description="Remove a tracked Instagram account.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_account(self, interaction: discord.Interaction):
        cfg = self.bot.config.get("instagram_feeds", {})
        accounts = cfg.get("accounts", [])
        if not accounts:
            await interaction.response.send_message("No accounts tracked.", ephemeral=True)
            return

        lines = []
        for i, acct in enumerate(accounts):
            ch = self.bot.get_channel(acct["channel_id"])
            ch_name = f"#{ch.name}" if ch else f"channel {acct['channel_id']}"
            lines.append(f"**{i}.** @{acct.get('username', '?')} -> {ch_name}")

        await interaction.response.send_message(
            "Reply with the number to remove:\n" + "\n".join(lines),
            ephemeral=True,
        )

        def check(m):
            return (
                m.author == interaction.user
                and m.channel == interaction.channel
                and m.content.isdigit()
            )

        try:
            msg = await self.bot.wait_for("message", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out.", ephemeral=True)
            return

        idx = int(msg.content)
        if idx < 0 or idx >= len(accounts):
            await interaction.followup.send("Invalid number.", ephemeral=True)
            return

        removed = accounts.pop(idx)
        from bot import save_config
        save_config(self.bot.config)

        await interaction.followup.send(
            f"Removed @{removed.get('username', '?')}.", ephemeral=True
        )
        log.info(f"Removed Instagram account @{removed.get('username', '?')}")

    @app_commands.command(
        name="set_instagram_login",
        description="Set the Instagram credentials for feed polling.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_login(
        self,
        interaction: discord.Interaction,
        username: str,
        password: str,
    ):
        cfg = self.bot.config.setdefault("instagram_feeds", {})
        cfg["ig_username"] = username
        cfg["ig_password"] = password

        # Reset client so it re-logs in next cycle
        self._client = None

        from bot import save_config
        save_config(self.bot.config)

        await interaction.response.send_message(
            "Instagram login credentials saved. The bot will log in on the next poll cycle.",
            ephemeral=True,
        )
        log.info("Instagram credentials updated")


async def setup(bot: commands.Bot):
    await bot.add_cog(InstagramFeed(bot))
