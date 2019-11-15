import threading
import trxbetbot.emoji as emo

from trxbetbot.plugin import TrxBetBotPlugin


class Shutdown(TrxBetBotPlugin):

    @TrxBetBotPlugin.owner
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        msg = f"{emo.GOODBYE} Shutting down..."
        update.message.reply_text(msg)

        threading.Thread(target=self._shutdown_thread).start()

    # TODO: Remove access to protected variable
    def _shutdown_thread(self):
        self._tgb.updater.stop()
        self._tgb.updater.is_idle = False
