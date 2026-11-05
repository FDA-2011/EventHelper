import logging

from vkbottle import BuiltinStateDispenser
from vkbottle.bot import Bot, BotLabeler

from config import VK_BOT_TOKEN
from seed import seed_if_empty
from handlers import registration, content, community

logging.basicConfig(level=logging.INFO)


def main():
    if not VK_BOT_TOKEN:
        raise RuntimeError("VK_BOT_TOKEN не задан. Заполните файл .env по примеру .env.example")

    seed_if_empty()
    bot = Bot(token=VK_BOT_TOKEN)
    bot.state_dispenser = BuiltinStateDispenser()

    labeler = BotLabeler()
    labeler.load(registration.router)
    labeler.load(content.router)
    labeler.load(community.router)
    bot.labeler = labeler
    bot.run_forever()


if __name__ == "__main__":
    main()
