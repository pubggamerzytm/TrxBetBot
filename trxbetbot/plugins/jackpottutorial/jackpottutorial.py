from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


class Jackpottutorial(TrxBetBotPlugin):

    INFO_FILE = "info.md"

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        update.message.reply_text(
            text=self.get_resource(self.INFO_FILE),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True)
