from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


def trunc(s: str, n: int = 1000) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class Logs(commands.Cog):
    """Логирование событий сервера в выбранный канал."""

    def __init__(self, bot):
        self.bot = bot

    async def send(self, guild: discord.Guild, embed: discord.Embed):
        cid = await self.bot.db.get(guild.id, "log_channel")
        channel = guild.get_channel(int(cid)) if cid else None
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    def embed(self, title: str, color: discord.Color) -> discord.Embed:
        return discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())

    @app_commands.command(name="logchannel", description="Канал для логов (без параметра — выключить)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def logchannel(self, inter: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await self.bot.db.set(inter.guild_id, "log_channel", channel.id if channel else None)
        await inter.response.send_message(
            f"✅ Логи → {channel.mention}" if channel else "✅ Логирование выключено.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, m: discord.Message):
        if not m.guild or m.author.bot:
            return
        e = self.embed("🗑 Сообщение удалено", discord.Color.red())
        e.add_field(name="Автор", value=f"{m.author.mention} ({m.author})")
        e.add_field(name="Канал", value=m.channel.mention)
        if m.content:
            e.add_field(name="Текст", value=trunc(m.content), inline=False)
        if m.attachments:
            e.add_field(name="Вложения", value=trunc("\n".join(a.filename for a in m.attachments)), inline=False)
        await self.send(m.guild, e)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if not guild:
            return
        e = self.embed("🧹 Массовое удаление", discord.Color.dark_red())
        e.add_field(name="Канал", value=f"<#{payload.channel_id}>")
        e.add_field(name="Сообщений", value=str(len(payload.message_ids)))
        await self.send(guild, e)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot or before.content == after.content:
            return
        e = self.embed("✏️ Сообщение изменено", discord.Color.orange())
        e.add_field(name="Автор", value=f"{after.author.mention} ({after.author})")
        e.add_field(name="Канал", value=after.channel.mention)
        e.add_field(name="Было", value=trunc(before.content) or "—", inline=False)
        e.add_field(name="Стало", value=trunc(after.content) or "—", inline=False)
        e.add_field(name="Ссылка", value=f"[перейти]({after.jump_url})")
        await self.send(after.guild, e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        e = self.embed("📥 Участник зашёл", discord.Color.green())
        e.add_field(name="Участник", value=f"{member.mention} ({member})")
        e.add_field(name="Аккаунт создан", value=discord.utils.format_dt(member.created_at, "R"))
        await self.send(member.guild, e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        e = self.embed("📤 Участник вышел", discord.Color.dark_grey())
        e.add_field(name="Участник", value=f"{member.mention} ({member})")
        await self.send(member.guild, e)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        e = self.embed("🔨 Бан", discord.Color.dark_red())
        e.add_field(name="Пользователь", value=f"{user.mention} ({user})")
        await self.send(guild, e)


async def setup(bot):
    await bot.add_cog(Logs(bot))
