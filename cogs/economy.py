import random
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DAILY_REWARD, DAILY_CD = 100, 24 * 3600
WORK_REWARD, WORK_CD = (20, 80), 3600
MAX_BET = 10_000
SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣"]

Bet = app_commands.Range[int, 1, MAX_BET]


class Economy(commands.Cog):
    """Виртуальная валюта + мини-игры."""

    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def claim(self, gid: int, uid: int, col: str, cd: int, reward: int):
        """Атомарно выдаёт награду. None — успех, иначе время (epoch), когда снова доступно."""
        now = int(time.time())
        await self.db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id) VALUES(?,?)", gid, uid)
        cur = await self.db.execute(
            f"UPDATE economy SET {col}=?, balance=balance+? "
            f"WHERE guild_id=? AND user_id=? AND {col}<=?", now, reward, gid, uid, now - cd)
        if cur.rowcount:
            return None
        row = await self.db.fetchone(f"SELECT {col} AS t FROM economy WHERE guild_id=? AND user_id=?", gid, uid)
        return row["t"] + cd

    # ---------- экономика ----------
    @app_commands.command(name="balance", description="Баланс монет")
    @app_commands.guild_only()
    async def balance(self, inter: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or inter.user
        bal = await self.db.balance(inter.guild_id, member.id)
        await inter.response.send_message(f"🪙 Баланс {member.display_name}: **{bal}**")

    @app_commands.command(name="daily", description="Ежедневная награда")
    @app_commands.guild_only()
    async def daily(self, inter: discord.Interaction):
        ready = await self.claim(inter.guild_id, inter.user.id, "last_daily", DAILY_CD, DAILY_REWARD)
        if ready:
            return await inter.response.send_message(f"⏳ Награда будет доступна <t:{ready}:R>", ephemeral=True)
        await inter.response.send_message(f"🎁 Ты получил **{DAILY_REWARD}** 🪙")

    @app_commands.command(name="work", description="Подработать (раз в час)")
    @app_commands.guild_only()
    async def work(self, inter: discord.Interaction):
        reward = random.randint(*WORK_REWARD)
        ready = await self.claim(inter.guild_id, inter.user.id, "last_work", WORK_CD, reward)
        if ready:
            return await inter.response.send_message(f"⏳ Отдохни, снова на работу <t:{ready}:R>", ephemeral=True)
        await inter.response.send_message(f"💼 Ты заработал **{reward}** 🪙")

    @app_commands.command(name="give", description="Передать монеты")
    @app_commands.guild_only()
    async def give(self, inter: discord.Interaction, member: discord.Member,
                   amount: app_commands.Range[int, 1, 1_000_000]):
        if member.bot or member.id == inter.user.id:
            return await inter.response.send_message("❌ Нельзя передать монеты этому пользователю.", ephemeral=True)
        if await self.db.change_balance(inter.guild_id, inter.user.id, -amount) is None:
            return await inter.response.send_message("❌ Недостаточно монет.", ephemeral=True)
        await self.db.change_balance(inter.guild_id, member.id, amount)
        await inter.response.send_message(f"✅ {inter.user.mention} передал {member.mention} **{amount}** 🪙",
                                          allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="top", description="Самые богатые")
    @app_commands.guild_only()
    async def top(self, inter: discord.Interaction):
        rows = await self.db.fetchall(
            "SELECT user_id,balance FROM economy WHERE guild_id=? ORDER BY balance DESC LIMIT 10", inter.guild_id)
        lines = [f"**{i}.** <@{r['user_id']}> — {r['balance']} 🪙" for i, r in enumerate(rows, 1)]
        await inter.response.send_message("\n".join(lines) or "Пока пусто.",
                                          allowed_mentions=discord.AllowedMentions.none())

    # ---------- мини-игры: ставка списывается заранее, выигрыш зачисляется после ----------
    async def _stake(self, inter, bet: int) -> bool:
        if await self.db.change_balance(inter.guild_id, inter.user.id, -bet) is None:
            await inter.response.send_message("❌ Недостаточно монет для такой ставки.", ephemeral=True)
            return False
        return True

    async def _payout(self, inter, payout: int) -> int:
        if payout:
            return await self.db.change_balance(inter.guild_id, inter.user.id, payout)
        return await self.db.balance(inter.guild_id, inter.user.id)

    @app_commands.command(name="coinflip", description="Орёл или решка (выигрыш ×1.9)")
    @app_commands.choices(side=[app_commands.Choice(name="Орёл", value="heads"),
                                app_commands.Choice(name="Решка", value="tails")])
    @app_commands.guild_only()
    async def coinflip(self, inter: discord.Interaction, bet: Bet, side: app_commands.Choice[str]):
        if not await self._stake(inter, bet):
            return
        result = random.choice(["heads", "tails"])
        win = result == side.value
        bal = await self._payout(inter, int(bet * 1.9) if win else 0)
        name = "Орёл" if result == "heads" else "Решка"
        await inter.response.send_message(
            f"🪙 Выпало: **{name}** — " + (f"ты выиграл **{int(bet * 1.9) - bet}**!" if win else f"ты проиграл **{bet}**.")
            + f" Баланс: {bal}")

    @app_commands.command(name="slots", description="Слоты: 3 одинаковых ×10, 2 одинаковых — ставка возвращается")
    @app_commands.guild_only()
    async def slots(self, inter: discord.Interaction, bet: Bet):
        if not await self._stake(inter, bet):
            return
        reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        distinct = len(set(reels))
        payout = bet * 10 if distinct == 1 else bet if distinct == 2 else 0
        bal = await self._payout(inter, payout)
        verdict = ("🎰 ДЖЕКПОТ!" if distinct == 1 else "😐 Ставка возвращена." if distinct == 2 else "💸 Мимо.")
        await inter.response.send_message(f"| {' | '.join(reels)} |\n{verdict} Баланс: {bal}")

    @app_commands.command(name="dice", description="Бросок кубика против бота (ничья — проигрыш)")
    @app_commands.guild_only()
    async def dice(self, inter: discord.Interaction, bet: Bet):
        if not await self._stake(inter, bet):
            return
        you, bot_roll = random.randint(1, 6), random.randint(1, 6)
        win = you > bot_roll
        bal = await self._payout(inter, bet * 2 if win else 0)
        await inter.response.send_message(
            f"🎲 Ты: **{you}**, бот: **{bot_roll}** — " + ("победа!" if win else "поражение.") + f" Баланс: {bal}")


async def setup(bot):
    await bot.add_cog(Economy(bot))
