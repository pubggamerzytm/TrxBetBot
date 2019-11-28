import logging
import trxbetbot.emoji as emo
import trxbetbot.utils as utl
import trxbetbot.constants as con

from tronapi import Tron
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


# TODO: Test with sending with and without fee
# TODO: Add examples to usage-files
class Tip(TrxBetBotPlugin):

    def __enter__(self):
        if not self.global_table_exists("tips"):
            sql = self.get_resource("create_tips.sql")
            self.execute_global_sql(sql)
        return self

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if len(args) != 2:
            update.message.reply_text(
                text=f"Usage:\n{self.get_usage()}",
                parse_mode=ParseMode.MARKDOWN)
            return

        amount = args[0]

        # Check if amount is valid
        try:
            float(amount)
        except:
            msg = f"{emo.ERROR} Provided amount is not valid"
            logging.info(f"{msg} - {update}")
            update.message.reply_text(msg)
            return

        to_username = args[1].replace("@", "")

        sql = self.get_resource("select_user.sql")
        res = self.execute_global_sql(sql, to_username)

        if not res["success"]:
            # TODO: show error
            return

        if not res["data"]:
            msg = f"{emo.ERROR} User @{to_username} doesn't have a wallet yet"
            logging.info(f"{msg} - {update}")
            update.message.reply_text(msg)
            return

        to_user_id = res["data"][0][0]
        to_address = res["data"][0][5]

        from_user_id = update.effective_user.id
        from_username = update.effective_user.username
        from_firstname = update.effective_user.first_name

        sql = self.get_global_resource("select_address.sql")
        res = self.execute_global_sql(sql, from_user_id)

        if not res["success"]:
            # TODO: show error
            return

        data = res["data"]

        if not data:
            msg = f"{emo.ERROR} You don't have a wallet yet. " \
                  f"Create one by talking to the bot @{bot.name}"
            logging.info(f"{msg} - {update}")
            update.message.reply_text(msg)
            return

        trx_kwargs = dict()
        trx_kwargs["private_key"] = data[0][2]
        trx_kwargs["default_address"] = data[0][1]

        tron = Tron(**trx_kwargs)

        balance = tron.trx.get_balance()
        available_amount = tron.fromSun(balance)

        # Check if address has enough balance
        if float(amount) > float(available_amount):
            msg = f"{emo.ERROR} Not enough funds. You balance is {available_amount} TRX"
            logging.info(f"{msg} - {data[0][1]} - {update}")
            update.message.reply_text(msg)
            return

        try:
            send = tron.trx.send(to_address, float(amount))

            if "transaction" not in send:
                logging.error(send)
                raise Exception("key 'transaction' not in send result")

            txid = send["transaction"]["txID"]

            explorer_link = f"https://tronscan.org/#/transaction/{txid}"
            msg = f"{emo.DONE} @{utl.esc_md(from_username)} tipped @{utl.esc_md(to_username)} with " \
                  f"`{amount}` TRX. View [Block Explorer]({explorer_link}) (wait ~1 minute)"

            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

            backslash = "\n"
            logging.info(f"{msg.replace(backslash, '')} - {update}")

            try:
                if from_username:
                    # Tipping user has a username
                    bot.send_message(
                        to_user_id,
                        f"You received `{amount}` TRX from @{from_username}",
                        parse_mode=ParseMode.MARKDOWN)
                else:
                    # Tipping user doesn't have a username
                    bot.send_message(
                        to_user_id,
                        f"You received `{amount}` TRX from @{from_firstname}",
                        parse_mode=ParseMode.MARKDOWN)
            except:
                logging.info(f"User {to_username} ({to_user_id}) couldn't be notified about tip")

            sent_amount = tron.toSun(amount)
            sql = self.get_resource("insert_tip.sql")
            self.execute_global_sql(sql, from_user_id, to_user_id, sent_amount)
        except Exception as e:
            msg = f"{emo.ERROR} Balance not sufficient. Try removing fee of {con.TRX_FEE} TRX"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            logging.error(e)
