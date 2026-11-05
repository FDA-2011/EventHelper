from vkbottle.bot import Bot
from vkbottle.dispatch.dispenser.builtin import BuiltinStateDispenser

from config import VK_BOT_TOKEN

bot = Bot(token=VK_BOT_TOKEN)

# Явно гарантируем, что labeler и bot используют один и тот же диспетчер состояний
bot.state_dispenser = bot.state_dispenser or BuiltinStateDispenser()
bot.labeler.state_dispenser = bot.state_dispenser