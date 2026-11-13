import random
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

XP_COOLDOWN = 60          # секунд между начислениями XP одному пользователю
XP_RANGE = (15, 25)
LEVEL_UP_COINS = 50       # монет за уровень (× номер уровня)


def xp_for_level(n: int) -> int:
    """Сколько XP нужно, чтобы перейти с уровня n на n+1."""
    return 5 * n * n + 50 * n + 100


def level_from_xp(xp: int) -> tuple[int, int, int]:
    """Возвращает (уровень, XP внутри уровня, XP до следующего)."""
    level = 0
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
    return level, xp, xp_for_level(level)


class Levels(commands.Cog):
    """XP за активность, уровни и роли за уровни."""

    def __init__(self, bot):
        self.bot = bot
        self._cooldowns: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild or not msg.content:
            return
        key = (msg.guild.id, msg.author.id)
        now = time.monotonic()
        if now - self._cooldowns.get(key, 0) < XP_COOLDOWN:
            return
        self._cooldowns[key] = now

        db = self.bot.db
        gain = random.randint(*XP_RANGE)
        await db.execute(
            "INSERT INTO levels(guild_id,user_id,xp) VALUES(?,?,?) "
            "ON CONFLICT(guild_id,user_id) DO UPDATE SET xp=xp+?",
            msg.guild.id, msg.author.id, gain, gain)
        row = await db.fetchone("SELECT xp FROM levels WHERE guild_id=? AND user_id=?",
                                msg.guild.id, msg.author.id)
        new_level = level_from_xp(row["xp"])[0]
        old_level = level_from_xp(row["xp"] - gain)[0]
        if new_level > old_level:
            await db.change_balance(msg.guild.id, msg.author.id, LEVEL_UP_COINS * new_level)
            await self.apply_roles(msg.author, new_level)
            try:
                await msg.channel.send(
                    f"🎉 {msg.author.mention} достиг **{new_level}** уровня! "
                    f"+{LEVEL_UP_COINS * new_level} 🪙")
            except discord.HTTPException:
                pass

    async def apply_roles(self, member: discord.Member, level: int):
        rows = await self.bot.db.fetchall(
            "SELECT role_id FROM level_roles WHERE guild_id=? AND level<=?", member.guild.id, level)
        roles = [r for row in rows
                 if (r := member.guild.get_role(row["role_id"])) and r not in member.roles]
        if roles:
            try:
                await member.add_roles(*roles, reason="level roles")
            except discord.HTTPException:
                pass

    @app_commands.command(name="rank", description="Твой уровень и XP")
    @app_commands.guild_only()
    async def rank(self, inter: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or inter.user
        row = await self.bot.db.fetchone(
            "SELECT xp FROM levels WHERE guild_id=? AND user_id=?", inter.guild_id, member.id)
        xp = row["xp"] if row else 0
        level, cur, need = level_from_xp(xp)
        pos = await self.bot.db.fetchone(
            "SELECT COUNT(*)+1 AS p FROM levels WHERE guild_id=? AND xp>?", inter.guild_id, xp)
        filled = int(10 * cur / need)
        bar = "█" * filled + "░" * (10 - filled)
        e = discord.Embed(title=member.display_name, color=discord.Color.blurple())
        e.add_field(name="Уровень", value=str(level))
        e.add_field(name="Место", value=f"#{pos['p']}")
        e.add_field(name="XP", value=f"{bar} {cur}/{need}", inline=False)
        await inter.response.send_message(embed=e)

    @app_commands.command(name="leaderboard", description="Топ-10 по XP")
    @app_commands.guild_only()
    async def leaderboard(self, inter: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT user_id,xp FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT 10", inter.guild_id)
        lines = [f"**{i}.** <@{r['user_id']}> — ур. {level_from_xp(r['xp'])[0]} ({r['xp']} XP)"
                 for i, r in enumerate(rows, 1)]
        await inter.response.send_message("\n".join(lines) or "Пока никого в рейтинге.",
                                          allowed_mentions=discord.AllowedMentions.none())

    # ---------- роли за уровни ----------
    levelrole = app_commands.Group(
        name="levelrole", description="Роли за уровни", guild_only=True,
        default_permissions=discord.Permissions(manage_roles=True))

    @levelrole.command(name="add", description="Выдавать роль при достижении уровня")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def levelrole_add(self, inter: discord.Interaction,
                            level: app_commands.Range[int, 1, 200], role: discord.Role):
        await self.bot.db.execute(
            "INSERT INTO level_roles(guild_id,level,role_id) VALUES(?,?,?) "
            "ON CONFLICT(guild_id,level) DO UPDATE SET role_id=excluded.role_id",
            inter.guild_id, level, role.id)
        await inter.response.send_message(f"✅ Уровень {level} → {role.mention}", ephemeral=True)

    @levelrole.command(name="remove", description="Убрать роль за уровень")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def levelrole_remove(self, inter: discord.Interaction, level: app_commands.Range[int, 1, 200]):
        await self.bot.db.execute(
            "DELETE FROM level_roles WHERE guild_id=? AND level=?", inter.guild_id, level)
        await inter.response.send_message(f"✅ Роль за уровень {level} убрана.", ephemeral=True)

    @levelrole.command(name="list", description="Список ролей за уровни")
    async def levelrole_list(self, inter: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT level,role_id FROM level_roles WHERE guild_id=? ORDER BY level", inter.guild_id)
        text = "\n".join(f"Уровень {r['level']} → <@&{r['role_id']}>" for r in rows)
        await inter.response.send_message(text or "Роли за уровни не настроены.", ephemeral=True,
                                          allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Levels(bot))
