import  os
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

    # Betting
    VALID_CHARS = "0123456789abcdef"
    LEVERAGE = {1: 15.2, 2: 7.6, 3: 5.06, 4: 3.8, 5: 3.04, 6: 2.53, 7: 2.17, 8: 1.9,
                9: 1.68, 10: 1.52, 11: 1.38, 12: 1.26, 13: 1.16, 14: 1.08, 15: 1.01}

    WON_DIR = "won"
    LOST_DIR = "lost"

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
            msg = f"{emo.ERROR} You can only bet on one or more of these characters `{self.VALID_CHARS}`"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        if count > 15:
            msg = f"{emo.ERROR} Max characters to bet on is {len(self.VALID_CHARS)-1}"
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
        chance = count / len(self.VALID_CHARS) * 100
        leverage = self.LEVERAGE[len(chars)]

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
        return 0 not in [c in self.VALID_CHARS for c in chars]

    def scan_balance(self, bot, job):
        tron = job.context["tron"]
        start = job.context["start"]
        choice = job.context["choice"]
        update = job.context["update"]

        bet_addr = tron.default_address
        bet_addr58 = bet_addr["base58"]

        msg1 = job.context["msg1"]
        msg2 = job.context["msg2"]

        # Retrieve time in seconds to scan the balance
        time_frame = int(self.config.get("stop_check"))

        # Check if time limit for balance scanning is reached
        if (start + time_frame) < time.time():
            logging.info(f"Job {bet_addr58} - Ending job because {time_frame} seconds are over")
            # Stop repeating job since we reached max time frame to scan for a balance
            job.schedule_removal()

            # Remove messages after betting address isn't valid anymore
            self.remove_messages(bot, msg1, msg2, bet_addr58)
            return

        try:
            # Get balance (in "Sun") of generated address
            balance = tron.trx.get_balance()
        except Exception as e:
            logging.error(f"Job {bet_addr58} - Can't retrieve balance: {e}")
            self.notify(e)
            return

        # Check if balance is still 0. If yes, rerun job in specified interval
        if balance == 0:
            logging.info(f"Job {bet_addr58} - Balance: 0")
            return

        amount = tron.fromSun(balance)
        logging.info(f"Job {bet_addr58} - Balance: {amount} TRX")

        try:
            transactions = self.tron_grid.get_trx_info_by_account(bet_addr.hex, only_to=True)
            logging.info(f"Job {bet_addr58} - Transactions: {transactions}")
        except Exception as e:
            logging.error(f"Job {bet_addr58} - Can't retrieve transaction: {e}")
            self.notify(e)
            return

        trx_balance = trx_amount = 0
        trx_id = from_hex = from_base58 = None

        for trx in transactions["data"]:
            value = trx["raw_data"]["contract"][0]["parameter"]["value"]

            if "asset_name" not in value:
                trx_id = trx["txID"]

                from_hex = value["owner_address"]
                from_base58 = (Address().from_hex(from_hex)).decode("utf-8")

                trx_balance = value["amount"]
                trx_amount = tron.fromSun(trx_balance)
                break

        if not trx_id or not from_hex:
            msg = f"{emo.ERROR} Can't determine transaction ID or user wallet address: {bet_addr58}"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(msg)
            self.notify(msg)
            return

        amo = float(trx_amount)
        min = self.config.get("min_trx")
        max = self.config.get("max_trx")

        if amo > max or amo < min:
            msg = f"{emo.ERROR} Balance ({amo} TRX) is not inside min ({min} TRX) and max ({max} " \
                  f"TRX) boundaries. Whole amount will be returned to the wallet it was sent from."

            logging.info(msg)

            try:
                # Send funds from betting address to original address
                send = tron.trx.send(from_hex, amo)
                logging.info(f"Job {bet_addr58} - Trx from Generated to Original: {send}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't send: {e}")
                self.notify(e)
                return

            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        try:
            info = tron.trx.get_transaction_info(trx_id)
        except Exception as e:
            logging.error(f"Job {bet_addr58} - Can't retrieve transaction info: {e}")
            self.notify(e)
            return

        if "blockNumber" not in info:
            return

        block_nr = info["blockNumber"]

        try:
            block = tron.trx.get_block(block_nr)
        except Exception as e:
            logging.error(f"Job {bet_addr58} - Can't retrieve block info: {e}")
            self.notify(e)
            return

        block_hash = block["blockID"]
        last_char = block_hash[-1:]

        logging.info(f"Job {bet_addr58} - "
                     f"TXID: {trx_id} - "
                     f"Sender: {from_base58} - "
                     f"Block: {block} - "
                     f"Block Hash: {block_hash} - ")

        bot_addr = self.get_tron().default_address.hex
        bet_won = last_char in choice

        winnings_sun = win_trx_id = None

        block_link = f"[Block Explorer](https://tronscan.org/#/block/{block_nr})"

        # --------------- USER WON ---------------
        if bet_won:
            leverage = self.LEVERAGE[len(choice)]
            winnings_sun = int(trx_balance * leverage)
            winnings_trx = tron.fromSun(winnings_sun)

            msg = self.get_resource("won.md")
            msg = msg.replace("{{winnings}}", str(winnings_trx))
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{last_char}}", last_char)
            msg = msg.replace("{{chars}}", choice)

            log_msg = msg.replace("\n", "")
            logging.info(f"Job {bet_addr58} - MSG: {log_msg}")

            try:
                # Send funds from bot address to user address
                send_user = self.get_tron().trx.send(from_hex, float(winnings_trx))
                logging.info(f"Job {bet_addr58} - Trx from Bot to User: {send_user}")
            except Exception as e:
                logging.error(f"Job {bet_addr58} - Can't send from BOT to USER: {e}")
                self.notify(e)
                return

            win_trx_id = send_user["transaction"]["txID"]

            # Determine winning animation path
            image_path = os.path.join(self.get_res_path(), self.WON_DIR)

        # --------------- BOT WON ---------------
        else:
            msg = self.get_resource("lost.md")
            msg = msg.replace("{{explorer}}", block_link)
            msg = msg.replace("{{last_char}}", last_char)
            msg = msg.replace("{{chars}}", choice)

            log_msg = msg.replace("\n", "")
            logging.info(f"Job {bet_addr58} - MSG: {log_msg}")

            # Determine loosing animation path
            image_path = os.path.join(self.get_res_path(), self.LOST_DIR)

        # --------------- General ---------------

        job.schedule_removal()
        logging.info(f"Job {bet_addr58} - Scheduled job for removal")

        # Save betting results to database
        sql = self.get_resource("update_bet.sql")
        self.execute_sql(
            sql,
            from_base58,
            balance,
            trx_id,
            block_nr,
            block_hash,
            str(bet_won),
            winnings_sun,
            win_trx_id,
            bet_addr58)

        logging.info(f"Job {bet_addr58} - Updated bet data in database")

        try:
            # Send funds from betting address to bot address
            send_bot = tron.trx.send(bot_addr, amo)
            logging.info(f"Job {bet_addr58} - Trx from Generated to Bot: {send_bot}")
        except Exception as e:
            logging.error(f"Job {bet_addr58} - Can't send from BETTING to BOT: {e}")
            self.notify(e)
            return

        # Randomly determine image to show to user
        image_choice = random.choice(os.listdir(image_path))
        image_final = os.path.join(image_path, image_choice)

        logging.info(f"Job {bet_addr58} - Chose image to show: {image_final}")

        # Let user know about outcome
        with open(image_final, "rb") as picture:
            message = bot.send_animation(
                chat_id=update.message.chat_id,
                animation=picture,
                caption=msg,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True)

        if not bet_won:
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
