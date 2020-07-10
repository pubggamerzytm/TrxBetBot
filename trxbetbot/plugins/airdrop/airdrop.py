import time
import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from trxbetbot.trxapi import TRXAPI
from telegram import ParseMode, Chat
from trxbetbot.plugin import TrxBetBotPlugin


class Airdrop(TrxBetBotPlugin):

    INFO = "info.md"
    MIN_AMOUNT = 0.01

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if update.effective_chat.type == Chat.PRIVATE:
            msg = f"{emo.ERROR} You can only execute this command in a public group"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        sql = self.get_global_resource("select_address.sql")
        user_wallet = self.execute_global_sql(sql, update.effective_user.id)

        if not user_wallet["success"]:
            msg = f"{emo.ERROR} Couldn't retrieve your wallet details"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {user_wallet}")
            return

        # Get number of users to tip
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

        min_trx = self.config.get("min_trx")
        min_sun = self.get_tron().toSun(min_trx)

        # Select more data sets than we need to make sure that after
        # filtering out same users we still have the needed amount of data
        bet_count = nr_users * 50

        sql = self.get_resource("select_last.sql")
        res_bet = self.execute_sql(sql, min_sun, bet_count, plugin="bet")

        if not res_bet["success"]:
            msg = f"{emo.ERROR} Couldn't retrieve last active users from /bet"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_bet}")
            self.notify(msg)
            return

        res_win = self.execute_sql(sql, min_sun, bet_count, plugin="win")

        if not res_win["success"]:
            msg = f"{emo.ERROR} Couldn't retrieve last active users from /win"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_win}")
            self.notify(msg)
            return

        res_mix = self.execute_sql(sql, min_sun, bet_count, plugin="mix")

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

        if len(user_ids) < 1:
            msg = f"{emo.ERROR} Airdrop not possible. Couldn't identify any users."
            update.message.reply_text(msg)
            logging.error(msg)
            return

        fees = con.TRX_FEE * (len(user_ids) + 1)
        total = float(amount) - fees
        usr_amount = float(f"{(total / len(user_ids)):.3f}")

        logging.info(f"Initial amount: {initial_amount} - "
                     f"Minus %: {minus_percent} - "
                     f"Amount: {amount} - "
                     f"Bot amount: {bot_amount} - "
                     f"Fee amount: {fees}"
                     f"User amount: {usr_amount}")

        if usr_amount <= self.MIN_AMOUNT:
            msg = f"{emo.ERROR} Not possible to tip less than {self.MIN_AMOUNT} TRX"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_mix}")
            return

        sql = self.get_resource("select_user.sql")

        if update.effective_user.username:
            tipping_usr = f"@{update.effective_user.username}"
        else:
            tipping_usr = update.effective_user.first_name

        # Set up user wallet
        trx_kwargs = dict()
        trx_kwargs["private_key"] = user_wallet["data"][0][2]
        trx_kwargs["default_address"] = user_wallet["data"][0][1]

        tron = TRXAPI(**trx_kwargs)

        balance = tron.re(tron.trx.get_balance)
        available_amount = tron.fromSun(balance)

        logging.info(f"Balance: {available_amount}")

        # Check if balance is sufficient
        if available_amount < float(initial_amount):
            msg = f"{emo.ERROR} Not enough balance. You need {total} TRX for this airdrop."
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(f"{msg} - {res_mix}")
            return

        # Send TRX share to bot wallet
        bot_addr = self.get_tron().default_address.hex

        try:
            send_bot = tron.re(tron.trx.send, bot_addr, bot_amount)

            # An error was returned
            if "code" in send_bot and "message" in send_bot:
                raise Exception(send_bot["message"])

            logging.info(f"Sent share of {bot_amount} TRX to bot wallet {bot_addr} - {send_bot}")
        except Exception as e:
            logging.error(f"Not possible to send {bot_amount} TRX to bot wallet: {e}")
            self.notify(f"Airdrop - Not possible to receive {bot_amount} TRX: {e}")

        users_str = str()

        # Get user data and airdrop TRX
        for user_id in user_ids:
            res = self.execute_global_sql(sql, user_id)

            if not res["success"] or not res["data"]:
                # Issue can be that users don't exist in DB since they don't need to for betting
                msg = f"{emo.ERROR} Couldn't retrieve user data for ID {user_id} to airdrop: {res}"
                logging.error(msg)
                continue

            usr_data = res["data"][0]
            username = f"@{usr_data[1]}" if usr_data[1] else usr_data[2]
            address = usr_data[5]

            try:
                # Airdrop TRX to user
                tip = tron.re(tron.trx.send, address, usr_amount)

                # An error was returned
                if "code" in tip and "message" in tip:
                    raise Exception(tip["message"])

                users_str += username + ", "

                if self.config.get("direct_msg"):
                    delay = self.config.get("delay")

                    # Sleep for configurable time so that bot doesn't get blocked
                    # because it's pushing out more than 30 messages per second
                    if delay and delay > 0:
                        time.sleep(delay)

                    try:
                        # Send direct message to user that received airdrop
                        msg = f"Hey {usr_data[2]} you got an airdrop of {usr_amount} TRX from user {tipping_usr}!"
                        bot.send_message(user_id, msg)
                    except Exception as e:
                        msg = f"Can't notify user {username}({user_id}) about airdrop of {usr_amount} TRX"
                        logging.warning(f"{msg}: {e}")

                logging.info(f"Airdropped {usr_amount} TRX to user {username} ({user_id}) at address {address}")
            except Exception as ex:
                msg = f"{emo.ERROR} Not possible to airdrop {usr_amount} TRX to user {username} ({user_id})"
                logging.error(f"{msg}: {ex}")
                self.notify(f"{msg}: {ex}")

                try:
                    update.message.reply_text(msg)
                except Exception as e:
                    msg = f"Not possible to notify user {tipping_usr} about not being able to airdrop: {e}"
                    logging.error(msg)

        users_str = users_str[:-2] if users_str else "No users found"

        tipping = self.get_resource("tipping.md")
        tipping = tipping.replace("{{user}}", tipping_usr)
        tipping = tipping.replace("{{amount}}", str(initial_amount))
        tipping = tipping.replace("{{useramount}}", str(usr_amount))
        tipping = tipping.replace("{{userlist}}", users_str)

        try:
            update.message.reply_text(tipping)
        except Exception as e:
            msg = f"Not able to send airdrop message to user {tipping_usr}: {e}"
            logging.error(msg)
