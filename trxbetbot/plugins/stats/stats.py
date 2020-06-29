import time
import trxbetbot.emoji as emo
import trxbetbot.utils as utl

from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


class Stats(TrxBetBotPlugin):

    MAX_DATA = 200
    DEF_TIME = 24

    @TrxBetBotPlugin.owner
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if update.effective_chat.type != Chat.PRIVATE:
            msg = f"{emo.ERROR} You can execute this command only in a private chat with the bot"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        addr_base58 = self.get_tron().default_address["base58"]
        addr_hex = self.get_tron().default_address["hex"]

        if len(args) > 0:
            try:
                float(args[0])
            except:
                msg = f"{emo.ERROR} Parameter needs to be number of hours"
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                return

            if float(args[0]) > 24:
                msg = f"{emo.ERROR} Max number of hours is 24"
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                return

        message = update.message.reply_text(f"{emo.WAIT} Wait...")

        h = self.DEF_TIME if len(args) == 0 else float(args[0])
        last_24_hours = datetime.utcnow() - timedelta(hours=h)

        tg = Trongrid()

        tx_kwargs = dict()
        tx_kwargs["limit"] = self.MAX_DATA
        tx_kwargs["min_timestamp"] = utl.to_unix_time(last_24_hours, millis=True)

        to_bot = list()
        from_bot = list()

        delay = self.config.get("delay")

        while True:
            # Get all transactions from or to bot address
            transactions = tg.get_transactions(addr_base58, **tx_kwargs)

            for tx in transactions["data"]:
                value = tx["raw_data"]["contract"][0]["parameter"]["value"]

                if "amount" in value:
                    trx_amount = value["amount"]

                    if value["to_address"] == addr_hex:
                        to_bot.append(trx_amount)
                    else:
                        from_bot.append(trx_amount)

            # End loop if we got less than the requested max number of transactions
            if not len(transactions["data"]) == self.MAX_DATA:
                break

            # Set fingerprint of last request to continue the next one
            tx_kwargs["fingerprint"] = transactions["meta"]["fingerprint"]
            time.sleep(delay)

        in_trx = self.get_tron().fromSun(sum(to_bot))
        out_trx = self.get_tron().fromSun(sum(from_bot))

        msg = f"`TRX In:     {in_trx}`\n" \
              f"`TRX Out:    {out_trx}`\n\n" \
              f"`TRX Profit: {in_trx - out_trx}`"
        message.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
