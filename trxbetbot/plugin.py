import os
import sqlite3
import logging
import inspect
import threading
import trxbetbot.constants as c
import trxbetbot.emoji as emo

from trxbetbot.trxapi import TRXAPI
from pathlib import Path
from telegram import ChatAction, Chat
from trxbetbot.config import ConfigManager
from trxbetbot.tgbot import TelegramBot


# TODO: Add properties where needed
class TrxBetBotPlugin:

    def __init__(self, tg_bot: TelegramBot):
        self._tgb = tg_bot

        # Create access to global config
        self.global_config = self._tgb.config

        # Create access to plugin config
        cfg_path = os.path.join(self.get_cfg_path(), f"{self.get_name()}.json")
        self.config = ConfigManager(cfg_path)

    def __enter__(self):
        """ This method gets executed before the plugin gets loaded.
        Make sure to return 'self' if you override it """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """ This method gets executed after the plugin gets loaded """
        pass

    def execute(self, bot, update, args):
        """ Override this to be executed after command gets triggered """
        method = inspect.currentframe().f_code.co_name
        msg = f"Method '{method}' not implemented for plugin '{self.get_name()}'"
        logging.warning(msg)

    def get_usage(self, replace: dict = None):
        """ Return how to use the command """
        usage = self.get_resource(f"{self.get_name()}.md")

        if usage:
            usage = usage.replace("{{handle}}", self.get_handle())

            if replace:
                for placeholder, value in replace.items():
                    usage = usage.replace(placeholder, str(value))

            return usage

        return None

    def get_handle(self):
        """ Return the command string that triggers the plugin """
        return self.config.get("handle")

    def get_category(self):
        """ Return the category of the plugin for the 'help' command """
        return self.config.get("category")

    def get_description(self):
        """ Return the description of the plugin """
        return self.config.get("description")

    def get_plugins(self):
        """ Return a list of all active plugins """
        return self._tgb.plugins

    def get_jobs(self):
        """ Return a tuple with all currently active jobs """
        return self._tgb.job_queue.jobs()

    def get_job(self, name=None):
        """ Return the periodic job with the given name or
        None if 'interval' is not set in plugin config """

        name = self.get_name() if not name else name
        jobs = self._tgb.job_queue.get_jobs_by_name(name)

        if not jobs or len(jobs) < 1:
            return None

        return jobs[0]

    # TODO: Maybe better set unique identifier as name?
    def repeat_job(self, callback, interval, first=0, context=None, name=None):
        """ Logic that gets executed periodically """
        self._tgb.job_queue.run_repeating(
            callback,
            interval,
            first=first,
            context=context,
            name=name if name else self.get_name())

    # TODO: Maybe better set unique identifier as name?
    def run_job(self, callback, when, context=None, name=None):
        """ Logic that gets executed once """
        self._tgb.job_queue.run_once(
            callback,
            when,
            context=context,
            name=name if name else self.get_name())

    def add_handler(self, handler, group=0):
        self._tgb.dispatcher.add_handler(handler, group=group)

    def add_plugin(self, module_name):
        """ Enable a plugin """
        return self._tgb.add_plugin(module_name)

    def remove_plugin(self, module_name):
        """ Disable a plugin """
        return self._tgb.remove_plugin(module_name)

    def get_tron(self) -> TRXAPI:
        return self._tgb.tron

    def get_global_resource(self, filename):
        """ Return the content of the given file
        from the global 'resource' directory """

        path = os.path.join(os.getcwd(), c.DIR_RES, filename)

        try:
            with open(path, "r", encoding="utf8") as f:
                return f.read()
        except Exception as e:
            logging.error(e)
            self.notify(e)
            return None

    # TODO: Maybe give the option to only check filename without extension
    def get_resource(self, filename, plugin=""):
        """ Return the content of the given file from
        the 'resource' directory of the plugin """
        path = os.path.join(self.get_res_path(plugin), filename)

        try:
            with open(path, "r", encoding="utf8") as f:
                return f.read()
        except Exception as e:
            logging.error(e)
            self.notify(e)
            return None

    def execute_global_sql(self, sql, *args):
        """ Execute raw SQL statement on the global
        database and return the result if there is one """

        res = {"success": None, "data": None}

        # Check if database usage is enabled
        if not self.global_config.get("database", "use_db"):
            res["data"] = "Database disabled"
            res["success"] = False
            return res

        timeout = self.global_config.get("database", "timeout")
        db_timeout = timeout if timeout else 5

        db_path = os.path.join(os.getcwd(), c.DIR_DAT, c.FILE_DAT)

        try:
            # Create directory if it doesn't exist
            directory = os.path.dirname(db_path)
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            res["data"] = str(e)
            res["success"] = False
            logging.error(e)
            self.notify(e)

        con = None
        cur = None

        try:
            con = sqlite3.connect(db_path, timeout=db_timeout)
            cur = con.cursor()
            cur.execute(sql, args)
            con.commit()

            res["data"] = cur.fetchall()
            res["success"] = True
        except Exception as e:
            res["data"] = str(e)
            res["success"] = False
            logging.error(e)
            self.notify(e)
        finally:
            if cur:
                cur.close()
            if con:
                con.close()

            return res

    # TODO: Describe how arguments can be used
    def execute_sql(self, sql, *args, plugin="", db_name=""):
        """ Execute raw SQL statement on database for given
        plugin and return the result if there is one """

        res = {"success": None, "data": None}

        # Check if database usage is enabled
        if not self.global_config.get("database", "use_db"):
            res["data"] = "Database disabled"
            res["success"] = False
            return res

        timeout = self.global_config.get("database", "timeout")
        db_timeout = timeout if timeout else 5

        if db_name:
            if not db_name.lower().endswith(".db"):
                db_name += ".db"
        else:
            if plugin:
                db_name = plugin + ".db"
            else:
                db_name = self.get_name() + ".db"

        if plugin:
            plugin = plugin.lower()
            data_path = self.get_dat_path(plugin=plugin)
            db_path = os.path.join(data_path, db_name)
        else:
            db_path = os.path.join(self.get_dat_path(), db_name)

        try:
            # Create directory if it doesn't exist
            directory = os.path.dirname(db_path)
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            res["data"] = str(e)
            res["success"] = False
            logging.error(e)
            self.notify(e)

        con = None
        cur = None

        try:
            con = sqlite3.connect(db_path, timeout=db_timeout)
            cur = con.cursor()
            cur.execute(sql, args)
            con.commit()

            res["data"] = cur.fetchall()
            res["success"] = True
        except Exception as e:
            res["data"] = str(e)
            res["success"] = False
            logging.error(e)
            self.notify(e)
        finally:
            if cur:
                cur.close()
            if con:
                con.close()

            return res

    def global_table_exists(self, table_name):
        """ Return TRUE if given table exists in global database, otherwise FALSE """
        db_path = os.path.join(os.getcwd(), c.DIR_DAT, c.FILE_DAT)

        if not Path(db_path).is_file():
            return False

        con = sqlite3.connect(db_path)
        cur = con.cursor()
        exists = False

        statement = self.get_global_resource("table_exists.sql")

        try:
            if cur.execute(statement, [table_name]).fetchone():
                exists = True
        except Exception as e:
            logging.error(e)
            self.notify(e)

        con.close()
        return exists

    def table_exists(self, table_name, plugin="", db_name=""):
        """ Return TRUE if given table exists, otherwise FALSE """
        if db_name:
            if not db_name.lower().endswith(".db"):
                db_name += ".db"
        else:
            if plugin:
                db_name = plugin + ".db"
            else:
                db_name = self.get_name() + ".db"

        if plugin:
            db_path = os.path.join(self.get_dat_path(plugin=plugin), db_name)
        else:
            db_path = os.path.join(self.get_dat_path(), db_name)

        if not Path(db_path).is_file():
            return False

        con = sqlite3.connect(db_path)
        cur = con.cursor()
        exists = False

        statement = self.get_global_resource("table_exists.sql")

        try:
            if cur.execute(statement, [table_name]).fetchone():
                exists = True
        except Exception as e:
            logging.error(e)
            self.notify(e)

        con.close()
        return exists

    def get_name(self):
        """ Return the name of the current plugin """
        return type(self).__name__.lower()

    def get_res_path(self, plugin=""):
        """ Return path of resource directory for this plugin """
        if not plugin:
            plugin = self.get_name()
        return os.path.join(c.DIR_SRC, c.DIR_PLG, plugin, c.DIR_RES)

    def get_cfg_path(self, plugin=""):
        """ Return path of configuration directory for this plugin """
        if not plugin:
            plugin = self.get_name()
        return os.path.join(c.DIR_SRC, c.DIR_PLG, plugin, c.DIR_CFG)

    def get_dat_path(self, plugin=""):
        """ Return path of data directory for this plugin """
        if not plugin:
            plugin = self.get_name()
        return os.path.join(c.DIR_SRC, c.DIR_PLG, plugin, c.DIR_DAT)

    def get_plg_path(self, plugin=""):
        """ Return path of current plugin directory """
        if not plugin:
            plugin = self.get_name()
        return os.path.join(c.DIR_SRC, c.DIR_PLG, plugin)

    def plugin_available(self, plugin_name):
        """ Return TRUE if the given plugin is enabled or FALSE otherwise """
        for plugin in self.get_plugins():
            if plugin.get_name() == plugin_name.lower():
                return True
        return False

    def notify(self, some_input):
        """ All admins in global config will get a message with the given text.
         Primarily used for exceptions but can be used with other inputs too. """

        if self.global_config.get("admin", "notify_on_error"):
            for admin in self.global_config.get("admin", "ids"):
                try:
                    msg = f"{emo.ALERT} Admin Notification {emo.ALERT}\n{some_input}"
                    self._tgb.updater.bot.send_message(admin, msg)
                except Exception as e:
                    error = f"Not possible to notify admin id '{admin}'"
                    logging.error(f"{error}: {e}")
        return some_input

    @staticmethod
    def threaded(fn):
        """ Decorator for methods that have to run in their own thread """
        def _threaded(*args, **kwargs):
            thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
            thread.start()

            return thread
        return _threaded

    # TODO: Change this so that the entry in the config is not needed
    @classmethod
    def private(cls, func):
        """ Decorator for methods that need to be run in a private chat with the bot """
        def _private(self, bot, update, **kwargs):
            if self.config.get("private"):
                if bot.get_chat(update.message.chat_id).type == Chat.PRIVATE:
                    return func(self, bot, update, **kwargs)

        return _private

    @classmethod
    def send_typing(cls, func):
        """ Decorator for sending typing notification in the Telegram chat """
        def _send_typing(self, bot, update, **kwargs):
            if update.message:
                user_id = update.message.chat_id
            elif update.callback_query:
                user_id = update.callback_query.message.chat_id
            else:
                logging.warning(f"No user ID - {update}")
                return func(self, bot, update, **kwargs)

            try:
                bot.send_chat_action(
                    chat_id=user_id,
                    action=ChatAction.TYPING)
            except:
                pass

            return func(self, bot, update, **kwargs)
        return _send_typing

    @classmethod
    def owner(cls, func):
        """
        Decorator that executes the method only if the user is an bot admin.

        The user ID that triggered the command has to be in the ["admin"]["ids"]
        list of the global config file 'config.json' or in the ["admins"] list
        of the currently used plugin config file.
        """

        def _owner(self, bot, update, **kwargs):
            user_id = update.effective_user.id

            admins_global = self.global_config.get("admin", "ids")
            if admins_global and isinstance(admins_global, list):
                if user_id in admins_global:
                    return func(self, bot, update, **kwargs)

            admins_plugin = self.config.get("admins")
            if admins_plugin and isinstance(admins_plugin, list):
                if user_id in admins_plugin:
                    return func(self, bot, update, **kwargs)

        return _owner

    @classmethod
    def dependency(cls, func):
        """ Decorator that executes a method only if the mentioned
        plugins in the config file of the current plugin are enabled """

        def _dependency(self, bot, update, **kwargs):
            dependencies = self.config.get("dependency")

            if dependencies and isinstance(dependencies, list):
                plugins = [p.get_name() for p in self.get_plugins()]

                for dependency in dependencies:
                    if dependency.lower() not in plugins:
                        return

            return func(self, bot, update, **kwargs)
        return _dependency
