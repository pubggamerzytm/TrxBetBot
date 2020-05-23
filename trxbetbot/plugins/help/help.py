import logging
from collections import OrderedDict

from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin


class Help(TrxBetBotPlugin):

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        categories = OrderedDict()

        for p in self.get_plugins():
            if p.get_category() and p.get_description():
                des = f"/{p.get_handle()} - {p.get_description()}"

                if p.get_category() not in categories:
                    categories[p.get_category()] = [des]
                else:
                    categories[p.get_category()].append(des)

        msg = "*Available commands*\n\n"

        for category in sorted(categories):
            msg += f"*{category}*\n"

            for cmd in sorted(categories[category]):
                msg += f"{cmd}\n"

            msg += "\n"

        message = update.message.reply_text(
            text=msg,
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
