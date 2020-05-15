import psutil

from trxbetbot.plugin import TrxBetBotPlugin


class Debug(TrxBetBotPlugin):

    @TrxBetBotPlugin.threaded
    @TrxBetBotPlugin.send_typing
    def execute(self, bot, update, args):
        print(psutil.Process().open_files())
