import logging
import trxbetbot.emoji as emo
import trxbetbot.constants as con

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


# TODO: Add leverage to message
# TODO: Add limit check
# TODO: Add logging output
class Bet(TrxBetBotPlugin):

    tron_grid = Trongrid()

    def __enter__(self):
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

        chance = count / len(con.VALID_CHARS) * 100

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

        # TODO: Clean up
        logging.info('Generated account: ')
        logging.info('- Private Key: ' + account.private_key)
        logging.info('- Public Key: ' + account.public_key)
        logging.info('- Address: ')
        logging.info('-- Base58: ' + account.address.base58)
        logging.info('-- Hex: ' + account.address.hex)

        choice = "".join(chars)

        msg = f"You are betting that the hash of the block that contains your " \
              f"transaction ends with one of these characters: `{choice}`\n\n" \
              f"You chose {count} characters. The chance that one of them " \
              f"is the last character of the block hash is {chance}%.\n\n" \
              f"Send between {con.TRX_MIN} and {con.TRX_MAX} TRX to this address\n\n" \
              f"`{account.address.base58}`\n\n" \

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        context = {"tron": tron, "chars": chars, "update": update}
        self.repeat_job(self.check_incomming, 5, context=context)

    def contains_all(self, chars):
        return 0 not in [c in con.VALID_CHARS for c in chars]

    # TODO: Add try catch and finally to avoid job being not removed
    def check_incomming(self, bot, job):
        tron = job.context["tron"]
        chars = job.context["chars"]
        update = job.context["update"]

        balance = tron.trx.get_balance()

        import calendar
        import time
        print(calendar.timegm(time.gmtime()))

        if balance != 0:
            job.schedule_removal()

            amount = tron.fromSun(balance)
            print(f"Coins received: {amount} TRX\n\n")

            to_hex = tron.default_address.hex
            to_base58 = Address().from_hex(to_hex)
            transactions = self.tron_grid.get_trx_info_by_account(to_hex, only_to=True)
            print(transactions)

            for trx in transactions["data"]:
                value = trx["raw_data"]["contract"][0]["parameter"]["value"]
                if "asset_name" not in value:
                    from_hex = value["owner_address"]
                    from_base58 = Address().from_hex(from_hex)
                    print(from_base58)

                    txid = trx["txID"]
                    print(txid)

            info = tron.trx.get_transaction_info(txid)
            print(info)

            block_nr = info["blockNumber"]

            block = tron.trx.get_block(block_nr)
            print(block)

            block_hash = block["blockID"]
            print(block_hash)

            last_char = block_hash[-1:]
            print(last_char)

            bot_addr = self.get_tron().default_address.hex

            if last_char in chars:
                lev = con.LEVERAGE[len(chars)]
                win = float(amount) * float(lev)
                msg = f"YOU WON {amount} TRX!\n\n" \
                      f"Block Hash: `{block_hash}`\n" \
                      f"Winning Character: `{last_char}`\n" \
                      f"Your Characters: `{chars}`"

                # Send funds from bot address to user address
                send = self.get_tron().trx.send(from_hex, win)
                print(send)

                # Send funds from betting address to bot address
                send = tron.trx.send(bot_addr, amount)
                print(send)
            else:
                amount = float(amount)
                msg = f"More luck next time!\n\n" \
                      f"Block Hash: `{block_hash}`\n" \
                      f"Winning Character: `{last_char}`\n" \
                      f"Your Characters: `{chars}`"
                send = tron.trx.send(bot_addr, amount)
                print(send)

            update.message.reply_text(msg)
