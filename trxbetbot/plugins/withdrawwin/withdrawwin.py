import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from tronapi import Tron
from trxbetbot.trc20 import TRC20
from trx_utils import is_address
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


class Withdrawwin(TrxBetBotPlugin):

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

        to_address = args[0]

        # Check if provided address is valid
        if not bool(is_address(to_address)):
            msg = f"{emo.ERROR} Provided WIN wallet is not valid"
            update.message.reply_text(msg)
            return

        user_id = update.effective_user.id

        sql = self.get_global_resource("select_address.sql")
        res = self.execute_global_sql(sql, user_id)

        if not res["success"] or not res["data"]:
            msg = f"{emo.ERROR} Something went wrong. Please contact Support"

            logging.error(f"{msg}: {res} - {update}")
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        from_address = res["data"][0][1]

        tron_kwargs = dict()
        tron_kwargs["private_key"] = res["data"][0][2]
        tron_kwargs["default_address"] = from_address

        tron = Tron(**tron_kwargs)

        # Get TRX balance
        trx_balance = tron.trx.get_balance()
        trx_amount = tron.fromSun(trx_balance)

        # Check if enough TRX to pay transaction fee
        if float(trx_amount) < con.TRX_FEE:
            msg = f"{emo.ERROR} Not enough funds. You can't pay the transaction fee of {con.TRX_FEE} TRX"
            logging.info(f"{msg} - Current balance: {trx_amount} - {update}")
            update.message.reply_text(msg)
            return

        account = Trongrid().get_account(from_address)

        win_balance = 0
        win_amount = 0

        # Get WIN balance
        if account and account["data"]:
            for trc20 in account["data"][0]["trc20"]:
                for trc20_addr, trc20_bal in trc20.items():
                    if trc20_addr == TRC20().SC["WIN"]:
                        win_balance = int(trc20_bal)
                        win_amount = tron.fromSun(win_balance)

        message = None

        try:
            sent_win = TRC20().send("WIN", tron, to_address, win_amount)
            logging.info(f"Withdrawn {win_amount} WIN from {from_address} to {to_address}: {sent_win}")

            if "transaction" not in sent_win:
                logging.error(f"Key 'transaction' not in result")
                raise Exception(sent_win["message"])

            sql = self.get_resource("insert_withdrawal.sql")
            self.execute_global_sql(sql, from_address, to_address, win_balance)

            txid = sent_win["transaction"]["txID"]
            explorer_link = f"https://tronscan.org/#/transaction/{txid}"
            msg = f"{emo.DONE} Successfully withdrawn `{win_amount}` WIN. [View " \
                  f"on Block Explorer]({explorer_link}) (wait ~1 minute)"

            message = update.message.reply_text(
                msg,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True)
        except Exception as e:
            msg = f"{emo.ERROR} Couldn't withdraw {win_amount} WIN from {from_address} to {to_address}: {e}"

            logging.error(msg)
            update.message.reply_text(msg)

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
