import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from tronapi import Tron
from trx_utils import is_address
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin


class Withdraw(TrxBetBotPlugin):

    def __enter__(self):
        if not self.global_table_exists("withdrawals"):
            sql = self.get_resource("create_withdrawals.sql")
            self.execute_global_sql(sql)
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

        # Check if provided address is valid
        if not bool(is_address(address)):
            msg = f"{emo.ERROR} Provided TRX wallet is not valid"
            update.message.reply_text(msg)
            return

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

        try:
            send = tron.trx.send(address, float(amount))
            txid = send["transaction"]["txID"]
        except Exception as e:
            logging.error(f"Couldn't withdraw full amount - {e}")

            amount = float(amount) - con.TRX_FEE

            try:
                send = tron.trx.send(address, amount)
                txid = send["transaction"]["txID"]
            except Exception as e:
                logging.error(f"Couldn't withdraw full amount minus fee - {e}")
                msg = f"{emo.ERROR} Couldn't withdraw: {repr(e)} - Try /send command"
                update.message.reply_text(msg)
                return

        explorer_link = f"https://tronscan.org/#/transaction/{txid}"
        msg = f"{emo.DONE} Successfully withdrawn `{amount}` TRX. [View " \
              f"on Block Explorer]({explorer_link}) (wait ~1 minute)"

        message = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

        if bot.get_chat(update.message.chat_id).type == Chat.PRIVATE:
            remove_time = self.config.get("private_remove_after")
        else:
            remove_time = self.config.get("public_remove_after")

        if message:
            self.run_job(
                self._remove_msg,
                datetime.now() + timedelta(seconds=remove_time),
                context=f"{message.chat_id}_{message.message_id}")

        logging.info(f"Withdraw {amount} TRX from {data[0][1]} to {address} - {update}")

        sql = self.get_resource("insert_withdrawal.sql")
        self.execute_global_sql(sql, data[0][1], address, int(balance))

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
