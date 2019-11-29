from tronapi import Tron
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


class Balance(TrxBetBotPlugin):

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        user_id = update.effective_user.id

        sql = self.get_global_resource("select_address.sql")
        res = self.execute_global_sql(sql, user_id)

        if not res["success"]:
            msg = f"Something went wrong. Please contact @Wikioshi the owner of this bot"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        data = res["data"]

        trx_kwargs = dict()
        trx_kwargs["private_key"] = data[0][2]
        trx_kwargs["default_address"] = data[0][1]

        tron = Tron(**trx_kwargs)

        balance = tron.trx.get_balance()
        amount = tron.fromSun(balance)

        msg = f"Balance: `{amount}` TRX"
        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
