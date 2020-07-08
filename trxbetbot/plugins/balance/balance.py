import logging
import trxbetbot.emoji as emo

from trxbetbot.trc20 import TRC20
from trxbetbot.trxapi import TRXAPI
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


class Balance(TrxBetBotPlugin):

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        user_id = update.effective_user.id

        sql = self.get_global_resource("select_address.sql")
        res = self.execute_global_sql(sql, user_id)

        if not res["success"] or not res["data"]:
            msg = f"{emo.ERROR} Something went wrong. Please contact Support"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        trx_kwargs = dict()
        trx_kwargs["private_key"] = res["data"][0][2]
        trx_kwargs["default_address"] = res["data"][0][1]

        tron = TRXAPI(**trx_kwargs)

        trx_balance = tron.trx.get_balance()
        trx_amount = tron.fromSun(trx_balance)

        account = Trongrid().get_account(res["data"][0][1])

        win_amount = 0
        if account and account["data"]:
            for trc20 in account["data"][0]["trc20"]:
                for trc20_addr, trc20_bal in trc20.items():
                    if trc20_addr == TRC20().SC["WIN"]:
                        win_amount = tron.fromSun(int(trc20_bal))

        msg = f"*Your wallet balance*\n\n" \
              f"`TRX: {trx_amount}`\n" \
              f"`WIN: {win_amount}`\n\n" \
              f"Balance refresh for WIN can take up to 10 min."
        message = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        if bot.get_chat(update.message.chat_id).type == Chat.PRIVATE:
            remove_time = self.config.get("private_remove_after")
        else:
            remove_time = self.config.get("public_remove_after")

        if message:
            self.run_job(
                self._remove_msg,
                datetime.now() + timedelta(seconds=remove_time),
                context=f"{message.chat_id}_{message.message_id}")

    def _remove_msg(self, bot, job):
        param_lst = job.context.split("_")
        chat_id = param_lst[0]
        msg_id = param_lst[1]

        try:
            logging.info(f"Removing {self.get_name()}-message (chat_id {chat_id} msg_id {msg_id})")
            bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logging.info(f"Removed {self.get_name()}-message (chat_id {chat_id} msg_id {msg_id})")
        except Exception as e:
            msg = f"Not possible to remove {self.get_name()}-message (chat_id {chat_id} msg_id {msg_id}): {e}"
            logging.error(msg)
