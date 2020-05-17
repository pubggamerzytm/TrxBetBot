import logging

from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin


# TODO: Do it dynamically
class Multiplier(TrxBetBotPlugin):

    INFO_FILE = "info.md"

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        info = self.get_resource(self.INFO_FILE)
        #info.replace("{{multibet}}", )
        #info.replace("{{multiwin}}", )

        message = update.message.reply_text(
            text=info,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True)

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