import logging
import trxbetbot.emoji as emo

from tronapi import Tron
from telegram import ParseMode
from trx_utils import is_address
from trxbetbot.plugin import TrxBetBotPlugin


class Withdraw(TrxBetBotPlugin):

    def __enter__(self):
        if not self.table_exists("addresses", plugin="deposit"):
            sql = self.get_resource("create_addresses.sql")
            self.execute_sql(sql)
        return self

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if len(args) != 1:
            update.message.reply_text(
                text=f"Usage:\n{self.get_usage()}",
                parse_mode=ParseMode.MARKDOWN)
            return

        address = args[0]

        # Check if generated address is valid
        if not bool(is_address(address)):
            msg = f"{emo.ERROR} Provided TRX wallet is not valid"
            update.message.reply_text(msg)
            return

        user_id = update.effective_user.id

        sql = self.get_resource("select_address.sql")
        res = self.execute_sql(sql, user_id, plugin="deposit")

        if not res["success"]:
            # TODO: show error
            return

        data = res["data"]

        if data:
            trx_kwargs = dict()
            trx_kwargs["private_key"] = data[0][2]
            trx_kwargs["default_address"] = data[0][1]

            tron = Tron(**trx_kwargs)

            balance = tron.trx.get_balance()
            amount = tron.fromSun(balance)

            send_bot = tron.trx.send(address, float(amount))
            trans_id = send_bot["transaction"]["txID"]

            # TODO: Check if successfull und if yes ...
            # TODO: Show success / error message and link to BlockExplorer
        else:
            msg = f"{emo.ERROR} You don't have a wallet yet. Create one with /deposit"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
