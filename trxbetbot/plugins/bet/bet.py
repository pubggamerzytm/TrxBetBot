import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


# TODO: Add limit check
class Bet(TrxBetBotPlugin):
    """
    Workflow:
    1) Create wallet address and save it to database table 'addresses'
    2) ...
    """

    tron_grid = Trongrid()

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
        if len(args) != 1:
            update.message.reply_text(self.get_usage(), parse_mode=ParseMode.MARKDOWN)
            return

        chars = set(args[0])
        count = len(chars)

        if not self.contains_all(chars):
            msg = f"{emo.ERROR} You can only bet on one or more of these characters `{con.VALID_CHARS}`"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        if count > 15:
            msg = f"{emo.ERROR} Max characters to bet on is {len(con.VALID_CHARS)-1}"
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
        chance = count / len(con.VALID_CHARS) * 100
        leverage = con.LEVERAGE[len(chars)]

        # TODO: Add approximate waiting time
        msg = self.get_resource("betting.md")
        msg = msg.replace("{{choice}}", choice)
        msg = msg.replace("{{count}}", str(count))
        msg = msg.replace("{{chance}}", str(chance))
        msg = msg.replace("{{min}}", str(con.TRX_MIN))
        msg = msg.replace("{{max}}", str(con.TRX_MAX))
        msg = msg.replace("{{leverage}}", str(leverage))
        logging.info(msg.replace("\n", ""))

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        update.message.reply_text(f"`{account.address.base58}`", parse_mode=ParseMode.MARKDOWN)

        # Save bet details to database
        sql = self.get_resource("insert_bet.sql")
        self.execute_sql(sql, account.address.base58, choice, update.effective_user.id)

        context = {"tron": tron, "chars": chars, "update": update}
        self.repeat_job(self.check_incoming, 5, context=context)

    def contains_all(self, chars):
        """ Check if characters in 'chars' are all valid characters """
        return 0 not in [c in con.VALID_CHARS for c in chars]

    # TODO: Add try catch and finally to avoid job being not removed
    # TODO: Add timer to terminate job after longer time
    def check_incoming(self, bot, job):
        tron = job.context["tron"]
        chars = job.context["chars"]
        update = job.context["update"]

        bet_addr = tron.default_address
        bet_addr58 = bet_addr["base58"]

        balance = tron.trx.get_balance()

        if balance == 0:
            logging.info(f"Job {bet_addr58} - Balance: 0")
            return

        job.schedule_removal()

        amount = tron.fromSun(balance)
        logging.info(f"Job {bet_addr58} - Balance: {amount} TRX")

        transactions = self.tron_grid.get_trx_info_by_account(bet_addr.hex, only_to=True)
        logging.info(f"Job {bet_addr58} - Transactions: {transactions}")

        txid = from_hex = from_base58 = None
        for trx in transactions["data"]:
            value = trx["raw_data"]["contract"][0]["parameter"]["value"]

            if "asset_name" not in value:
                txid = trx["txID"]
                from_hex = value["owner_address"]
                from_base58 = Address().from_hex(from_hex)

        if not txid or not from_hex:
            # TODO: Display error
            pass

        info = tron.trx.get_transaction_info(txid)
        block_nr = info["blockNumber"]
        block = tron.trx.get_block(block_nr)
        block_hash = block["blockID"]
        last_char = block_hash[-1:]

        logging.info(f"Job {bet_addr58} - "
                     f"TXID: {txid} - "
                     f"Sender: {from_base58} - "
                     f"Block: {block} - "
                     f"Block Hash: {block_hash} - "
                     f"")

        bot_addr = self.get_tron().default_address.hex
        bet_won = last_char in chars

        # TODO: Add link to explorer when sending message to user

        # USER WON
        if bet_won:
            leverage = con.LEVERAGE[len(chars)]
            winnings = float(amount) * float(leverage)  # TODO: Change to amount so that i can save it

            # TODO: Export to resources
            msg = f"YOU WON {winnings} TRX!\n\n" \
                  f"Block Hash: `{block_hash}`\n" \
                  f"Winning Character: `{last_char}`\n" \
                  f"Your Characters: `{chars}`"

            log_msg = msg.replace("\n", "")
            logging.info(f"Job {bet_addr58} - MSG: {log_msg}")

            # Send funds from bot address to user address
            send_user = self.get_tron().trx.send(from_hex, winnings)
            logging.info(f"Job {bet_addr58} - Bot to User: {send_user}")

            # Send funds from betting address to bot address
            send_bot = tron.trx.send(bot_addr, amount)
            logging.info(f"Job {bet_addr58} - Generated to Bot: {send_bot}")

        # BOT WON
        else:
            amount = float(amount)

            # TODO: Export to resources
            msg = f"More luck next time!\n\n" \
                  f"Block Hash: `{block_hash}`\n" \
                  f"Winning Character: `{last_char}`\n" \
                  f"Your Characters: `{chars}`"

            logging.info(f"Job {bet_addr58} - MSG: {msg}")

            # Send funds from betting address to bot address
            send_bot = tron.trx.send(bot_addr, amount)
            logging.info(f"Job {bet_addr58} - Generated to Bot: {send_bot}")

        # Save betting results to database
        sql = self.get_resource("insert_result.sql")
        # TODO: Include trx_id
        self.execute_sql(sql, from_base58, balance, txid, block_nr, block_hash, bet_won, amount, send_bot)

        # Let user know about outcome
        update.message.reply_text(msg)
        logging.info(f"Job {bet_addr58} - Ending job")
