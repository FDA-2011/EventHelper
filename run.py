import logging

from vkbottle import BuiltinStateDispenser
from vkbottle.bot import Bot, BotLabeler

from config import VK_BOT_TOKEN
from seed import seed_if_empty
from handlers import registration, content, community
from vkbottle.dispatch.dispenser import BuiltinStateDispenser

# DEBUG — чтобы видеть в консоли реальные ошибки из хендлеров
logging.basicConfig(level=logging.DEBUG)

seed_if_empty()

bot = Bot(token=VK_BOT_TOKEN)
bot.state_dispenser = BuiltinStateDispenser()   # ← ключевая строка

main_labeler = BotLabeler()
main_labeler.load(registration.router)
main_labeler.load(content.router)
main_labeler.load(community.router)
bot.labeler = main_labeler


if __name__ == "__main__":
    bot.run_forever()