import os
import time
import random
import logging
import trxbetbot.emoji as emo

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.tronscan import Tronscan


class Bet(TrxBetBotPlugin):
    _WON_DIR = "won"
    _LOST_DIR = "lost"
    _VALID_CHARS = "123456789abcdef"

    tronscan = Tronscan()

    def __enter__(self):
        if not self.table_exists("addresses"):
            sql = self.get_resource("create_addresses.sql")
            self.execute_sql(sql)
        if not self.table_exists("bets"):
            sql = self.get_resource("create_bets.sql")
            self.execute_sql(sql)

        clean_losses = self.config.get("clean_losses")

        if clean_losses:
            # Create background job that removes messages related to losses
            self.repeat_job(self.remove_losses, clean_losses, first=clean_losses)

        return self

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        logging.info(f"{emo.INFO} {update}")

        if len(args) != 1:
            update.message.reply_text(self.get_usage(), parse_mode=ParseMode.MARKDOWN)
            return

        choice = args[0]
        preset = self.config.get("preset")

        if not str(len(choice)) in preset:
            keys = ' or '.join(list(preset.keys()))
            msg = f"{emo.ERROR} You need to provide {keys} characters and not {len(choice)}"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        if not self.contains_all(choice):
            msg = f"{emo.ERROR} Your bet can only include these characters: `{self._VALID_CHARS}`"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        preset = preset[str(len(choice))]
        if "min_trx" not in preset or "max_trx" not in preset or "leverage" not in preset:
            msg = f"{emo.ERROR} Wrong configuration in preset: {preset}"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(msg)
            self.notify(msg)
            return

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

        """ Calculate chance to win
        chance = 1
        for i in range(len(choice)):
            chance *= 1 / len(self._VALID_CHARS)
        chance *= 100
        """

        leverage = preset["leverage"]

        min_trx = preset["min_trx"]
        max_trx = preset["max_trx"]

        msg = self.get_resource("betting.md")
        msg = msg.replace("{{choice}}", choice)
        msg = msg.replace("{{chars}}", str(len(choice)))
        msg = msg.replace("{{factor}}", str(leverage))
        msg = msg.replace("{{min}}", str(min_trx))
        msg = msg.replace("{{max}}", str(max_trx))
        logging.info(msg.replace("\n", ""))

        msg1 = update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        msg2 = update.message.reply_text(f"`{account.address.base58}`", parse_mode=ParseMode.MARKDOWN)

        # Save bet details to database
        sql = self.get_resource("insert_bet.sql")
        self.execute_sql(sql, account.address.base58, choice, update.effective_user.id)

        first = self.config.get("check_start")
        check = self.config.get("balance_check")

        context = {
            "tron": tron,
            "choice": choice,
            "preset": preset,
            "update": update,
            "start": time.time(),
            "msg1": msg1,
            "msg2": msg2
        }

        self.repeat_job(self.scan_balance, check, first=first, context=context)

        logging.info(f"Initiated repeating job for {account.address.base58}")

    def remove_losses(self, bot, job):
        for msg in self.config.get("loss_messages"):
            try:
                bot.delete_message(chat_id=msg['chat_id'], message_id=msg['msg_id'])
                logging.info(f"Loss message removed: {msg}")
            except Exception as e:
                logging.warning(f"Cant delete message: {e}")
        self.config.set(list(), "loss_messages")

    def contains_all(self, chars):
        """ Check if characters in 'chars' are all valid characters """
        return 0 not in [c in self._VALID_CHARS for c in chars]

    def scan_balance(self, bot, job):
        tron = job.context["tron"]
        start = job.context["start"]
        choice = job.context["choice"]
        preset = job.context["preset"]
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

        # Check if we already found a saved transaction
        if not bet.bet_trx_id:
            try:
                transactions = self.tronscan.get_transactions_for(bet_addr58)
                logging.info(f"Job {bet_addr58} - Get Transactions: {transactions}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't retrieve transactions: {e}")
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

        min = preset["min_trx"]
        max = preset["max_trx"]

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

        # Determine if bet was won or not
        # But only if not already saved
        if bet.bet_won is None:
            bet.bet_won = str(bet.bet_trx_block_hash).lower().endswith(choice.lower())

        logging.info(f"Job {bet_addr58} - WON: {bet.bet_won} Choice: {choice} Hash: {bet.bet_trx_block_hash}")

        block_link = f"[Block Explorer](https://tronscan.org/#/block/{bet.bet_trx_block})"

        # --------------- USER WON ---------------
        if bet.bet_won:
            leverage = preset["leverage"]
            winnings_sun = int(bet.usr_amount * leverage)
            winnings_trx = tron.fromSun(winnings_sun)

            bet.pay_amount = winnings_sun

            msg = self.get_resource("won.md")
            msg = msg.replace("{{hash}}", bet.bet_trx_block_hash)
            msg = msg.replace("{{winnings}}", str(winnings_trx))
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{chars}}", choice)

            log_msg = msg.replace("\n", "")
            logging.info(f"Job {bet_addr58} - MSG: {log_msg}")

            # Pay winning amount if not done yet
            if not bet.pay_trx_id:
                try:
                    # Send funds from bot address to user address
                    send_user = self.get_tron().trx.send(from_hex, float(winnings_trx))

                    # An error was returned
                    if "code" in send_user and "message" in send_user:
                        raise Exception(send_user["message"])

                    logging.info(f"Job {bet_addr58} - Send from Bot to User: {send_user}")
                except Exception as e:
                    logging.error(f"Job {bet_addr58} - Can't send from Bot to User: {e}")

                    if "Cannot transfer TRX to the same account" in str(e):
                        logging.info(f"Job {bet_addr58} - Ending job")
                        self.notify(f"Bet {bet_addr58} - {e}")
                        job.schedule_removal()

                    return

                bet.pay_trx_id = send_user["transaction"]["txID"]

            # Determine path for winning animation
            image_path = os.path.join(self.get_res_path(), self._WON_DIR)

        # --------------- BOT WON ---------------
        else:
            bet.pay_amount = 0
            bet.pay_trx_id = "-"

            msg = self.get_resource("lost.md")
            msg = msg.replace("{{hash}}", bet.bet_trx_block_hash)
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{chars}}", choice)

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

        if not bet.bet_won:
            if message:
                # Save messages about lost bets so that they can be removed later
                msg_list = self.config.get("loss_messages")
                msg_list.append({"chat_id": message.chat_id, "msg_id": message.message_id})
                self.config.set(msg_list, "loss_messages")

        # Remove messages after betting address isn't valid anymore
        self.remove_messages(bot, msg1, msg2, bet_addr58)

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
