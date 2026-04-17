import logging

import discord
from discord import app_commands
from discord.ext import commands
from deep_translator import GoogleTranslator

log = logging.getLogger("fpvgate-bot.translate")

# Regional indicator symbols occupy U+1F1E6 (A) through U+1F1FF (Z).
# Two of these combined form a country flag whose letters are the
# ISO 3166-1 alpha-2 country code (e.g. 🇫🇷 => FR).
_REGIONAL_INDICATOR_BASE = 0x1F1E6

# ISO 3166-1 alpha-2 country code -> Google Translate language code.
# For multilingual countries, the most widely used / most likely
# translation target is chosen. Territories fall back to the language
# of their parent country. Unsupported-by-Google languages are mapped
# to the nearest supported one (e.g. Greenlandic -> Danish).
COUNTRY_TO_LANG = {
    # ---- Africa ----
    "DZ": "ar", "AO": "pt", "BJ": "fr", "BW": "en", "BF": "fr",
    "BI": "fr", "CM": "fr", "CV": "pt", "CF": "fr", "TD": "fr",
    "KM": "ar", "CG": "fr", "CD": "fr", "CI": "fr", "DJ": "fr",
    "EG": "ar", "GQ": "es", "ER": "ti", "SZ": "en", "ET": "am",
    "GA": "fr", "GM": "en", "GH": "en", "GN": "fr", "GW": "pt",
    "KE": "sw", "LS": "en", "LR": "en", "LY": "ar", "MG": "mg",
    "MW": "en", "ML": "fr", "MR": "ar", "MU": "en", "MA": "ar",
    "MZ": "pt", "NA": "en", "NE": "fr", "NG": "en", "RW": "rw",
    "ST": "pt", "SN": "fr", "SC": "fr", "SL": "en", "SO": "so",
    "ZA": "af", "SS": "en", "SD": "ar", "TZ": "sw", "TG": "fr",
    "TN": "ar", "UG": "en", "EH": "ar", "ZM": "en", "ZW": "en",
    "SH": "en",

    # ---- Americas ----
    "AG": "en", "AR": "es", "BS": "en", "BB": "en", "BZ": "en",
    "BO": "es", "BR": "pt", "CA": "en", "CL": "es", "CO": "es",
    "CR": "es", "CU": "es", "DM": "en", "DO": "es", "EC": "es",
    "SV": "es", "GD": "en", "GT": "es", "GY": "en", "HT": "ht",
    "HN": "es", "JM": "en", "MX": "es", "NI": "es", "PA": "es",
    "PY": "es", "PE": "es", "KN": "en", "LC": "en", "VC": "en",
    "SR": "nl", "TT": "en", "US": "en", "UY": "es", "VE": "es",
    # Territories
    "AI": "en", "AW": "nl", "BM": "en", "BQ": "nl", "BV": "no",
    "IO": "en", "VG": "en", "KY": "en", "CW": "nl", "FK": "en",
    "GF": "fr", "GL": "da", "GP": "fr", "MQ": "fr", "MS": "en",
    "PR": "es", "BL": "fr", "MF": "fr", "PM": "fr", "SX": "nl",
    "GS": "en", "TC": "en", "VI": "en", "UM": "en",

    # ---- Asia ----
    "AF": "ps", "AM": "hy", "AZ": "az", "BH": "ar", "BD": "bn",
    "BT": "en", "BN": "ms", "KH": "km", "CN": "zh-CN", "CY": "el",
    "GE": "ka", "HK": "zh-TW", "IN": "hi", "ID": "id", "IR": "fa",
    "IQ": "ar", "IL": "iw", "JP": "ja", "JO": "ar", "KZ": "kk",
    "KW": "ar", "KG": "ky", "LA": "lo", "LB": "ar", "MO": "zh-TW",
    "MY": "ms", "MV": "en", "MN": "mn", "MM": "my", "NP": "ne",
    "KP": "ko", "OM": "ar", "PK": "ur", "PS": "ar", "PH": "tl",
    "QA": "ar", "SA": "ar", "SG": "en", "KR": "ko", "LK": "si",
    "SY": "ar", "TW": "zh-TW", "TJ": "tg", "TH": "th", "TL": "pt",
    "TR": "tr", "TM": "tk", "AE": "ar", "UZ": "uz", "VN": "vi",
    "YE": "ar",

    # ---- Europe ----
    "AL": "sq", "AD": "ca", "AT": "de", "BY": "be", "BE": "nl",
    "BA": "bs", "BG": "bg", "HR": "hr", "CZ": "cs", "DK": "da",
    "EE": "et", "FO": "da", "FI": "fi", "FR": "fr", "DE": "de",
    "GI": "en", "GR": "el", "GG": "en", "HU": "hu", "IS": "is",
    "IE": "en", "IM": "en", "IT": "it", "JE": "en", "XK": "sq",
    "LV": "lv", "LI": "de", "LT": "lt", "LU": "fr", "MT": "mt",
    "MD": "ro", "MC": "fr", "ME": "sr", "NL": "nl", "MK": "mk",
    "NO": "no", "PL": "pl", "PT": "pt", "RO": "ro", "RU": "ru",
    "SM": "it", "RS": "sr", "SK": "sk", "SI": "sl", "ES": "es",
    "SE": "sv", "CH": "de", "UA": "uk", "GB": "en", "VA": "it",
    "AX": "sv", "SJ": "no",

    # ---- Oceania ----
    "AU": "en", "FJ": "en", "KI": "en", "MH": "en", "FM": "en",
    "NR": "en", "NZ": "en", "PW": "en", "PG": "en", "WS": "sm",
    "SB": "en", "TO": "en", "TV": "en", "VU": "en",
    # Territories
    "AS": "en", "CX": "en", "CC": "en", "CK": "en", "TF": "fr",
    "PF": "fr", "GU": "en", "NC": "fr", "NU": "en", "NF": "en",
    "MP": "en", "PN": "en", "TK": "en", "WF": "fr", "YT": "fr",
    "RE": "fr",

    # ---- Other ----
    "AQ": "en",
}


