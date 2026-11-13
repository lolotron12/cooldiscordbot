from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DEFAULT_WELCOME = "👋 Добро пожаловать, {user}! Ты участник №{count} на {server}."
DEFAULT_FAREWELL = "😢 {name} покинул(а) {server}."


def fmt(template: str, member: discord.Member) -> str:
    return (template.replace("{user}", member.mention)
            .replace("{name}", member.display_name)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count)))


class VerifyView(discord.ui.View):
    """Постоянная кнопка верификации (работает и после перезапуска бота)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Пройти верификацию", emoji="✅",
                       style=discord.ButtonStyle.success, custom_id="verify:button")
    async def verify(self, inter: discord.Interaction, button: discord.ui.Button):
        db = inter.client.db
        rid = await db.get(inter.guild_id, "verify_role")
        role = inter.guild.get_role(int(rid)) if rid else None
        if not role:
            return await inter.response.send_message("Верификация не настроена.", ephemeral=True)
        if role in inter.user.roles:
            return await inter.response.send_message("Ты уже верифицирован ✅", ephemeral=True)
        try:
            await inter.user.add_roles(role, reason="verification")
            uid = await db.get(inter.guild_id, "unverified_role")
            unverified = inter.guild.get_role(int(uid)) if uid else None
            if unverified and unverified in inter.user.roles:
                await inter.user.remove_roles(unverified, reason="verification")
        except discord.Forbidden:
            return await inter.response.send_message(
                "У бота нет прав выдать роль (роль бота должна быть выше).", ephemeral=True)
        await inter.response.send_message("Готово! Добро пожаловать 🎉", ephemeral=True)


class Welcome(commands.Cog):
    """Приветствия, прощания, autorole, верификация."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(VerifyView())

    async def _announce(self, member, channel_key, msg_key, default):
        db = self.bot.db
        cid = await db.get(member.guild.id, channel_key)
        channel = member.guild.get_channel(int(cid)) if cid else None
        if not channel:
            return
        template = await db.get(member.guild.id, msg_key, default)
        try:
            await channel.send(fmt(template, member))
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        db = self.bot.db
        for key in ("autorole", "unverified_role"):
            rid = await db.get(member.guild.id, key)
            role = member.guild.get_role(int(rid)) if rid else None
            if role:
                try:
                    await member.add_roles(role, reason=f"auto: {key}")
                except discord.HTTPException:
                    pass
        if not member.bot:
            await self._announce(member, "welcome_channel", "welcome_msg", DEFAULT_WELCOME)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member.bot:
            await self._announce(member, "farewell_channel", "farewell_msg", DEFAULT_FAREWELL)

    # ---------- /setup ----------
    setup = app_commands.Group(
        name="setup", description="Настройка приветствий, ролей и верификации",
        guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    @setup.command(name="welcome", description="Канал и текст приветствия ({user} {name} {server} {count})")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_welcome(self, inter: discord.Interaction,
                            channel: Optional[discord.TextChannel] = None, message: Optional[str] = None):
        await self.bot.db.set(inter.guild_id, "welcome_channel", channel.id if channel else None)
        if message:
            await self.bot.db.set(inter.guild_id, "welcome_msg", message)
        await inter.response.send_message(
            f"✅ Приветствия → {channel.mention}" if channel else "✅ Приветствия выключены.", ephemeral=True)

    @setup.command(name="farewell", description="Канал и текст прощания")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_farewell(self, inter: discord.Interaction,
                             channel: Optional[discord.TextChannel] = None, message: Optional[str] = None):
        await self.bot.db.set(inter.guild_id, "farewell_channel", channel.id if channel else None)
        if message:
            await self.bot.db.set(inter.guild_id, "farewell_msg", message)
        await inter.response.send_message(
            f"✅ Прощания → {channel.mention}" if channel else "✅ Прощания выключены.", ephemeral=True)

    @setup.command(name="autorole", description="Роль новичкам при входе (без параметра — выключить)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_autorole(self, inter: discord.Interaction, role: Optional[discord.Role] = None):
        await self.bot.db.set(inter.guild_id, "autorole", role.id if role else None)
        await inter.response.send_message(
            f"✅ Autorole: {role.mention}" if role else "✅ Autorole выключен.", ephemeral=True)

    @setup.command(name="verify", description="Опубликовать сообщение с кнопкой верификации")
    @app_commands.describe(channel="Куда опубликовать", role="Роль после верификации",
                           unverified_role="Роль «непроверенного» (выдаётся при входе, снимается после)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_verify(self, inter: discord.Interaction, channel: discord.TextChannel,
                           role: discord.Role, unverified_role: Optional[discord.Role] = None):
        await self.bot.db.set(inter.guild_id, "verify_role", role.id)
        await self.bot.db.set(inter.guild_id, "unverified_role", unverified_role.id if unverified_role else None)
        embed = discord.Embed(title="Верификация",
                              description="Нажми кнопку ниже, чтобы получить доступ к серверу.",
                              color=discord.Color.green())
        await channel.send(embed=embed, view=VerifyView())
        await inter.response.send_message(f"✅ Верификация опубликована в {channel.mention}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Welcome(bot))
