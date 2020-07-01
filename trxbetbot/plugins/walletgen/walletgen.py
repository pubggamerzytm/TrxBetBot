import trxbetbot.emoji as emo

from telegram import ParseMode, Chat
from trxbetbot.plugin import TrxBetBotPlugin


class Walletgen(TrxBetBotPlugin):

    @TrxBetBotPlugin.owner
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        if update.effective_chat.type != Chat.PRIVATE:
            msg = f"{emo.ERROR} You can execute this command only in a private chat with the bot"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # Default number of days to fetch address data for
        days = 9999

        if len(args) > 0:
            try:
                days = int(args[0])
            except:
                msg = f"{emo.ERROR} Parameter needs to be number of days"
                update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
                return

        sql = self.get_resource("count_addr_date.sql")
        res_bet = self.execute_sql(sql, f"-{days} day", plugin="bet")
        res_mix = self.execute_sql(sql, f"-{days} day", plugin="mix")
        res_win = self.execute_sql(sql, f"-{days} day", plugin="win")
        res_global = self.execute_global_sql(sql, f"-{days} day")

        # Historic data
        h_bet = self.config.get("past_bet_addr")
        h_mix = self.config.get("past_mix_addr")
        h_win = self.config.get("past_win_addr")

        # Current data
        bet = res_bet['data'][0][0] + h_bet
        mix = res_mix['data'][0][0] + h_mix
        win = res_win['data'][0][0] + h_win
        usr = res_global['data'][0][0]
        total = bet + mix + win + usr

        msg = f"*Number of generated addresses*\n\n" \
              f"`Bet   {bet}`\n" \
              f"`Mix   {mix}`\n" \
              f"`Win   {win}`\n" \
              f"`Users {usr}`\n\n" \
              f"`Total {total}`"

        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