def _tag_flag(subdivision: str, with_base: bool = True) -> str:
    """Build a subdivision flag emoji from a tag code like 'gbeng'."""
    tags = "".join(chr(0xE0000 + ord(c)) for c in subdivision)
    cancel = "\U000E007F"
    return (("\U0001F3F4" if with_base else "") + tags + cancel)


# Tag-sequence subdivision flags. We register both forms (with and without
# the U+1F3F4 waving-black-flag base) because Discord payloads have been
# observed in both variants historically.
SUBDIVISION_FLAGS = {
    _tag_flag("gbeng"): "en",                 # England
    _tag_flag("gbsct"): "en",                 # Scotland
    _tag_flag("gbwls"): "cy",                 # Wales (Welsh)
    _tag_flag("gbeng", with_base=False): "en",
    _tag_flag("gbsct", with_base=False): "en",
    _tag_flag("gbwls", with_base=False): "cy",
}


def flag_to_lang(emoji: str) -> str | None:
    """Return a Google Translate language code for a flag emoji, or None."""
    # Subdivision (tag-sequence) flags first.
    if emoji in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[emoji]

    # Regional-indicator country flags are exactly two code points.
    if len(emoji) == 2:
        code = ""
        for ch in emoji:
            cp = ord(ch)
            if not (0x1F1E6 <= cp <= 0x1F1FF):
                return None
            code += chr(cp - _REGIONAL_INDICATOR_BASE + ord("A"))
        return COUNTRY_TO_LANG.get(code)

    return None


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
        target_lang = flag_to_lang(emoji)
        if target_lang is None:
            log.info(f"Emoji {repr(emoji)} not recognised as a flag, ignoring.")
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
            log.warning(f"Message {payload.message_id} not found")
            return
        except discord.Forbidden:
            log.error(f"Missing permissions to fetch message in channel {payload.channel_id}")
            return
        except Exception as e:
            log.error(f"Failed to fetch message: {e}")
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

        try:
            await message.reply(embed=embed, mention_author=False)
        except discord.Forbidden:
            log.error(f"Missing permission to reply in channel {payload.channel_id}")
            return
        except Exception as e:
            log.error(f"Failed to send translation reply: {e}")
            return
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
