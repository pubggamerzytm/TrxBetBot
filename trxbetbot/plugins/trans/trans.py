import trxbetbot.emoji as emo

from telegram import ParseMode, Chat
from trxbetbot.plugin import TrxBetBotPlugin


# TODO: Get number of incoming & outgoing & and all transactions
class Trans(TrxBetBotPlugin):

    URL = "https://tronscan.org/#/address/"

    @TrxBetBotPlugin.owner
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if update.effective_chat.type != Chat.PRIVATE:
            msg = f"{emo.ERROR} You can execute this command only in a private chat with the bot"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # TODO: Find way to get all transactions
