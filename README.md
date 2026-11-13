# Discord-бот: модерация + комьюнити + экономика (MVP)

Python 3.10+, discord.py 2.x, SQLite (aiosqlite).

## Запуск
1. https://discord.com/developers/applications → New Application → Bot → скопируй токен.
2. В разделе Bot включи **Privileged Intents**: *Server Members Intent* и *Message Content Intent*.
3. Пригласи бота: OAuth2 → URL Generator → scopes `bot` + `applications.commands`,
   права: Manage Messages, Manage Roles, Read Message History, Send Messages, Embed Links, View Channels.
4. Роль бота на сервере должна стоять **выше** выдаваемых ролей (autorole, верификация, роли за уровни).
5. ```bash
   pip install -r requirements.txt
   cp .env.example .env   # впиши DISCORD_TOKEN (и DEV_GUILD_ID для теста)
   python main.py
   ```

## Команды
| Блок | Команды |
|---|---|
| Чистка | `/purge count author minutes regex attachments`, `/autoclean add/remove/list` |
| Логи | `/logchannel` (удаления, правки, вход/выход, баны, массовые удаления) |
| Комьюнити | `/setup welcome`, `/setup farewell`, `/setup autorole`, `/setup verify` |
| Уровни | `/rank`, `/leaderboard`, `/levelrole add/remove/list` |
| Экономика | `/balance`, `/daily`, `/work`, `/give`, `/top` |
| Игры | `/coinflip`, `/slots`, `/dice` |

Плейсхолдеры приветствий: `{user}` `{name}` `{server}` `{count}`.

## Заметки
- `/purge count` — сколько последних сообщений **просмотреть**, а не сколько удалить.
- Закреплённые сообщения чистка не трогает.
- Discord удаляет пачкой только сообщения младше 14 дней; старые удаляются по одному (медленно).
- Что не сделано и что дальше — в `ДОЛГ.md`.
