import os
import time
import random
import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.tronscan import Tronscan


class Bet(TrxBetBotPlugin):

    AUTOBET = "autobet"

    _WON_DIR = "won"
    _LOST_DIR = "lost"
    _VALID_CHARS = "123456789abcdef"
    _SECOND_CHANCE_DIR = "won_second"
    _LEVERAGE = {1: 14.4, 2: 7.2014, 3: 4.8453, 4: 3.6604, 5: 2.9273, 6: 2.4246, 7: 2.0803, 8: 1.8122,
                 9: 1.6231, 10: 1.4562, 11: 1.3221, 12: 1.2131, 13: 1.1264, 14: 1.0523}

    tronscan = Tronscan()

    def __enter__(self):
        if not self.table_exists("addresses"):
            sql = self.get_resource("create_addresses.sql")
            self.execute_sql(sql)
        if not self.table_exists("bets"):
            sql = self.get_resource("create_bets.sql")
            self.execute_sql(sql)

        return self

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if len(args) != 2:
            update.message.reply_text(self.get_usage(), parse_mode=ParseMode.MARKDOWN)
            return

        chars = set(self.remove_unwanted(args[0]))
        count = len(chars)

        amount = args[1]

        try:
            amount = float(amount)
        except:
            msg = f"{emo.ERROR} Provide a valid TRX amount"
            update.message.reply_text(msg)
            return

        # Check if user provided any valid characters
        if count == 0:
            msg = f"{emo.ERROR} You did not provide any valid characters to bet on. " \
                  f"Allowed are: `{self._VALID_CHARS}`"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # Bet need to be smaller than allowed characters (at least by one)
        if count >= (len(self._VALID_CHARS)):
            msg = f"{emo.ERROR} You need to provide 1-{len(self._VALID_CHARS)-1} characters and not {count}"
            update.message.reply_text(msg)
            return

        logging.info(f"Update: {update}")

        tron = Tron()
        account = tron.create_account
        tron.private_key = account.private_key
        tron.default_address = account.address.base58

        # Check if generated address is valid
        if not bool(tron.isAddress(account.address.hex)):
            msg = f"{emo.ERROR} Generated wallet is not valid"
            update.message.reply_text(msg)
            return

        generated = {"pubkey": account.public_key,
                     "privkey": account.private_key,
                     "addr_hex": account.address.hex,
                     "addr_base58": account.address.base58}

        logging.info(f"Update: {update}")
        logging.info(f"TRX address created {generated}")

        # Save generated address to database
        sql = self.get_resource("insert_address.sql")
        self.execute_sql(sql, account.address.base58, account.private_key)

        choice = "".join(sorted(chars))
        leverage = self._LEVERAGE[len(chars)]

        # Save bet details to database
        sql = self.get_resource("insert_bet.sql")
        self.execute_sql(sql, account.address.base58, choice, update.effective_user.id)

        # Get min and max amounts for this bet from config
        min_trx = self.config.get("min_trx")
        max_trx = self.config.get("max_trx")

        # Get users wallet to send bet TRX from
        sql = self.get_global_resource("select_address.sql")
        res = self.execute_global_sql(sql, update.effective_user.id)

        # --- Start auto-bet logic - send TRX from user wallet to generated wallet ---

        if self.is_autobet(update):
            logging.info("Bet is an auto-bet")

            msg = self.get_resource("betting_autobet.md")
            msg = msg.replace("{{choice}}", choice)
            msg = msg.replace("{{count}}", str(count))
            msg = msg.replace("{{min}}", str(min_trx))
            msg = msg.replace("{{max}}", str(max_trx))
            msg = msg.replace("{{factor}}", str(leverage))
            msg1 = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

            logging.info(msg.replace("\n", " "))

            msg = f"{emo.WAIT} AUTO-BET: Sending TRX from your wallet..."
            msg2 = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

            logging.info(msg.replace("\n", " "))

            if not res["success"]:
                msg = f"{emo.ERROR} Auto-bet stopped. Your TRX wallet could not be determined."
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                self.get_job(update.effective_user.id).schedule_removal()
                logging.error(res)
                return

            logging.info(f"Users wallet used for auto-bet: {res['data']}")

            # Users existing wallet used for auto-bet
            from_user = Tron()
            from_user.private_key = res["data"][0][2]
            from_user.default_address = res["data"][0][1]

            sql = self.get_resource("select_autobet.sql", plugin="autobet")
            res = self.execute_sql(sql, update.effective_user.id, plugin="autobet")

            if not res["success"]:
                msg = f"{emo.ERROR} Auto-bet stopped. Couldn't read data from DB."
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                self.get_job(update.effective_user.id).schedule_removal()
                logging.error(res)
                return

            bet_amount = float(res["data"][0][2])

            # Send determined bet amount from user wallet to generated wallet
            send = from_user.trx.send(tron.default_address.hex, bet_amount)
            logging.info(f"Auto-bet {bet_amount} TRX - {send}")

            if "code" in send and "message" in send:
                msg = f"{emo.ERROR} Auto-bet stopped. Not possible to send {bet_amount} TRX: {send['message']}"
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                self.get_job(update.effective_user.id).schedule_removal()
                logging.error(msg)
                return

            msg = f"{emo.DONE} AUTO-BET: Successfully sent `{bet_amount}` TRX to `{account.address.base58}`"
            msg2.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

            logging.info(msg.replace("\n", " "))

        # --- Start normal logic - either auto-send if possible or manual-send ---

        else:
            manual_send = False

            try:
                if not res["success"]:
                    raise Exception(f"Users TRX wallet could not be determined: {res}")

                from_user = Tron()
                from_user.private_key = res["data"][0][2]
                from_user.default_address = res["data"][0][1]

                # Get balance (in "Sun") of generated address
                balance = from_user.trx.get_balance()
                trx_balance = from_user.fromSun(balance)

                if trx_balance < (amount + con.TRX_FEE):
                    raise Exception(f"Not enough balance for autosend: {trx_balance} TRX")
            except Exception as e:
                logging.warning(f"Couldn't activate autosend: {e}")
                manual_send = True

            if manual_send:
                msg = self.get_resource("betting_manual.md")
            else:
                msg = self.get_resource("betting.md")

            msg = msg.replace("{{choice}}", choice)
            msg = msg.replace("{{count}}", str(count))
            msg = msg.replace("{{min}}", str(min_trx))
            msg = msg.replace("{{max}}", str(max_trx))
            msg = msg.replace("{{factor}}", str(leverage))
            msg1 = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

            logging.info(msg.replace("\n", ""))

            if manual_send:
                msg = f"`{account.address.base58}`"
            else:
                msg = f"{emo.WAIT} Sending TRX from your wallet..."

            msg2 = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

            logging.info(msg.replace("\n", ""))

            if not manual_send:
                try:
                    # Send bet amount from user wallet to generated wallet
                    send = from_user.trx.send(tron.default_address.hex, amount)
                    logging.info(f"Sent {amount} TRX to {tron.default_address.hex} - {send}")

                    if "code" in send and "message" in send:
                        raise Exception(send['message'])

                    msg = f"{emo.DONE} Successfully sent `{amount}` TRX to `{account.address.base58}`"
                    msg2.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

                    logging.info(msg.replace("\n", " "))
                except Exception as e:
                    msg = f"{emo.ERROR} Not possible to automatically send TRX. " \
                          f"Please send manually to this address: `{account.address.base58}`"
                    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                    logging.error(f"Not possible to auto-send TRX: {e}")

        # --- General logic ---

        first = self.config.get("check_start")
        check = self.config.get("balance_check")

        context = {
            "tron": tron,
            "choice": choice,
            "update": update,
            "start": time.time(),
            "msg1": msg1,
            "msg2": msg2
        }

        self.repeat_job(self.scan_balance, check, first=first, context=context)

        logging.info(f"Initiated repeating job for {account.address.base58}")

    def is_autobet(self, update):
        caption = update.effective_message.caption
        if caption and caption == self.AUTOBET:
            return True
        else:
            return False

    def _remove_losses(self, bot, job):
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

    def contains_all(self, chars):
        """ Check if characters in 'chars' are all valid characters """
        return 0 not in [c in self._VALID_CHARS for c in chars]

    def remove_unwanted(self, chars):
        return [i for i in chars if i in self._VALID_CHARS]

    def scan_balance(self, bot, job):
        tron = job.context["tron"]
        start = job.context["start"]
        choice = job.context["choice"]
        update = job.context["update"]

        bet_addr = tron.default_address
        bet_addr58 = bet_addr["base58"]

        # Messages that bot posted after user executed command
        msg1 = job.context["msg1"]
        msg2 = job.context["msg2"]

        # Read data for this bet from database
        bet = DBBet(self, bet_addr58, choice, update.effective_user.id)

        # Retrieve time in seconds to scan the balance
        time_frame = int(self.config.get("stop_check"))

        # Check if time limit for balance scanning is reached
        if (start + time_frame) < time.time():
            logging.info(f"Job {bet_addr58} - Ending job because {time_frame} seconds are over")

            # Stop repeating job since we reached max time frame to scan for a balance
            job.schedule_removal()
            logging.info(f"Job {bet_addr58} - Scheduled job for removal")

            # Remove messages after betting address isn't valid anymore
            self.remove_messages(bot, msg1, msg2, bet_addr58)

            # If there was a balance...
            if bet.usr_amount and bet.usr_amount != 0:
                # ... check if everything is complete
                if not bet.is_complete():
                    msg = f"Job {bet_addr58} - Not all data present"
                    logging.error(f"{msg}: {vars(bet)}")
                    self.notify(msg)
            return

        try:
            # Get balance (in "Sun") of generated address
            balance = tron.trx.get_balance()
        except Exception as e:
            logging.error(f"Job {bet_addr58} - Can't retrieve balance: {e}")
            return

        # Check if balance is 0. If yes, rerun job in specified interval
        if balance == 0:
            logging.info(f"Job {bet_addr58} - Balance: 0 TRX")
            return

        logging.info(f"Job {bet_addr58} - Balance: {tron.fromSun(balance)} TRX")

        # We already found a saved transaction
        if not bet.bet_trx_id:
            try:
                transactions = self.tronscan.get_transactions_for(bet_addr58)
                logging.info(f"Job {bet_addr58} - Get Transactions: {transactions}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't retrieve transaction: {e}")
                return

            found = False
            for trx in reversed(transactions["data"]):
                data = trx["contractData"]

                # We check just for TRX
                if "asset_name" not in data:
                    trx_id = trx["hash"]
                    from_base58 = data["owner_address"]
                    from_hex = Address().to_hex(from_base58)
                    trx_balance = data["amount"]
                    trx_amount = tron.fromSun(trx_balance)

                    # We only take the first transaction ...
                    if not found:
                        bet.bet_trx_id = trx_id
                        bet.usr_address = from_base58
                        bet.usr_amount = trx_balance

                        found = True

                    # ... everything else will be returned
                    else:
                        try:
                            # Return funds from betting address to original address
                            send = tron.trx.send(from_hex, float(trx_amount))

                            # An error was returned
                            if "code" in send and "message" in send:
                                raise Exception(send["message"])

                            msg = "Returned from Generated to User (not first transaction)"
                            logging.info(f"Job {bet_addr58} - {msg}: {send}")
                        except Exception as e:
                            msg = "Can't return from Generated to User (not first transaction)"
                            logging.error(f"Job {bet_addr58} - {msg}: {e}")

        # Check if a transaction was found
        if not bet.bet_trx_id:
            msg = f"Job {bet_addr58} - No transaction found"
            logging.error(msg)
            return
        # Check if a user address was found
        if not bet.usr_address:
            msg = f"Job {bet_addr58} - No user address found"
            logging.error(msg)
            return
        # Check if a user amount was found
        if not bet.usr_amount:
            msg = f"Job {bet_addr58} - No user amount found"
            logging.error(msg)
            return

        from_hex = Address().to_hex(bet.usr_address)

        amo = float(tron.fromSun(bet.usr_amount))
        min = self.config.get("min_trx")
        max = self.config.get("max_trx")

        # Check if amount is out of MIN / MAX boundaries
        if amo > max or amo < min:
            msg = f"{emo.ERROR} Sent amount of {amo} TRX is not inside min ({min} TRX) and max ({max} " \
                  f"TRX) boundaries. Whole amount will be returned to the wallet it was sent from."

            logging.info(f"Job {bet_addr58} - {msg}")

            try:
                # Send funds from betting address to original address
                send = tron.trx.send(from_hex, amo)

                # An error was returned
                if "code" in send and "message" in send:
                    raise Exception(send["message"])

                logging.info(f"Job {bet_addr58} - Send from Generated to User: {send}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't send from Generated to User: {e}")
                return

            try:
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logging.warning(f"Job {bet_addr58} - Can't send funds back for min / max violation: {e}")

            job.schedule_removal()
            logging.info(f"Job {bet_addr58} - Scheduled job for removal")

            self.remove_messages(bot, msg1, msg2, bet_addr58)
            return

        # Check if we already know the block
        if not bet.bet_trx_block:
            try:
                info = tron.trx.get_transaction_info(bet.bet_trx_id)
                logging.info(f"Job {bet_addr58} - Get Transaction Info: {info}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't retrieve transaction info: {e}")
                return

            if "blockNumber" not in info:
                logging.info(f"Job {bet_addr58} - Key 'blockNumber' not in info: {info}")
                return

            bet.bet_trx_block = info["blockNumber"]

        # Check if we already know the block hash
        if not bet.bet_trx_block_hash:
            try:
                block = tron.trx.get_block(bet.bet_trx_block)
                logging.info(f"Job {bet_addr58} - Get Block: {block}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't retrieve block info: {e}")
                return

            bet.bet_trx_block_hash = block["blockID"]

        logging.info(f"Job {bet_addr58} - "
                     f"TXID: {bet.bet_trx_id} - "
                     f"Sender: {bet.usr_address} - "
                     f"Block: {bet.bet_trx_block} - "
                     f"Block Hash: {bet.bet_trx_block_hash}")

        bot_addr = self.get_tron().default_address.hex

        second_chance_win = False
        second_chance_trx = 0

        last_char = bet.bet_trx_block_hash[-1:]

        # Determine if bet was won or lost
        # But only if not already saved
        if bet.bet_won is None:
            # WON
            if last_char in choice:
                bet.bet_won = "true"
                logging.info(
                    f"Job {bet_addr58} - "
                    f"WON: {bet.bet_won} "
                    f"Choice: {choice} "
                    f"Hash: {bet.bet_trx_block_hash}")
            # LOST
            else:
                logging.info(
                    f"Job {bet_addr58} - "
                    f"WON: False "
                    f"Choice: {choice} "
                    f"Hash: {bet.bet_trx_block_hash}")

                # Chance to still win even if you lost (aka bonus)
                bonuses = self.config.get("bonus_chances")
                bonuses = sorted(bonuses, key=lambda k: k['chance'])

                random_number = random.random()

                for bonus in bonuses:
                    # SECOND CHANCE WON
                    if random_number < (bonus["chance"] / 100):
                        second_chance_trx = bonus["trx"]
                        second_chance_win = True
                        bet.bet_won = "true"
                        logging.info(
                            f"Job {bet_addr58} - "
                            f"SECOND CHANCE WON: {bet.bet_won} "
                            f"Choice: {choice} "
                            f"Hash: {bet.bet_trx_block_hash} "
                            f"Second chance probability: {bonus['chance']}% "
                            f"Random number: {random_number * 100} "
                            f"Won amount: {second_chance_trx} TRX")
                        break

                # SECOND CHANCE LOST
                if not second_chance_win:
                    bet.bet_won = "false"
                    logging.info(
                        f"Job {bet_addr58} - "
                        f"SECOND CHANCE WON: {bet.bet_won} "
                        f"Choice: {choice} "
                        f"Hash: {bet.bet_trx_block_hash}")

        block_link = f"[Block Explorer](https://tronscan.org/#/block/{bet.bet_trx_block})"

        # --------------- USER WON ---------------
        if bet.bet_won == "true":
            if second_chance_win:
                winnings_trx = second_chance_trx
                winnings_sun = tron.toSun(winnings_trx)

                msg = self.get_resource("won_second.md")
            else:
                leverage = self._LEVERAGE[len(choice)]
                winnings_sun = int(bet.usr_amount * leverage)
                winnings_trx = tron.fromSun(winnings_sun)

                msg = self.get_resource("won.md")

            bet.pay_amount = winnings_sun

            msg = msg.replace("{{winnings}}", str(winnings_trx))
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{last_char}}", last_char)
            msg = msg.replace("{{chars}}", choice)
            msg = msg.replace("{{hash}}", bet.bet_trx_block_hash)
            msg = msg.replace("{{charswin}}", bet.bet_trx_block_hash[-1:])

            log_msg = msg.replace("\n", "")
            logging.info(f"Job {bet_addr58} - MSG: {log_msg}")

            # Pay winning amount if not done yet
            if not bet.pay_trx_id:
                try:
                    if second_chance_win:
                        params = dict()
                        params["private_key"] = self.config.get("bonus_privkey")
                        params["default_address"] = Address.from_private_key(params["private_key"])["base58"]

                        # Initiate wallet for bonus payments
                        bonus_tron = Tron(**params)

                        # Send funds from bonus wallet to user address
                        send_user = bonus_tron.trx.send(from_hex, float(winnings_trx))
                    else:
                        # Send funds from bot wallet to user address
                        send_user = self.get_tron().trx.send(from_hex, float(winnings_trx))

                    # An error was returned
                    if "code" in send_user and "message" in send_user:
                        raise Exception(send_user["message"])

                    bet.pay_trx_id = send_user["transaction"]["txID"]

                    if second_chance_win:
                        logging.info(f"Job {bet_addr58} - Send from Bonus to User: {send_user}")
                    else:
                        logging.info(f"Job {bet_addr58} - Send from Bot to User: {send_user}")
                except Exception as e:
                    logging.error(f"Job {bet_addr58} - Can't send from Bot to User: {e}")

                    if "Cannot transfer TRX to the same account" in str(e):
                        logging.info(f"Job {bet_addr58} - Ending job")
                        self.notify(f"Bet {bet_addr58} - {e}")
                        job.schedule_removal()

                    return

            # Determine path for winning animation
            if second_chance_win:
                image_path = os.path.join(self.get_res_path(), self._SECOND_CHANCE_DIR, str(second_chance_trx))
            else:
                image_path = os.path.join(self.get_res_path(), self._WON_DIR)

        # --------------- BOT WON ---------------
        else:
            bet.pay_amount = 0
            bet.pay_trx_id = "-"

            msg = self.get_resource("lost.md")
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{last_char}}", last_char)
            msg = msg.replace("{{chars}}", choice)
            msg = msg.replace("{{hash}}", bet.bet_trx_block_hash)
            msg = msg.replace("{{charswin}}", bet.bet_trx_block_hash[-1:])

            log_msg = msg.replace("\n", "")
            logging.info(f"Job {bet_addr58} - MSG: {log_msg}")

            # Determine path for loosing animation
            image_path = os.path.join(self.get_res_path(), self._LOST_DIR)

        # --------------- General ---------------

        # Check if we already sent funds from generated wallet to bot wallet
        if not bet.rtn_trx_id:
            try:
                # Send funds from generated address to bot address
                send_bot = tron.trx.send(bot_addr, amo)

                # An error was returned
                if "code" in send_bot and "message" in send_bot:
                    raise Exception(send_bot["message"])

                logging.info(f"Job {bet_addr58} - Send from Generated to Bot: {send_bot}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't send from Generated to Bot: {e}")
                return

            bet.rtn_trx_id = send_bot["transaction"]["txID"]

        job.schedule_removal()
        logging.info(f"Job {bet_addr58} - Scheduled job for removal")

        # Randomly determine image to show to user
        image_choice = random.choice(os.listdir(image_path))
        image_final = os.path.join(image_path, image_choice)

        logging.info(f"Job {bet_addr58} - Chose image to show: {image_final}")

        message = None

        # Let user know about outcome
        with open(image_final, "rb") as picture:
            try:
                message = bot.send_animation(
                    chat_id=update.message.chat_id,
                    animation=picture,
                    caption=msg,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                    reply_to_message_id=update.message.message_id)
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Couldn't send outcome message: {e}")

        if bet.bet_won == "false":
            if message:
                if bot.get_chat(update.message.chat_id).type == Chat.PRIVATE:
                    remove_time = self.config.get("private_remove_after")
                else:
                    remove_time = self.config.get("public_remove_after")

                if message:
                    self.run_job(
                        self._remove_losses,
                        datetime.now() + timedelta(seconds=remove_time),
                        context=f"{message.chat_id}_{message.message_id}")

        # Remove messages after betting address isn't valid anymore
        self.remove_messages(bot, msg1, msg2, bet_addr58)

        # Inform admins that user won with second chance
        if second_chance_win:
            if update.effective_user.username:
                u = f"@{update.effective_user.username}"
            else:
                u = update.effective_user.first_name

            msg = f"User {u} just won {second_chance_trx} TRX by second chance"
            self.notify(msg)

        logging.info(f"Job {bet_addr58} - Ending job")

    def remove_messages(self, bot, msg1, msg2, bet_addr58):
        try:
            chat_id1 = msg1.chat_id
            msg_id1 = msg1.message_id
            bot.delete_message(chat_id=chat_id1, message_id=msg_id1)
            logging.info(f"Job {bet_addr58} - Removed betting message 1")

            chat_id2 = msg2.chat_id
            msg_id2 = msg2.message_id
            bot.delete_message(chat_id=chat_id2, message_id=msg_id2)
            logging.info(f"Job {bet_addr58} - Removed betting message 2")
        except Exception as e:
            logging.warning(f"Job {bet_addr58} - Couldn't remove message: {e}")


