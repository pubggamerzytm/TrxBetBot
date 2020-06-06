import zlib
import pickle
import logging
import trxbetbot.emoji as emo

from random import randrange
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin


class Automix(TrxBetBotPlugin):

    AUTOMIX = "automix"

    def __enter__(self):
        if not self.table_exists("automix"):
            sql = self.get_resource("create_automix.sql")
            self.execute_sql(sql)

        sql = self.get_resource("select_automixes.sql")
        res = self.execute_sql(sql)

        if not res["success"]:
            msg = f"{emo.ERROR} Not possible to read bets for /{self.get_name()}"
            logging.error(res)
            self.notify(msg)
            return self

        for automix in res["data"]:
            context = {
                "update": pickle.loads(zlib.decompress(automix[3])),
                "bet_chars": automix[1],
                "bet_amount": automix[2]
            }

            self.repeat_job(
                self.auto_mix,
                self.config.get("interval"),
                first=randrange(0, 60),
                context=context,
                name=f"{self.get_name()}_{automix[0]}")

        return self

    @TrxBetBotPlugin.private
    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        usr_id = update.effective_user.id

        if len(args) == 1 and args[0].lower() == "stop":
            sql = self.get_resource("exists_automix.sql")
            if self.execute_sql(sql, usr_id)["data"][0][0] == 1:
                sql = self.get_resource("delete_automix.sql")
                self.execute_sql(sql, update.effective_user.id)
                logging.info(f"Removed {self.get_name()} DB entry for user ID {usr_id}")

                job = self.get_job(name=f"{self.get_name()}_{str(usr_id)}")

                if job:
                    job.schedule_removal()
                    logging.info(f"Removed {self.get_name()} job for user ID {usr_id}")
                else:
                    logging.warning(f"No {self.get_name()} job for user ID {usr_id}")

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

        # Identify this as an automix and add the amount of TRX to bet
        update.effective_message.caption = f"{self.AUTOMIX}"

        updt = zlib.compress(pickle.dumps(update))

        # Check if there is already an auto-mix for this user ...
        sql = self.get_resource("exists_automix.sql")

        # ... if yes, update it
        if self.execute_sql(sql, usr_id)["data"][0][0] == 1:
            sql = self.get_resource("update_automix.sql")
            self.execute_sql(sql, bet_chars, bet_amount, updt, usr_id)

            logging.info(f"Updated {self.get_name()} for user ID {usr_id} - "
                         f"chars {bet_chars} - amount {bet_amount}")

            msg = f"{emo.INFO} Auto-Betting data for {self.get_name()} updated..."
            update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        # ... if not, insert it
        else:
            sql = self.get_resource("insert_automix.sql")
            self.execute_sql(sql, usr_id, bet_chars, bet_amount, updt)

            logging.info(f"Inserted {self.get_name()} for user ID {usr_id} - "
                         f"chars {bet_chars} - amount {bet_amount}")

        context = {
            "update": update,
            "bet_chars": bet_chars,
            "bet_amount": bet_amount
        }

        msg = f"{emo.MONEY_FACE} Starting Auto-Betting..."
        update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        logging.info(f"Creating repeating job for {self.get_name()} - {update}")

        # Repeating job for auto-send
        self.repeat_job(
            self.auto_mix,
            self.config.get("interval"),
            context=context,
            name=f"{self.get_name()}_{str(usr_id)}")

    def auto_mix(self, bot, job):
        update = job.context["update"]
        bet_chars = job.context["bet_chars"]
        bet_amount = job.context["bet_amount"]

        # Find '/mix' plugin
        for plugin in self._tgb.plugins:
            if plugin.get_name() == "mix":
                logging.info(f"Execute job {job.name} - chars {bet_chars} - amount {bet_amount}")
                plugin.execute(bot, update, args=[bet_chars, bet_amount])
                return
