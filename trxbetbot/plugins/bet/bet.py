import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


# TODO: Is it possible to have foreign key from another database? for address
# TODO: Add leverage to message
# TODO: Add limit check
class Bet(TrxBetBotPlugin):
    """
    Workflow:
    1) Create address and save it to
    """

    tron_grid = Trongrid()

    def __enter__(self):
        if not self.table_exists("addresses"):
            sql = self.get_resource("create_addresses.sql")
            self.execute_sql(sql)
        if not self.table_exists("bets"):
            sql = self.get_resource("create_bets.sql")
            self.execute_sql(sql)
        if not self.table_exists("results"):
            sql = self.get_resource("create_results.sql")
            self.execute_sql(sql)
        if not self.table_exists("payouts"):
            sql = self.get_resource("create_payouts.sql")
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

        # TODO: Test
        # Save generated address to database
        sql = self.get_resource("insert_address.sql")
        self.execute_sql(sql, account.address.base58, account.private_key)

        # Check if generated address is valid
        if not bool(tron.isAddress(account.address.hex)):
            msg = f"{emo.ERROR} Generated wallet is not valid"
            update.message.reply_text(msg)
            return

        generated = {"pubkey": account.public_key,
                     "privkey": account.private_key,
                     "addr_hex": account.address.hex,
                     "addr_base58": account.address.base58}

        logging.info(f"TRX address created {generated}")

        choice = "".join(chars)
        chance = count / len(con.VALID_CHARS) * 100

        # TODO: Include winning amount
        msg = self.get_resource("betting.md")
        msg = msg.replace("{{choice}}", "".join(sorted(choice)))
        msg = msg.replace("{{count}}", str(count))
        msg = msg.replace("{{chance}}", str(chance))
        msg = msg.replace("{{min}}", str(con.TRX_MIN))
        msg = msg.replace("{{max}}", str(con.TRX_MAX))
        msg = msg.replace("{{address}}", account.address.base58)
        logging.info(msg.replace("\n", ""))

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        # TODO: Test
        user = update.effective_user

        sql = self.get_resource("insert_bet.sql")
        self.execute_sql(sql, count.address.base58, chars, user.id)

        context = {"tron": tron, "chars": chars, "update": update}
        self.repeat_job(self.check_incomming, 5, context=context)

    def contains_all(self, chars):
        """ Check if characters in 'chars' are all valid characters """
        return 0 not in [c in con.VALID_CHARS for c in chars]

    # TODO: Add try catch and finally to avoid job being not removed
    # TODO: Add timer to terminate job after longer time
    def check_incomming(self, bot, job):
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

        # USER WON
        if last_char in chars:
            lev = con.LEVERAGE[len(chars)]
            win = float(amount) * float(lev)

            # TODO: Export to resources
            msg = f"YOU WON {amount} TRX!\n\n" \
                  f"Block Hash: `{block_hash}`\n" \
                  f"Winning Character: `{last_char}`\n" \
                  f"Your Characters: `{chars}`"

            logging.info(f"Job {bet_addr58} - MSG: {msg}")

            # Send funds from bot address to user address
            send_user = self.get_tron().trx.send(from_hex, win)
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

            send_bot = tron.trx.send(bot_addr, amount)
            logging.info(f"Job {bet_addr58} - Generated to Bot: {send_bot}")

        update.message.reply_text(msg)
        logging.info(f"Job {bet_addr58} - Ending job")
