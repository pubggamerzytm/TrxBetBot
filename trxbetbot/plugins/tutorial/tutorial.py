from telegram import ParseMode, Chat
from datetime import datetime, timedelta
from trxbetbot.plugin import TrxBetBotPlugin


class Tutorial(TrxBetBotPlugin):

    INFO_FILE = "info.md"

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        message = update.message.reply_text(
            text=self.get_resource(self.INFO_FILE),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True)

        if bot.get_chat(update.message.chat_id).type == Chat.PRIVATE:
            remove_time = self.config.get("private_remove_after")
        else:
            remove_time = self.config.get("public_remove_after")

        if message:
            self.repeat_job(
                self._remove_msg,
                0,
                datetime.now() + timedelta(seconds=remove_time),
                context=f"{message.chat_id}_{message.message_id}")

    def _remove_msg(self, bot, job):
        param_lst = job.context.split("_")
        chat_id = param_lst[0]
        msg_id = param_lst[1]

        bot.delete_message(chat_id=chat_id, message_id=msg_id)
        job.schedule_removal()
