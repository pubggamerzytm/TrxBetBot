import time
import logging
import trxbetbot.emoji as emo

from tronapi import Tron
from tronapi.main import Address
from telegram import ParseMode
from trxbetbot.plugin import TrxBetBotPlugin
from trxbetbot.trongrid import Trongrid


class Tip(TrxBetBotPlugin):

    def execute(self, bot, update, args):
        pass
