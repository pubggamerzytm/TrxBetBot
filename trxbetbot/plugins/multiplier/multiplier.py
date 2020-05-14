from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


class Multiplier(TrxBetBotPlugin):

    INFO_FILE = "info.md"

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        info = self.get_resource(self.INFO_FILE)
        info.replace("{{multibet}}", )
        info.replace("{{multiwin}}", )

        update.message.reply_text(
            text=info,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True)
