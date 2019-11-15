import logging

from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


class Start(TrxBetBotPlugin):

    ABOUT_FILE = "about.md"

    def __enter__(self):
        if not self.table_exists("users"):
            sql = self.get_resource("create_users.sql")
            self.execute_sql(sql)
        return self

    @TrxBetBotPlugin.threaded
    def execute(self, bot, update, args):
        user = update.effective_user
        data = self.insert_user(user)
        logging.info(f"Insert User: {user} {data}")

        update.message.reply_text(
            text=self.get_resource(self.ABOUT_FILE),
            parse_mode=ParseMode.MARKDOWN)

    def insert_user(self, user):
        user_id = user.id
        username = user.username
        first_name = user.first_name
        last_name = user.last_name
        language = user.language_code

        exists = self.get_resource("user_exists.sql")
        if self.execute_sql(exists, user_id)["data"][0][0] == 1:
            return "User already exists"

        insert = self.get_resource("insert_user.sql")
        return self.execute_sql(insert, user_id, username, first_name, last_name, language)

