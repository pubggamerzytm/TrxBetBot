import logging
import trxbetbot.emoji as emo
import trxbetbot.utils as utl

from tronapi import Tron
from trxbetbot.trc20 import TRC20
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


# TODO: 24 hours Wins and Losses statistics UTC trading time
class Stats(TrxBetBotPlugin):

    MAX_DATA = 200

    @TrxBetBotPlugin.owner
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if update.effective_chat.type != Chat.PRIVATE:
            msg = f"{emo.ERROR} You can execute this command only in a private chat with the bot"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # TODO: Uncomment
        #address = self.get_tron().default_address["base58"]
        address = "TXRZqGMEXsGTX6AQtcSgYknos93hqw18P7"

        last_24_hours = datetime.utcnow() - timedelta(minutes=30)

        tg = Trongrid()

        tx_kwargs = dict()
        tx_kwargs["only_from"] = True
        tx_kwargs["limit"] = self.MAX_DATA
        tx_kwargs["min_timestamp"] = utl.linux_time(last_24_hours, millis=True)

        tx_to = tg.get_transactions(address, **tx_kwargs)
        data = tx_to["data"]

        while len(tx_to["data"]) == self.MAX_DATA:
            tx_kwargs["fingerprint"] = tx_to["meta"]["fingerprint"]
            tx_to = tg.get_transactions(address, **tx_kwargs)
            data.extend(tx_to["data"])
