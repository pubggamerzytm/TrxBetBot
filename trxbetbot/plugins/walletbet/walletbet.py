import trxbetbot.emoji as emo

from telegram import ParseMode, Chat
from trxbetbot.plugin import TrxBetBotPlugin


class Walletbet(TrxBetBotPlugin):

    @TrxBetBotPlugin.owner
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if update.effective_chat.type != Chat.PRIVATE:
            msg = f"{emo.ERROR} You can execute this command only in a private chat with the bot"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # Default number of days to fetch address data for
        days = 30

        if len(args) > 0:
            try:
                days = int(args[0])
            except:
                msg = f"{emo.ERROR} Parameter needs to be number of days"
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                return

        sql = self.get_resource("count_unique_addr.sql")
        res_bet = self.execute_sql(sql, f"-{days} day", plugin="bet")
        res_mix = self.execute_sql(sql, f"-{days} day", plugin="mix")
        res_win = self.execute_sql(sql, f"-{days} day", plugin="win")

        # Current data
        bet = len(res_bet['data'][0]) if res_bet['data'] else 0
        mix = len(res_mix['data'][0]) if res_mix['data'] else 0
        win = len(res_win['data'][0]) if res_win['data'] else 0
        total = bet + mix + win

        msg = f"*Users who have bet in last {days} days*\n\n" \
              f"`Bet   {bet}`\n" \
              f"`Mix   {mix}`\n" \
              f"`Win   {win}`\n\n" \
              f"`Total {total}`"

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
