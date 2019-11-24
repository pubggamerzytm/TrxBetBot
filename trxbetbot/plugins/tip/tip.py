import time
import logging
import trxbetbot.emoji as emo
import trxbetbot.utils as utl

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


# TODO: Nachricht an zu tippenden user schicken
# TODO: Add examples to usage-files
class Tip(TrxBetBotPlugin):

    def __enter__(self):
        if not self.global_table_exists("tips"):
            sql = self.get_resource("create_tips.sql")
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

        to_username = args[1].replace("@", "")

        sql = self.get_resource("select_user.sql")
        res = self.execute_global_sql(sql, to_username)

        if not res["success"]:
            # TODO: show error
            return

        if not res["data"]:
            msg = f"{emo.ERROR} User @{to_username} doesn't have a wallet yet"
            logging.info(f"{msg} - {update}")
            update.message.reply_text(msg)
            return

        to_address = res["data"][0][5]

        user_id = update.effective_user.id

        sql = self.get_global_resource("select_address.sql")
        # TODO: Could be that user has no wallet...
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

        send = tron.trx.send(to_address, float(amount))
        txid = send["transaction"]["txID"]

        explorer_link = f"https://tronscan.org/#/transaction/{txid}"
        msg = f"{emo.DONE} [@{utl.esc_md(to_username)} was tipped with {amount} TRX]" \
              f"({explorer_link})\n(Link will work after ~1 minute)"

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

        logging.info(f"{msg} - {update}")

        sql = self.get_resource("insert_sent.sql")
        self.execute_global_sql(sql, data[0][1], to_address, int(balance))
