import logging
import trxbetbot.emoji as emo

from tronapi import Tron
from telegram import ParseMode
from trx_utils import is_address
from trxbetbot.plugin import TrxBetBotPlugin


# TODO: Do i ever need to account for a fee?
class Send(TrxBetBotPlugin):

    def __enter__(self):
        if not self.global_table_exists("sent"):
            sql = self.get_resource("create_sent.sql")
            self.execute_global_sql(sql)
        return self

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if len(args) != 2:
            update.message.reply_text(
                text=f"Usage:\n{self.get_usage()}",
                parse_mode=ParseMode.MARKDOWN)
            return

        amount = args[0]

        # Check if amount is valid
        try:
            float(amount)
        except:
            msg = f"{emo.ERROR} Provided amount is not valid"
            logging.info(f"{msg} - {update}")
            update.message.reply_text(msg)
            return

        address = args[1]

        # Check if provided address is valid
        if not bool(is_address(address)):
            msg = f"{emo.ERROR} Provided wallet is not valid"
            logging.info(f"{msg} - {update}")
            update.message.reply_text(msg)
            return

        user_id = update.effective_user.id

        sql = self.get_global_resource("select_address.sql")
        res = self.execute_global_sql(sql, user_id)

        if not res["success"]:
            # TODO: show error
            return

        data = res["data"]

        trx_kwargs = dict()
        trx_kwargs["private_key"] = data[0][2]
        trx_kwargs["default_address"] = data[0][1]

        tron = Tron(**trx_kwargs)

        balance = tron.trx.get_balance()
        available_amount = tron.fromSun(balance)

        # Check if address has enough balance
        if float(amount) > float(available_amount):
            msg = f"{emo.ERROR} Not enough funds. You balance is {available_amount} TRX"
            logging.info(f"{msg} - {data[0][1]} - {update}")
            update.message.reply_text(msg)
            return

        send = tron.trx.send(address, float(amount))
        txid = send["transaction"]["txID"]

        explorer_link = f"https://tronscan.org/#/transaction/{txid}"
        msg = f"{emo.DONE} [Successfully sent {amount} TRX]({explorer_link})\n" \
              f"(Link will work after ~1 minute)"

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

        logging.info(f"Sent {amount} TRX from {data[0][1]} to {address} - {update}")

        sql = self.get_resource("insert_sent.sql")
        self.execute_global_sql(sql, data[0][1], address, int(balance))