class DBBet:

    def __init__(self, bet: Bet, address, chars, user_id):
        sql = bet.get_resource("insert_ignore.sql")
        bet.execute_sql(sql, address, chars, user_id)

        sql = bet.get_resource("select_bet.sql")
        res = bet.execute_sql(sql, address)

        self.bet = bet

        self.bet_address = res["data"][0][0]  # Can only be read
        self.bet_chars = res["data"][0][1]  # Can only be read
        self.usr_id = res["data"][0][2]  # Can only be read
        self.usr_address = res["data"][0][3]
        self.usr_amount = res["data"][0][4]
        self.bet_trx_id = res["data"][0][5]
        self.bet_trx_block = res["data"][0][6]
        self.bet_trx_block_hash = res["data"][0][7]
        self.bet_won = res["data"][0][8]
        self.pay_amount = res["data"][0][9]
        self.pay_trx_id = res["data"][0][10]
        self.date_time = res["data"][0][11]
        self.rtn_trx_id = res["data"][0][12]

    @property
    def usr_address(self):
        return self.__usr_address

    @usr_address.setter
    def usr_address(self, new_value):
        sql = self.get_sql("usr_address")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__usr_address = new_value

    @property
    def usr_amount(self):
        return self.__usr_amount

    @usr_amount.setter
    def usr_amount(self, new_value):
        sql = self.get_sql("usr_amount")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__usr_amount = new_value

    @property
    def bet_trx_id(self):
        return self.__bet_trx_id

    @bet_trx_id.setter
    def bet_trx_id(self, new_value):
        sql = self.get_sql("bet_trx_id")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__bet_trx_id = new_value

    @property
    def bet_trx_block(self):
        return self.__bet_trx_block

    @bet_trx_block.setter
    def bet_trx_block(self, new_value):
        sql = self.get_sql("bet_trx_block")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__bet_trx_block = new_value

    @property
    def bet_trx_block_hash(self):
        return self.__bet_trx_block_hash

    @bet_trx_block_hash.setter
    def bet_trx_block_hash(self, new_value):
        sql = self.get_sql("bet_trx_block_hash")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__bet_trx_block_hash = new_value

    @property
    def bet_won(self):
        return self.__bet_won

    @bet_won.setter
    def bet_won(self, new_value):
        sql = self.get_sql("bet_won")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__bet_won = new_value

    @property
    def pay_amount(self):
        return self.__pay_amount

    @pay_amount.setter
    def pay_amount(self, new_value):
        sql = self.get_sql("pay_amount")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__pay_amount = new_value

    @property
    def pay_trx_id(self):
        return self.__pay_trx_id

    @pay_trx_id.setter
    def pay_trx_id(self, new_value):
        sql = self.get_sql("pay_trx_id")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__pay_trx_id = new_value

    @property
    def rtn_trx_id(self):
        return self.__rtn_trx_id

    @rtn_trx_id.setter
    def rtn_trx_id(self, new_value):
        sql = self.get_sql("rtn_trx_id")
        self.bet.execute_sql(sql, new_value, self.bet_address)
        self.__rtn_trx_id = new_value

    def get_sql(self, variable):
        return f"UPDATE bets SET {variable} = ? WHERE bet_address = ?"

    def is_complete(self):
        return None not in vars(self).values()
