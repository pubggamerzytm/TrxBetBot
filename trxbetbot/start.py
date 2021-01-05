import os
import json
import logging
import trxbetbot.constants as con
import sqlite3

from argparse import ArgumentParser
from trxbetbot.tgbot import TelegramBot
from trxbetbot.config import ConfigManager as Cfg
from logging.handlers import TimedRotatingFileHandler
from trxbetbot.web import FlaskAppWrapper


# TODO: In case database will be removed on the fly, check if user & address is available and if not, create them
class TrxBetBot:

    def __init__(self):
        # Parse command line arguments
        self.args = self._parse_args()

        # Set up logging
        self._init_logger()

        # Read global config file and create Telegram bot
        self.cfg = Cfg(os.path.join(con.DIR_CFG, con.FILE_CFG))
        self.tgb = TelegramBot(self.cfg, self._get_bot_token(), self._get_bot_wallet())

    def _parse_args(self):
        """ Parse command line arguments """
        desc = "Telegram Tron Bot For Betting"
        parser = ArgumentParser(description=desc)

        # Save logfile
        parser.add_argument(
            "--no-log",
            dest="savelog",
            action="store_false",
            help="don't save log-files",
            required=False,
            default=True)

        # Log level
        parser.add_argument(
            "-log",
            dest="loglevel",
            type=int,
            choices=[0, 10, 20, 30, 40, 50],
            help="disabled, debug, info, warning, error, critical",
            default=30,
            required=False)

        # Module log level
        parser.add_argument(
            "-mlog",
            dest="mloglevel",
            help="set log level for a module",
            default=None,
            required=False)

        # Bot token
        parser.add_argument(
            "1309504600:AAEeBquYnfrdKOqGd_1kBUwsPengw42bTHo",
            dest="1309504600:AAEeBquYnfrdKOqGd_1kBUwsPengw42bTHo",
            help="1309504600:AAEeBquYnfrdKOqGd_1kBUwsPengw42bTHo",
            required=False,
            default=None)

        # Bot token via input
        parser.add_argument(
            "1309504600:AAEeBquYnfrdKOqGd_1kBUwsPengw42bTHo",
            dest="input_token",
            action="store_true",
            help="1309504600:AAEeBquYnfrdKOqGd_1kBUwsPengw42bTHo",
            required=False,
            default=False)

        # Bot TRX private key
        parser.add_argument(
            "48a96c836659399dc0e49db829b922b0de620345935602e4e8255ea4f4dbe821",
            dest="48a96c836659399dc0e49db829b922b0de620345935602e4e8255ea4f4dbe821",
            help="48a96c836659399dc0e49db829b922b0de620345935602e4e8255ea4f4dbe821",
            required=False,
            default=None)

        # Bot TRX private key via input
        parser.add_argument(
            "--input-privkey",
            dest="input_privkey",
            action="store_true",
            help="48a96c836659399dc0e49db829b922b0de620345935602e4e8255ea4f4dbe821",
            required=False,
            default=False)

        return parser.parse_args()

    # Configure logging
    def _init_logger(self):
        """ Initialize the console logger and file logger """
        logger = logging.getLogger()
        logger.setLevel(self.args.loglevel)

        log_file = os.path.join(con.DIR_LOG, con.FILE_LOG)
        log_format = "[%(asctime)s %(levelname)s %(filename)s:%(lineno)s %(funcName)s()] %(message)s"

        # Log to console
        console_log = logging.StreamHandler()
        console_log.setFormatter(logging.Formatter(log_format))
        console_log.setLevel(self.args.loglevel)

        logger.addHandler(console_log)

        # Save logs if enabled
        if self.args.savelog:
            # Create 'log' directory if not present
            log_path = os.path.dirname(log_file)
            if not os.path.exists(log_path):
                os.makedirs(log_path)

            file_log = TimedRotatingFileHandler(
                log_file,
                when="H",
                encoding="utf-8")

            file_log.setFormatter(logging.Formatter(log_format))
            file_log.setLevel(self.args.loglevel)

            logger.addHandler(file_log)

        # Set log level for specified modules
        if self.args.mloglevel:
            for modlvl in self.args.mloglevel.split(","):
                module, loglvl = modlvl.split("=")
                logr = logging.getLogger(module)
                logr.setLevel(int(loglvl))

    # Read bot token from file
    def _get_bot_token(self):
        """ Read Telegram bot token from config file or command line or input """
        if self.args.input_token:
            return input("Enter Telegram Bot Token: ")
        if self.args.token:
            return self.args.token

        token_path = os.path.join(con.DIR_CFG, con.FILE_TKN)

        try:
            if os.path.isfile(token_path):
                with open(token_path, "r", encoding="utf8") as file:
                    return json.load(file)["telegram"]
            else:
                exit(f"ERROR: No token file '{con.FILE_TKN}' found at '{token_path}'")
        except KeyError as e:
            cls_name = f"Class: {type(self).__name__}"
            logging.error(f"{repr(e)} - {cls_name}")
            exit("ERROR: Can't read bot token")

    def _get_bot_wallet(self):
        """ Read Tron bot wallet from config file or command line or input """
        if self.args.input_privkey:
            return input("Enter Tron Private Key For Bot: ")
        if self.args.privkey:
            return self.args.privkey

        token_path = os.path.join(con.DIR_CFG, con.FILE_TRX)

        try:
            if os.path.isfile(token_path):
                with open(token_path, "r", encoding="utf8") as file:
                    return json.load(file)["privkey"]
            else:
                exit(f"ERROR: No Tron wallet file '{con.FILE_TKN}' found at '{token_path}'")
        except KeyError as e:
            cls_name = f"Class: {type(self).__name__}"
            logging.error(f"{repr(e)} - {cls_name}")
            exit("ERROR: Can't read Tron wallet")

    def _get_bet(self, key):
        return self._get_data("bets", key)

    def _get_address(self, key):
        return self._get_data("addresses", key)

    def _get_data(self, table, key):
        path = os.path.dirname(os.path.realpath(__file__))
        path = os.path.join(path, "plugins", "bet", "data", "bet.db")

        if not os.path.isfile(path):
            return {"error": f"File doesn't exist: {path}"}

        connection = sqlite3.connect(path)
        cursor = connection.cursor()

        if key:
            column = "bet_address" if table == "bets" else "address"
            sql = f"SELECT * FROM {table} WHERE {column} = ?"
            cursor.execute(sql, [key])
        else:
            sql = f"SELECT * FROM {table}"
            cursor.execute(sql)

        connection.commit()
        data = cursor.fetchall()
        connection.close()
        return data

    def start(self):
        if self.cfg.get("webhook", "use_webhook"):
            self.tgb.bot_start_webhook()
        else:
            self.tgb.bot_start_polling()

        if self.cfg.get("web", "use_web"):
            password = self.cfg.get("web", "password")

            port = self.cfg.get("web", "port")
            a = FlaskAppWrapper(__name__, port)

            a.add_endpoint(
                endpoint='/',
                endpoint_name='/')

            a.add_endpoint(
                endpoint='/bet',
                endpoint_name='/bet',
                handler=self._get_bet,
                secret=password)

            a.add_endpoint(
                endpoint='/address',
                endpoint_name='/address',
                handler=self._get_address,
                secret=password)

            a.run()

        self.tgb.bot_idle()
