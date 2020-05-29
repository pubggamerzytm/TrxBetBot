import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from tronapi import Tron
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin


class Airdrop(TrxBetBotPlugin):

    INFO = "info.md"
    MIN_AMOUNT = 0.01

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        sql = self.get_global_resource("select_address.sql")
        user_wallet = self.execute_global_sql(sql, update.effective_user.id)

        if not user_wallet["success"]:
            msg = f"{emo.ERROR} Couldn't retrieve your wallet details"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {user_wallet}")
            return

        nr_users = self.config.get("number_of_users")

        info = self.get_resource("info.md")
        info = info.replace("{{users}}", str(nr_users))
        info = info.replace("{{handle}}", self.get_name())

        if not args or len(args) != 1:
            update.message.reply_text(
                text=f"Usage:\n{info}",
                parse_mode=ParseMode.MARKDOWN)
            return

        initial_amount = args[0]
        minus_percent = self.config.get("minus")
        amount = float(f"{float(initial_amount) / 100 * (100 - minus_percent):.3f}")
        bot_amount = float(f"{(float(initial_amount) - amount):.3f}")

        if update.effective_chat.type == Chat.PRIVATE:
            msg = f"{emo.ERROR} You can only execute this command in a public group"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        bet_count = nr_users * 5

        sql = self.get_resource("select_last.sql")
        res_bet = self.execute_sql(sql, bet_count, plugin="bet")

        if not res_bet["success"]:
            msg = f"{emo.ERROR} Couldn't retrieve last active users from /bet"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_bet}")
            self.notify(msg)
            return

        res_win = self.execute_sql(sql, bet_count, plugin="win")

        if not res_win["success"]:
            msg = f"{emo.ERROR} Couldn't retrieve last active users from /win"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_win}")
            self.notify(msg)
            return

        res_mix = self.execute_sql(sql, bet_count, plugin="mix")

        if not res_mix["success"]:
            msg = f"{emo.ERROR} Couldn't retrieve last active users from /mix"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_mix}")
            self.notify(msg)
            return

        # Combine all lists and sort bets by date
        final = res_bet["data"] + res_win["data"] + res_mix["data"]
        final.sort(key=lambda x: x[11])

        logging.info(f"Sorted last bets: {final}")

        # Get last user IDs
        user_ids = set()
        for bet in reversed(final):
            # Do not tip own user
            if int(update.effective_user.id) == int(bet[2]):
                continue
            user_ids.add(bet[2])

            if len(user_ids) == nr_users:
                break

        logging.info(f"User IDs to tip: {user_ids}")

        fees = con.TRX_FEE * (len(user_ids) + 1)
        total = float(amount) - fees
        user_amount = total / len(user_ids)

        logging.info(f"Initial amount: {initial_amount} - "
                     f"Minus %: {minus_percent} - "
                     f"Amount: {amount} - "
                     f"Bot amount: {bot_amount} - "
                     f"Fee amount: {fees}"
                     f"User amount: {user_amount}")

        if user_amount <= self.MIN_AMOUNT:
            msg = f"{emo.ERROR} Not possible to tip less than {self.MIN_AMOUNT} TRX"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_mix}")
            return

        sql = self.get_resource("select_user.sql")

        # Get last usernames
        addresses = list()
        users_str = str()
        for user_id in user_ids:
            res = self.execute_global_sql(sql, user_id)["data"]
            if res:
                addresses.append(res[0][5])

                username = f"@{res[0][1]}" if res[0][1] else res[0][2]
                users_str += username + ", "

        users_str = users_str[:-2]

        if update.effective_user.username:
            tipping_usr = f"@{update.effective_user.username}"
        else:
            tipping_usr = update.effective_user.first_name

        tipping = self.get_resource("tipping.md")
        tipping = tipping.replace("{{user}}", tipping_usr)
        tipping = tipping.replace("{{amount}}", str(initial_amount))
        tipping = tipping.replace("{{useramount}}", str(user_amount))
        tipping = tipping.replace("{{userlist}}", users_str)

        # Set up user wallet
        trx_kwargs = dict()
        trx_kwargs["private_key"] = user_wallet["data"][0][2]
        trx_kwargs["default_address"] = user_wallet["data"][0][1]

        tron = Tron(**trx_kwargs)

        balance = tron.trx.get_balance()
        available_amount = tron.fromSun(balance)

        logging.info(f"Balance: {balance}")

        if available_amount < float(initial_amount):
            msg = f"{emo.ERROR} Not enough balance. You need {total} TRX for this airdrop."
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_mix}")
            return

        # Send share to bot wallet
        bot_addr = self.get_tron().default_address.hex
        tron.trx.send(bot_addr, bot_amount)

        # Tip users
        for address in addresses:
            try:
                # Send tip to chosen user
                tip = tron.trx.send(address, user_amount)

                # An error was returned
                if "code" in tip and "message" in tip:
                    raise Exception(tip["message"])

                logging.info(f"Tipped address {address} with {user_amount} TRX")
            except Exception as e:
                msg = f"{emo.ERROR} Something went wrong. Not all users tipped"
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                msg = f"Couldn't tip address {address} with {user_amount} TRX: {e}"
                logging.error(msg)
                self.notify(msg)
                return

        message = update.message.reply_text(tipping)

        if bot.get_chat(update.message.chat_id).type == Chat.PRIVATE:
            remove_time = self.config.get("private_remove_after")
        else:
            remove_time = self.config.get("public_remove_after")

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