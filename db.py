import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
    PRIMARY KEY (guild_id, key));
CREATE TABLE IF NOT EXISTS levels (
    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, xp INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id));
CREATE TABLE IF NOT EXISTS level_roles (
    guild_id INTEGER NOT NULL, level INTEGER NOT NULL, role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level));
CREATE TABLE IF NOT EXISTS economy (
    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
    last_daily INTEGER NOT NULL DEFAULT 0,
    last_work INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id));
CREATE TABLE IF NOT EXISTS autoclean (
    channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, max_age_min INTEGER NOT NULL);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def init(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def execute(self, sql: str, *args):
        cur = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cur

    async def fetchone(self, sql: str, *args):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchone()

    async def fetchall(self, sql: str, *args):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchall()

    # --- настройки сервера (key/value) ---
    async def get(self, guild_id: int, key: str, default=None):
        row = await self.fetchone(
            "SELECT value FROM settings WHERE guild_id=? AND key=?", guild_id, key)
        return row["value"] if row else default

    async def set(self, guild_id: int, key: str, value):
        if value is None:
            await self.execute("DELETE FROM settings WHERE guild_id=? AND key=?", guild_id, key)
            return
        await self.execute(
            "INSERT INTO settings(guild_id,key,value) VALUES(?,?,?) "
            "ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value",
            guild_id, key, str(value))

    # --- экономика ---
    async def change_balance(self, guild_id: int, user_id: int, delta: int):
        """Атомарно меняет баланс. Возвращает новый баланс или None, если не хватает монет."""
        await self.execute(
            "INSERT OR IGNORE INTO economy(guild_id,user_id) VALUES(?,?)", guild_id, user_id)
        cur = await self.execute(
            "UPDATE economy SET balance=balance+? "
            "WHERE guild_id=? AND user_id=? AND balance+?>=0",
            delta, guild_id, user_id, delta)
        if cur.rowcount == 0:
            return None
        row = await self.fetchone(
            "SELECT balance FROM economy WHERE guild_id=? AND user_id=?", guild_id, user_id)
        return row["balance"]

    async def balance(self, guild_id: int, user_id: int) -> int:
        row = await self.fetchone(
            "SELECT balance FROM economy WHERE guild_id=? AND user_id=?", guild_id, user_id)
        return row["balance"] if row else 0
