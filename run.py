import logging
from bot_instance import bot
from seed import seed_if_empty
from handlers import registration, content, community

logging.basicConfig(level=logging.DEBUG)
seed_if_empty()

bot.labeler.load(registration.router)
bot.labeler.load(content.router)
bot.labeler.load(community.router)

if __name__ == "__main__":
    print("🚀 Бот запускается...")
    bot.run()