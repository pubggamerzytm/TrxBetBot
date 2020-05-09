from tronapi import Tron
from telegram import ParseMode
from datetime import datetime, timedelta
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
        message = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        remove_time = self.config.get("remove_after")

        self.repeat_job(
            self._remove_msg,
            0,
            datetime.now() + timedelta(seconds=remove_time),
            context=f"{message.chat_id}_{message.message_id}")

    def _remove_msg(self, bot, job):
        param_lst = job.context.split("_")
        chat_id = param_lst[0]
        msg_id = param_lst[1]

        bot.delete_message(chat_id=chat_id, message_id=msg_id)
        job.schedule_removal()
