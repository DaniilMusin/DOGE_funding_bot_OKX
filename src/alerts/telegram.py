import asyncio
import structlog
import os
from telegram import Bot, constants

log = structlog.get_logger()

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")

class Telegram:
    def __init__(self):
        self._bot: Bot | None = None
        if TG_TOKEN and TG_CHAT:
            self._bot = Bot(TG_TOKEN)

    async def send(self, text: str):
        if not self._bot:
            return
        try:
            await self._bot.send_message(
                TG_CHAT, text[:4000], parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            log.warning("TG_SEND_FAIL", err=str(e))

tg = Telegram()
