"""Post new uploads from the FPVGate Instagram account to a Discord channel.

Uses the official Instagram API with Instagram Login (graph.instagram.com), so
there is no password and no scraping. The account must be a Business or Creator
account, and the bot needs a long-lived access token with the
`instagram_business_basic` permission.

Setup:
  * Put the token in .env as IG_ACCESS_TOKEN (or use /instagram_set_token).
  * The bot posts to the channel set with /instagram_set_channel. If none is
    set, it uses a channel named like "socials".

Runtime state (refreshed token, seen post IDs, channel override) lives in
data/instagram_state.json. That file is gitignored, so deploys
(`git reset --hard`) don't wipe it.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger("fpvgate-bot.instagram_feed")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE_DIR, "data", "instagram_state.json")

GRAPH_URL = "https://graph.instagram.com"
MEDIA_FIELDS = (
    "id,caption,media_type,media_product_type,media_url,thumbnail_url,"
    "permalink,timestamp,username,children{media_type,media_url,thumbnail_url}"
)
REFRESH_EVERY = timedelta(days=7)  # long-lived tokens last 60 days
MAX_SEEN_IDS = 200
DEFAULT_CHANNEL_NAME = "socials"


class InstagramAPIError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class InstagramFeed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = self._load_state()
        self.session: aiohttp.ClientSession | None = None
        self.last_check: datetime | None = None
        self.last_error: str | None = None
        self._adopt_env_token()

        minutes = self._cfg().get("poll_minutes", 10)
        self.check_feed.change_interval(minutes=max(2, minutes))

    async def cog_load(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        if self._cfg().get("enabled", True):
            self.check_feed.start()

    async def cog_unload(self):
        self.check_feed.cancel()
        if self.session:
            await self.session.close()

    # ── config & state ───────────────────────────────────────────────

    def _cfg(self) -> dict:
        return self.bot.config.get("instagram", {})

    def _load_state(self) -> dict:
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception:
            log.exception("Could not read Instagram state file. Starting fresh.")
            return {}

    def _save_state(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)
        os.replace(tmp, STATE_PATH)

    def _adopt_env_token(self):
        """Use IG_ACCESS_TOKEN from .env if it's new. Otherwise keep the refreshed token in state."""
        env_token = os.getenv("IG_ACCESS_TOKEN", "").strip()
        if env_token and env_token != self.state.get("env_token_seed"):
            self._set_token(env_token)
            self.state["env_token_seed"] = env_token
            self._save_state()
            log.info("Using new Instagram token from IG_ACCESS_TOKEN")

    def _set_token(self, token: str):
        self.state["access_token"] = token
        self.state["token_set_at"] = datetime.now(timezone.utc).isoformat()
        self.state.pop("token_expires_at", None)

    # ── Instagram API ────────────────────────────────────────────────

    async def _get(self, path: str, **params) -> dict:
        params["access_token"] = self.state["access_token"]
        async with self.session.get(f"{GRAPH_URL}/{path}", params=params) as resp:
            data = await resp.json(content_type=None)
        if "error" in data:
            err = data["error"]
            raise InstagramAPIError(err.get("message", str(err)), err.get("code"))
        return data

    async def _maybe_refresh_token(self):
        set_at = datetime.fromisoformat(self.state["token_set_at"])
        if datetime.now(timezone.utc) - set_at < REFRESH_EVERY:
            return
        try:
            data = await self._get("refresh_access_token", grant_type="ig_refresh_token")
        except InstagramAPIError as e:
            log.warning(f"Instagram token refresh failed (will retry next cycle): {e}")
            return
        self._set_token(data["access_token"])
        expires_in = data.get("expires_in")
        if expires_in:
            self.state["token_expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            ).isoformat()
        self._save_state()
        log.info("Refreshed Instagram access token")

    async def _fetch_recent_media(self, limit: int = 10) -> list[dict]:
        data = await self._get("me/media", fields=MEDIA_FIELDS, limit=limit)
        return data.get("data", [])

    # ── Discord ──────────────────────────────────────────────────────

    async def _resolve_channel(self) -> discord.abc.Messageable | None:
        channel_id = self.state.get("channel_id") or self._cfg().get("channel_id")
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(int(channel_id))
                except discord.HTTPException:
                    log.error(f"Instagram channel {channel_id} not found")
                    return None
            return channel

        name = self._cfg().get("channel_name", DEFAULT_CHANNEL_NAME).lower()
        candidates = [c for g in self.bot.guilds for c in g.text_channels]
        exact = [c for c in candidates if c.name.lower() == name]
        fuzzy = [c for c in candidates if name in c.name.lower()]
        match = (exact or fuzzy or [None])[0]
        if match is None:
            log.warning(f"No channel named '{name}' found. Use /instagram_set_channel.")
        return match

    @staticmethod
    def _image_for(media: dict) -> str | None:
        item = media
        if media.get("media_type") == "CAROUSEL_ALBUM":
            children = media.get("children", {}).get("data", [])
            if children:
                item = children[0]
        if item.get("media_type") == "VIDEO":
            return item.get("thumbnail_url")
        return item.get("media_url") or item.get("thumbnail_url")

    def _build_embed(self, media: dict) -> discord.Embed:
        username = media.get("username", "instagram")
        is_reel = media.get("media_product_type") == "REELS"
        kind = "reel" if is_reel else "video" if media.get("media_type") == "VIDEO" else "post"

        caption = media.get("caption") or ""
        if len(caption) > 1000:
            caption = caption[:1000].rstrip() + "…"

        timestamp = None
        if media.get("timestamp"):
            # Instagram returns e.g. 2026-11-17T12:00:00+0000
            timestamp = datetime.strptime(media["timestamp"], "%Y-%m-%dT%H:%M:%S%z")

        embed = discord.Embed(
            title=f"New {kind} on Instagram",
            url=media.get("permalink"),
            description=caption or None,
            color=discord.Color.from_rgb(225, 48, 108),
            timestamp=timestamp,
        )
        embed.set_author(name=f"@{username}", url=f"https://www.instagram.com/{username}/")
        image = self._image_for(media)
        if image:
            embed.set_image(url=image)
        embed.set_footer(text="Instagram")
        return embed

    async def _post(self, channel, media: dict) -> bool:
        view = discord.ui.View()
        if media.get("permalink"):
            view.add_item(discord.ui.Button(label="View on Instagram", url=media["permalink"]))
        try:
            await channel.send(embed=self._build_embed(media), view=view)
            log.info(f"Posted Instagram media {media['id']} to #{getattr(channel, 'name', channel)}")
            return True
        except discord.HTTPException as e:
            log.error(f"Failed to post Instagram media {media['id']}: {e}")
            return False

    # ── polling ──────────────────────────────────────────────────────

    @tasks.loop(minutes=10)
    async def check_feed(self):
        if not self.state.get("access_token"):
            return
        try:
            await self._run_check()
            self.last_error = None
        except InstagramAPIError as e:
            self.last_error = str(e)
            if e.code == 190:
                log.error(f"Instagram token is invalid or expired. Set a new one with /instagram_set_token. ({e})")
            else:
                log.error(f"Instagram API error: {e}")
        except Exception as e:
            self.last_error = str(e)
            log.exception("Instagram feed check failed")
        finally:
            self.last_check = datetime.now(timezone.utc)

    @check_feed.before_loop
    async def _before_check(self):
        await self.bot.wait_until_ready()

    async def _run_check(self):
        await self._maybe_refresh_token()
        media = await self._fetch_recent_media()
        seen: list[str] = self.state.get("seen_ids", [])

        # First run: remember the posts that already exist so the channel isn't flooded.
        if not self.state.get("seeded"):
            self.state["seen_ids"] = [m["id"] for m in media]
            self.state["seeded"] = True
            self._save_state()
            log.info(f"Instagram feed seeded with {len(media)} existing posts")
            return

        new = [m for m in media if m["id"] not in seen]
        if not new:
            return

        channel = await self._resolve_channel()
        if channel is None:
            return

        for m in reversed(new):  # API returns newest first. Post oldest first.
            if await self._post(channel, m):
                seen.append(m["id"])
        self.state["seen_ids"] = seen[-MAX_SEEN_IDS:]
        self._save_state()

    # ── admin commands ───────────────────────────────────────────────

    @app_commands.command(name="instagram_set_channel", description="Choose the channel for new Instagram posts.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.state["channel_id"] = channel.id
        self._save_state()
        await interaction.response.send_message(
            f"New Instagram posts will go to {channel.mention}.", ephemeral=True
        )

    @app_commands.command(name="instagram_set_token", description="Set the Instagram API access token.")
    @app_commands.describe(token="Long-lived Instagram access token (from the Meta developer dashboard)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def set_token(self, interaction: discord.Interaction, token: str):
        await interaction.response.defer(ephemeral=True)
        old = self.state.get("access_token")
        self._set_token(token.strip())
        try:
            me = await self._get("me", fields="username")
        except InstagramAPIError as e:
            if old:
                self.state["access_token"] = old
            await interaction.followup.send(f"Token rejected by Instagram: {e}", ephemeral=True)
            return
        self._save_state()
        if not self.check_feed.is_running():
            self.check_feed.start()
        await interaction.followup.send(f"Token saved. Watching **@{me.get('username')}**.", ephemeral=True)
        log.info(f"Instagram token updated via command for @{me.get('username')}")

    @app_commands.command(name="instagram_status", description="Show the Instagram feed status.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        channel = await self._resolve_channel()

        def ts(iso: str | None) -> str:
            return f"<t:{int(datetime.fromisoformat(iso).timestamp())}:R>" if iso else "unknown"

        lines = [
            f"**Token:** {'set' if self.state.get('access_token') else 'not set'}",
            f"**Token refreshed:** {ts(self.state.get('token_set_at'))}",
            f"**Token expires:** {ts(self.state.get('token_expires_at'))}",
            f"**Channel:** {channel.mention if channel else 'not found'}",
            f"**Polling:** {'running' if self.check_feed.is_running() else 'stopped'}",
            f"**Last check:** {ts(self.last_check.isoformat()) if self.last_check else 'never'}",
            f"**Posts tracked:** {len(self.state.get('seen_ids', []))}",
        ]
        if self.last_error:
            lines.append(f"**Last error:** {self.last_error[:300]}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="instagram_post_latest", description="Post the latest Instagram upload now (for testing).")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def post_latest(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not self.state.get("access_token"):
            await interaction.followup.send("No token set. Use /instagram_set_token.", ephemeral=True)
            return
        channel = await self._resolve_channel()
        if channel is None:
            await interaction.followup.send("No socials channel found. Use /instagram_set_channel.", ephemeral=True)
            return
        try:
            media = await self._fetch_recent_media(limit=1)
        except InstagramAPIError as e:
            await interaction.followup.send(f"Instagram API error: {e}", ephemeral=True)
            return
        if not media:
            await interaction.followup.send("The account has no posts.", ephemeral=True)
            return
        ok = await self._post(channel, media[0])
        await interaction.followup.send(
            f"Posted to {channel.mention}." if ok else "Failed to post. Check the bot's permissions.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(InstagramFeed(bot))
