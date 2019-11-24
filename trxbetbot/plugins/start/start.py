import logging

from tronapi import Tron
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


# TODO: Make username primary key, not user_id
class Start(TrxBetBotPlugin):

    ABOUT_FILE = "about.md"

    def __enter__(self):
        if not self.global_table_exists("users"):
            sql = self.get_resource("create_users.sql")
            self.execute_global_sql(sql)
        if not self.global_table_exists("addresses"):
            sql = self.get_resource("create_addresses.sql")
            self.execute_global_sql(sql)
        return self

    @TrxBetBotPlugin.threaded
    def execute(self, bot, update, args):
        user = update.effective_user

        exists = self.get_resource("user_exists.sql")
        if self.execute_global_sql(exists, user.id)["data"][0][0] == 1:
            return "User already exists"

        tron = Tron()
        account = tron.create_account
        address = account.address.base58
        privkey = account.private_key

        logging.info(f"Created Address: {address} - Private Key: {privkey} - Update: {update}")

        insert = self.get_resource("insert_address.sql")
        result = self.execute_global_sql(
            insert,
            user.id,
            address,
            privkey)

        logging.info(f"Insert Address: {user} {result}")

        insert = self.get_resource("insert_user.sql")
        result = self.execute_global_sql(
            insert,
            user.id,
            user.username,
            user.first_name,
            user.last_name,
            user.language_code,
            address)

        logging.info(f"Insert User: {user} {result}")

        update.message.reply_text(
            text=self.get_resource(self.ABOUT_FILE),
            parse_mode=ParseMode.MARKDOWN)
