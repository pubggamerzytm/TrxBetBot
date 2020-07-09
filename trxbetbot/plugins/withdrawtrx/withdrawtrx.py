import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from trxbetbot.trxapi import TRXAPI
from trx_utils import is_address
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin


class Withdrawtrx(TrxBetBotPlugin):

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
            msg = f"{emo.ERROR} Provided TRX wallet is not valid"
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

        trx_kwargs = dict()
        trx_kwargs["private_key"] = res["data"][0][2]
        trx_kwargs["default_address"] = from_address

        tron = TRXAPI(**trx_kwargs)

        balance = tron.re(tron.trx.get_balance)
        amount = tron.fromSun(balance)

        if (float(amount) - con.TRX_FEE) <= 0:
            msg = f"{emo.ERROR} Not enough funds after paying fee of {con.TRX_FEE} TRX"
            logging.info(f"{msg} - {from_address} - {update}")
            update.message.reply_text(msg)
            return

        try:
            # Try withdrawing without paying a fee
            send = tron.re(tron.trx.send, to_address, amount)

            if "transaction" not in send:
                logging.error(f"Key 'transaction' not in result")
                raise Exception(send["message"])

            txid = send["transaction"]["txID"]
            logging.info("Withdrawn without paying fee")
        except Exception as e:
            logging.info(f"Couldn't withdraw without paying fee: {e} - {update}")

            try:
                # Try withdrawing with paying a fee
                amount = float(amount) - con.TRX_FEE
                send = tron.re(tron.trx.send, to_address, amount)

                if "transaction" not in send:
                    logging.error(f"Key 'transaction' not in result")
                    raise Exception(send["message"])

                txid = send["transaction"]["txID"]
                logging.info("Withdrawn with paying fee")
            except Exception as e:
                msg = f"{emo.ERROR} Couldn't withdraw {amount} TRX from {from_address} to {to_address}: {e}"

                logging.error(msg)
                update.message.reply_text(msg)
                return

        logging.info(f"Withdrawn {amount} TRX from {from_address} to {to_address}: {send}")

        sql = self.get_resource("insert_withdrawal.sql")
        self.execute_global_sql(sql, from_address, to_address, tron.toSun(amount))

        explorer_link = f"https://tronscan.org/#/transaction/{txid}"
        msg = f"{emo.DONE} Successfully withdrawn `{amount}` TRX. [View " \
              f"on Block Explorer]({explorer_link}) (wait ~1 minute)"

        message = update.message.reply_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True)

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
