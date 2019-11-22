import logging

from tronapi import Tron
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


class Balance(TrxBetBotPlugin):

    def __enter__(self):
        if not self.table_exists("addresses", plugin="deposit"):
            sql = self.get_resource("create_addresses.sql")
            self.execute_sql(sql)
        return self

    def execute(self, bot, update, args):
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

            msg = f"Balance: `{amount}` TRX"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        else:
            msg = "You don't have a wallet yet. Create one with `/deposit`"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
