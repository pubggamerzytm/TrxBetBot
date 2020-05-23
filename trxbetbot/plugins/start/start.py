import logging

from tronapi import Tron
from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin


# FIXME: Do not save address in 'users' an 'addresses' DB
# only save it in addresses and foreign key is user_id or username
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

            # Update user details
            updusr = self.get_resource("update_user.sql")
            result = self.execute_global_sql(
                updusr,
                user.username,
                user.first_name,
                user.last_name,
                user.language_code,
                user.id)

            logging.info(f"Updated User: {user} {result}")

            sql = self.get_global_resource("select_address.sql")
            res = self.execute_global_sql(sql, user.id)

            if not res["success"]:
                msg = f"Something went wrong. Please contact @Wikioshi the owner of this bot"
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                return

            address = res["data"][0][1]

            logging.info(f"User already exists - Address: {address} - {update}")
        else:
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

        about = self.get_resource(self.ABOUT_FILE)
        about = about.replace("{{address}}", address)

        if user.username:
            about = about.replace("{{warning}}", "")
        else:
            warning = f"*ATTENTION! You need a username to be able to receive tips. Set one in " \
                      f"your Telegram profile and execute the /{self.get_handle()} command again*\n\n"
            about = about.replace("{{warning}}", warning)

        message = update.message.reply_text(about, parse_mode=ParseMode.MARKDOWN)

        if bot.get_chat(update.message.chat_id).type == Chat.PRIVATE:
            remove_time = self.config.get("private_remove_after")
        else:
            remove_time = self.config.get("public_remove_after")

        if message:
            self.run_job(
                self._remove_msg,
                datetime.now() + timedelta(seconds=remove_time),
                context=f"{message.chat_id}_{message.message_id}")

    def _remove_msg(self, bot, job):
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
