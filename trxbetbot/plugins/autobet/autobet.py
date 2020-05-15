import zlib
import pickle
import logging

import trxbetbot.emoji as emo
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


# TODO: What happens if i delete the message that initiated an auto-bet?
# TODO: Issue that some betting messages will not be overwritten?
class Autobet(TrxBetBotPlugin):

    AUTOBET = "autobet"

    def __enter__(self):
        if not self.table_exists("autobet"):
            sql = self.get_resource("create_autobet.sql")
            self.execute_sql(sql)

        sql = self.get_resource("select_autobets.sql")
        res = self.execute_sql(sql)

        if not res["success"]:
            msg = f"{emo.ERROR} Not possible to read bets for /{self.get_name()}"
            logging.error(res)
            self.notify(msg)

        for autobet in res["data"]:
            context = {
                "update": pickle.loads(zlib.decompress(autobet[3])),
                "bet_chars": autobet[1]
            }

            self.repeat_job(self.auto_bet, self.config.get("interval"), context=context, name=autobet[0])

        return self

    @TrxBetBotPlugin.private
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        usr_id = update.effective_user.id

        if len(args) == 1 and args[0].lower() == "stop":
            sql = self.get_resource("exists_autobet.sql")
            if self.execute_sql(sql, usr_id)["data"][0][0] == 1:
                sql = self.get_resource("delete_autobet.sql")
                self.execute_sql(sql, update.effective_user.id)

                job = self.get_job(name=usr_id)
                if job: job.schedule_removal()

                msg = f"{emo.INFO} Stopped automatic betting"
            else:
                msg = f"{emo.INFO} Automatic betting not active"

            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        if len(args) != 2:
            d = {"{{interval}}": self.config.get("interval")}
            update.message.reply_text(self.get_usage(replace=d), parse_mode=ParseMode.MARKDOWN)
            return

        bet_chars = args[0]
        bet_amount = args[1]

        try:
            float(bet_amount)
        except:
            msg = f"{emo.ERROR} Second argument needs to be the amount of TRX to bet"
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        logging.info(f"Update: {update}")

        # Identify this as an autobet and add the amount of TRX to bet
        update.effective_message.caption = f"{self.AUTOBET}"

        updt = zlib.compress(pickle.dumps(update))

        # Check if there is already an auto-bet for this user
        sql = self.get_resource("exists_autobet.sql")
        if self.execute_sql(sql, usr_id)["data"][0][0] == 1:
            sql = self.get_resource("update_autobet.sql")
            self.execute_sql(sql, bet_chars, bet_amount, updt, usr_id)

            msg = f"{emo.INFO} Auto-Betting data for {self.get_name()} updated..."
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return
        else:
            sql = self.get_resource("insert_autobet.sql")
            self.execute_sql(sql, usr_id, bet_chars, bet_amount, updt)

        context = {
            "update": update,
            "bet_chars": bet_chars
        }

        msg = f"{emo.MONEY_FACE} Starting Auto-Betting..."
        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        # Repeating job for auto-send
        logging.info("Creating repeating job for auto-bet")
        self.repeat_job(self.auto_bet, self.config.get("interval"), context=context, name=usr_id)

    def auto_bet(self, bot, job):
        update = job.context["update"]
        bet_chars = job.context["bet_chars"]

        # Find '/bet' plugin
        for plugin in self._tgb.plugins:
            if plugin.get_name() == "bet":
                plugin.execute(bot, update, args=[bet_chars])
                return
