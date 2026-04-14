import logging

import discord
from discord import app_commands
from discord.ext import commands
from deep_translator import GoogleTranslator

log = logging.getLogger("fpvgate-bot.translate")

# Maps flag emoji to language codes (ISO 639-1)
FLAG_TO_LANG = {
    "\U0001F1FA\U0001F1F8": "en",       # US
    "\U0001F1EC\U0001F1E7": "en",       # GB
    "\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F": "en",  # England
    "\U0001F1EB\U0001F1F7": "fr",       # France
    "\U0001F1EA\U0001F1F8": "es",       # Spain
    "\U0001F1E9\U0001F1EA": "de",       # Germany
    "\U0001F1EE\U0001F1F9": "it",       # Italy
    "\U0001F1F5\U0001F1F9": "pt",       # Portugal
    "\U0001F1E7\U0001F1F7": "pt",       # Brazil
    "\U0001F1F7\U0001F1FA": "ru",       # Russia
    "\U0001F1EF\U0001F1F5": "ja",       # Japan
    "\U0001F1F0\U0001F1F7": "ko",       # South Korea
    "\U0001F1E8\U0001F1F3": "zh-CN",    # China
    "\U0001F1F3\U0001F1F1": "nl",       # Netherlands
    "\U0001F1F5\U0001F1F1": "pl",       # Poland
    "\U0001F1F8\U0001F1EA": "sv",       # Sweden
    "\U0001F1E8\U0001F1FF": "cs",       # Czech Republic
    "\U0001F1F9\U0001F1F7": "tr",       # Turkey
    "\U0001F1FA\U0001F1E6": "uk",       # Ukraine
}


class Translate(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        cfg = self.bot.config.get("translate", {})
        if not cfg.get("enabled", True):
            return

        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        emoji = str(payload.emoji)
        log.info(f"Reaction received: {repr(emoji)} from user {payload.user_id}")
        target_lang = FLAG_TO_LANG.get(emoji)
        if target_lang is None:
            log.info(f"Emoji {repr(emoji)} not in flag map, ignoring.")
            return

        log.info(f"Translating to {target_lang}")

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)
            except Exception:
                log.error(f"Could not fetch channel {payload.channel_id}")
                return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        text = message.content.strip()
        if not text:
            return

        try:
            translated = GoogleTranslator(source="auto", target=target_lang).translate(text)
        except Exception as e:
            log.error(f"Translation failed: {e}")
            return

        if not translated or translated.lower() == text.lower():
            return

        lang_name = GoogleTranslator().get_supported_languages(as_dict=True)
        display_lang = next(
            (name for name, code in lang_name.items() if code == target_lang),
            target_lang,
        )

        embed = discord.Embed(
            description=translated,
            color=discord.Color.greyple(),
        )
        embed.set_footer(text=f"Translated to {display_lang.title()}")

        await message.reply(embed=embed, mention_author=False)
        log.info(f"Translated message {message.id} to {target_lang}")

    @app_commands.command(name="translate", description="Translate text to a given language.")
    @app_commands.describe(
        text="The text to translate",
        to="Target language code (e.g. en, fr, es, de)",
    )
    async def translate_cmd(self, interaction: discord.Interaction, text: str, to: str = "en"):
        try:
            translated = GoogleTranslator(source="auto", target=to).translate(text)
        except Exception as e:
            await interaction.response.send_message(f"Translation error: {e}", ephemeral=True)
            return

        embed = discord.Embed(description=translated, color=discord.Color.greyple())
        embed.set_footer(text=f"Translated to {to}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="toggle_translate", description="Enable or disable the auto-translate reactions.")
    @app_commands.checks.has_permissions(administrator=True)
    async def toggle_translate(self, interaction: discord.Interaction, enabled: bool):
        self.bot.config.setdefault("translate", {})["enabled"] = enabled
        from bot import save_config
        save_config(self.bot.config)
        state = "enabled" if enabled else "disabled"
        await interaction.response.send_message(f"Translation reactions {state}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Translate(bot))
