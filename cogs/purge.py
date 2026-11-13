import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks


class Purge(commands.Cog):
    """Чистка чата по фильтрам + автоочистка каналов."""

    def __init__(self, bot):
        self.bot = bot
        self.autoclean_loop.start()

    def cog_unload(self):
        self.autoclean_loop.cancel()

    # ---------- /purge ----------
    @app_commands.command(name="purge", description="Удалить сообщения по фильтрам")
    @app_commands.describe(
        count="Сколько последних сообщений просмотреть (до 1000)",
        author="Только сообщения этого пользователя",
        minutes="Только за последние N минут",
        regex="Только сообщения, подходящие под regex (без учёта регистра)",
        attachments="Только сообщения с вложениями",
    )
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    @app_commands.guild_only()
    async def purge(
        self,
        inter: discord.Interaction,
        count: app_commands.Range[int, 1, 1000] = 100,
        author: Optional[discord.Member] = None,
        minutes: Optional[app_commands.Range[int, 1, 20160]] = None,
        regex: Optional[str] = None,
        attachments: Optional[bool] = None,
    ):
        pattern = None
        if regex:
            try:
                pattern = re.compile(regex, re.IGNORECASE)
            except re.error as e:
                return await inter.response.send_message(f"❌ Некорректный regex: `{e}`", ephemeral=True)

        await inter.response.defer(ephemeral=True)
        after = datetime.now(timezone.utc) - timedelta(minutes=minutes) if minutes else None

        def check(m: discord.Message) -> bool:
            if m.pinned:
                return False
            if author and m.author.id != author.id:
                return False
            if attachments and not m.attachments:
                return False
            if pattern and not pattern.search(m.content or ""):
                return False
            return True

        deleted = await inter.channel.purge(
            limit=count, check=check, after=after, oldest_first=False, bulk=True,
            reason=f"/purge by {inter.user}")
        await inter.followup.send(f"🧹 Удалено сообщений: **{len(deleted)}**", ephemeral=True)

    # ---------- /autoclean ----------
    autoclean = app_commands.Group(
        name="autoclean", description="Автоочистка старых сообщений в канале",
        guild_only=True, default_permissions=discord.Permissions(manage_messages=True))

    @autoclean.command(name="add", description="Включить автоочистку канала")
    @app_commands.describe(channel="Канал", max_age_minutes="Удалять сообщения старше N минут")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def autoclean_add(self, inter: discord.Interaction, channel: discord.TextChannel,
                            max_age_minutes: app_commands.Range[int, 5, 10080]):
        await self.bot.db.execute(
            "INSERT INTO autoclean(channel_id,guild_id,max_age_min) VALUES(?,?,?) "
            "ON CONFLICT(channel_id) DO UPDATE SET max_age_min=excluded.max_age_min",
            channel.id, inter.guild_id, max_age_minutes)
        await inter.response.send_message(
            f"✅ {channel.mention}: удаляю сообщения старше {max_age_minutes} мин "
            f"(закреплённые не трогаю).", ephemeral=True)

    @autoclean.command(name="remove", description="Выключить автоочистку канала")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def autoclean_remove(self, inter: discord.Interaction, channel: discord.TextChannel):
        await self.bot.db.execute("DELETE FROM autoclean WHERE channel_id=?", channel.id)
        await inter.response.send_message(f"✅ Автоочистка в {channel.mention} выключена.", ephemeral=True)

    @autoclean.command(name="list", description="Каналы с автоочисткой")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def autoclean_list(self, inter: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT channel_id,max_age_min FROM autoclean WHERE guild_id=?", inter.guild_id)
        text = "\n".join(f"<#{r['channel_id']}> — старше {r['max_age_min']} мин" for r in rows)
        await inter.response.send_message(text or "Автоочистка не настроена.", ephemeral=True)

    @tasks.loop(minutes=5)
    async def autoclean_loop(self):
        rows = await self.bot.db.fetchall("SELECT channel_id,max_age_min FROM autoclean")
        for r in rows:
            channel = self.bot.get_channel(r["channel_id"])
            if channel is None:
                continue
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=r["max_age_min"])
            try:
                await channel.purge(limit=200, before=cutoff, check=lambda m: not m.pinned,
                                    bulk=True, reason="autoclean")
            except discord.HTTPException:
                logging.exception("autoclean failed in %s", r["channel_id"])

    @autoclean_loop.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Purge(bot))
