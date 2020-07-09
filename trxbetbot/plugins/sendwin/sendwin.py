import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from trxbetbot.trxapi import TRXAPI
from trxbetbot.trc20 import TRC20
from telegram import ParseMode, Chat
from trx_utils import is_address
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


class Sendwin(TrxBetBotPlugin):

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
            amount = float(amount)
        except:
            msg = f"{emo.ERROR} Provided amount is not valid"
            logging.info(f"{msg} - {update}")
            update.message.reply_text(msg)
            return

        to_address = args[1]

        # Check if provided address is valid
        if not bool(is_address(to_address)):
            msg = f"{emo.ERROR} Provided wallet is not valid"
            logging.info(f"{msg} - {update}")
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

        tron = TRXAPI(**tron_kwargs)

        trx_balance = tron.re(tron.trx.get_balance)
        trx_amount = tron.fromSun(trx_balance)

        # Check if enough TRX to pay transaction fee
        if float(trx_amount) < con.TRX_FEE:
            msg = f"{emo.ERROR} Not enough funds. You can't pay the transaction fee of {con.TRX_FEE} TRX"
            logging.info(f"{msg} - Current balance: {trx_amount} - {update}")
            update.message.reply_text(msg)
            return

        account = Trongrid().get_account(from_address)

        win_amount = 0

        # Get WIN balance
        if account and account["data"]:
            for trc20 in account["data"][0]["trc20"]:
                for trc20_addr, trc20_bal in trc20.items():
                    if trc20_addr == TRC20().SC["WIN"]:
                        win_amount = tron.fromSun(int(trc20_bal))

        # Check if address has enough balance
        if amount > float(win_amount):
            msg = f"{emo.ERROR} Not enough funds. Your balance is {win_amount} WIN"
            logging.info(f"{msg} - {from_address} - {update}")
            update.message.reply_text(msg)
            return

        message = None

        try:
            sent_win = TRC20().send("WIN", tron, to_address, amount)
            logging.info(f"Sent {amount} WIN from {from_address} to {to_address}: {sent_win}")

            if "transaction" not in sent_win:
                logging.error(f"Key 'transaction' not in result")
                raise Exception(sent_win["message"])

            # Insert details into database
            sql = self.get_resource("insert_sent.sql")
            self.execute_global_sql(sql, from_address, to_address, tron.toSun(amount))

            txid = sent_win["transaction"]["txID"]
            explorer_link = f"https://tronscan.org/#/transaction/{txid}"
            msg = f"{emo.DONE} Successfully sent `{amount}` WIN. [View " \
                  f"on Block Explorer]({explorer_link}) (wait ~1 minute)"

            message = update.message.reply_text(
                msg,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True)
        except Exception as e:
            msg = f"{emo.ERROR} Couldn't send {amount} WIN from {from_address} to {to_address}: {e}"

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
