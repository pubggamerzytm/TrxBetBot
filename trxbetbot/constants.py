import os

TRX_MIN = 10
TRX_MAX = 10000

# Betting
VALID_CHARS = "0123456789abcdef"
LEVERAGE = {1: 15.2, 2: 7.6, 3: 5.06, 4: 3.8, 5: 3.04, 6: 2.53, 7: 2.17, 8: 1.9,
            9: 1.68, 10: 1.52, 11: 1.38, 12: 1.26, 13: 1.16, 14: 1.08, 15: 1.01}

# Project folders
DIR_SRC = os.path.basename(os.path.dirname(__file__))
DIR_RES = "resources"
DIR_PLG = "plugins"
DIR_CFG = "config"
DIR_LOG = "logs"
DIR_DAT = "data"
DIR_TMP = "temp"

# Project files
FILE_CFG = "config.json"
FILE_TKN = "token.json"
FILE_TRX = "wallet.json"
FILE_LOG = "trxbetbot.log"

# Max Telegram message length
MAX_TG_MSG_LEN = 4096
