import trxbetbot.emoji as emo

from telegram import ParseMode, Chat
from trxbetbot.plugin import TrxBetBotPlugin


class Trans(TrxBetBotPlugin):

    URL = "https://tronscan.org/#/address/"

    @TrxBetBotPlugin.owner
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if update.effective_chat.type != Chat.PRIVATE:
            msg = f"{emo.ERROR} You can execute this command only in a private chat with the bot"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        sql = self.get_resource("count_all.sql")
        res_bet = self.execute_sql(sql, plugin="bet")
        res_mix = self.execute_sql(sql, plugin="bet")
        res_win = self.execute_sql(sql, plugin="bet")

        print("BET", res_bet["data"][0][0])
        print("MIX", res_mix["data"][0][0])
        print("WIN", res_win["data"][0][0])
