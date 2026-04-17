import os
import json
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from logger import setup_logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

log = setup_logging()

VERSION = "1.0.0"

COGS = [
    "cogs.reaction_roles",
    "cogs.welcome",
    "cogs.translate",
]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


class FPVGateBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.reactions = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            description="FPVGate Discord Bot",
        )

        self.config = load_config()

    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded cog: {cog}")
            except Exception as e:
                log.error(f"Failed to load cog {cog}: {e}")

        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")


    async def on_message(self, message):
        await self.process_commands(message)


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN not set in .env file")

    bot = FPVGateBot()

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def sync(ctx: commands.Context):
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"Synced {len(synced)} commands to this server.")

    @bot.command()
    async def version(ctx: commands.Context):
        await ctx.send(f"FPVGate Bot v{VERSION}")

    bot.run(token)


if __name__ == "__main__":
    main()
