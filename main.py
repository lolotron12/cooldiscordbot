import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from db import DB

load_dotenv()
logging.basicConfig(level=logging.INFO)

COGS = ["cogs.purge", "cogs.logs", "cogs.welcome", "cogs.levels", "cogs.economy"]


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # regex-чистка, XP за сообщения
        intents.members = True          # приветствия, autorole, прощания
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.db = DB(os.getenv("DB_PATH", "bot.db"))

    async def setup_hook(self):
        await self.db.init()
        for cog in COGS:
            await self.load_extension(cog)
        dev_guild = os.getenv("DEV_GUILD_ID")
        if dev_guild:  # мгновенная синхронизация команд на тестовом сервере
            guild = discord.Object(int(dev_guild))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        logging.info("Logged in as %s (%s)", self.user, self.user.id)


bot = Bot()


@bot.tree.error
async def on_app_command_error(inter: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, (app_commands.MissingPermissions, app_commands.BotMissingPermissions)):
        text = "⛔ Не хватает прав (у тебя или у бота)."
    elif isinstance(error, app_commands.CommandOnCooldown):
        text = f"⏳ Подожди {error.retry_after:.0f} сек."
    else:
        logging.exception("Command error", exc_info=error)
        text = "⚠️ Что-то пошло не так. Попробуй ещё раз."
    if inter.response.is_done():
        await inter.followup.send(text, ephemeral=True)
    else:
        await inter.response.send_message(text, ephemeral=True)


if __name__ == "__main__":
    bot.run(os.environ["DISCORD_TOKEN"])
