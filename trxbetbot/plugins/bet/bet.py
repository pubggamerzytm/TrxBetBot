import os
import time
import random
import logging
import trxbetbot.emoji as emo

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


class Bet(TrxBetBotPlugin):

    _WON_DIR = "won"
    _LOST_DIR = "lost"
    _VALID_CHARS = "0123456789abcdef"
    _LEVERAGE = {1: 15.2, 2: 7.6, 3: 5.06, 4: 3.8, 5: 3.04, 6: 2.53, 7: 2.17, 8: 1.9,
                 9: 1.68, 10: 1.52, 11: 1.38, 12: 1.26, 13: 1.16, 14: 1.08, 15: 1.01}

    tron_grid = Trongrid()

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
        if len(args) != 1:
            update.message.reply_text(self.get_usage(), parse_mode=ParseMode.MARKDOWN)
            return

        chars = set(args[0])
        count = len(chars)

        if not self.contains_all(chars):
            msg = f"{emo.ERROR} You can only bet on one or more of these characters `{self._VALID_CHARS}`"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        if count > 15:
            msg = f"{emo.ERROR} Max characters to bet on is {len(self._VALID_CHARS) - 1}"
            update.message.reply_text(msg)
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

        choice = "".join(sorted(chars))
        chance = count / len(self._VALID_CHARS) * 100
        leverage = self._LEVERAGE[len(chars)]

        min_trx = self.config.get("min_trx")
        max_trx = self.config.get("max_trx")

        msg = self.get_resource("betting.md")
        msg = msg.replace("{{choice}}", choice)
        msg = msg.replace("{{count}}", str(count))
        msg = msg.replace("{{chance}}", str(chance))
        msg = msg.replace("{{min}}", str(min_trx))
        msg = msg.replace("{{max}}", str(max_trx))
        msg = msg.replace("{{leverage}}", str(leverage))
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

        trx_balance = trx_amount = 0
        trx_id = from_hex = from_base58 = None

        # We already found a saved transaction
        if bet.bet_trx_id:
            trx_balance = bet.usr_amount
            trx_amount = tron.fromSun(trx_balance)
            trx_id = bet.bet_trx_id
            from_base58 = bet.usr_address
            from_hex = Address().to_hex(from_base58)
        else:
            try:
                transactions = self.tron_grid.get_trx_info_by_account(bet_addr.hex, only_to=True)
                logging.info(f"Job {bet_addr58} - Get Transactions: {transactions}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't retrieve transaction: {e}")
                return

            found = False
            for trx in reversed(transactions["data"]):
                value = trx["raw_data"]["contract"][0]["parameter"]["value"]

                # We check just for TRX
                if "asset_name" not in value:
                    trx_id = trx["txID"]
                    from_hex = value["owner_address"]
                    from_base58 = (Address().from_hex(from_hex)).decode("utf-8")
                    trx_balance = value["amount"]
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

        amo = float(trx_amount)
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
        if bet.bet_trx_block:
            block_nr = bet.bet_trx_block
        else:
            try:
                info = tron.trx.get_transaction_info(trx_id)
                logging.info(f"Job {bet_addr58} - Get Transaction Info: {info}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't retrieve transaction info: {e}")
                return

            if "blockNumber" not in info:
                logging.info(f"Job {bet_addr58} - Key 'blockNumber' not in info: {info}")
                return

            block_nr = info["blockNumber"]
            bet.bet_trx_block = block_nr

        # Check if we already know the block hash
        if bet.bet_trx_block_hash:
            block_hash = bet.bet_trx_block_hash
        else:
            try:
                block = tron.trx.get_block(block_nr)
                logging.info(f"Job {bet_addr58} - Get Block: {block}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't retrieve block info: {e}")
                return

            block_hash = block["blockID"]
            bet.bet_trx_block_hash = block_hash

        last_char = block_hash[-1:]

        logging.info(f"Job {bet_addr58} - "
                     f"TXID: {trx_id} - "
                     f"Sender: {from_base58} - "
                     f"Block: {block_nr} - "
                     f"Block Hash: {block_hash} - ")

        bot_addr = self.get_tron().default_address.hex

        # Check if we already know if the bet was won
        if bet.bet_won:
            bet_won = bet.bet_won
        else:
            bet_won = last_char in choice
            bet.bet_won = bet_won

        block_link = f"[Block Explorer](https://tronscan.org/#/block/{block_nr})"

        # --------------- USER WON ---------------
        if bet_won:
            leverage = self._LEVERAGE[len(choice)]
            winnings_sun = int(trx_balance * leverage)
            winnings_trx = tron.fromSun(winnings_sun)

            bet.pay_amount = winnings_sun

            msg = self.get_resource("won.md")
            msg = msg.replace("{{winnings}}", str(winnings_trx))
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{last_char}}", last_char)
            msg = msg.replace("{{chars}}", choice)

            log_msg = msg.replace("\n", "")
            logging.info(f"Job {bet_addr58} - MSG: {log_msg}")

            # Pay winning amount if not done yet
            if not bet.pay_trx_id:
                try:
                    # Send funds from bot address to user address
                    send_user = self.get_tron().trx.send(from_hex, float(winnings_trx))
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
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{last_char}}", last_char)
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

        if not bet_won:
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
