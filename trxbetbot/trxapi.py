import os
import random
import logging
import trxbetbot.constants as con

from tronapi import Tron
from trxbetbot.config import ConfigManager as Cfg


class TRXAPI(Tron):

    cfg = Cfg(os.path.join(con.DIR_CFG, con.FILE_CFG))

    def __init__(self, **kwargs):
        self.kwargs = kwargs

        if not self.kwargs or not self.kwargs["full_node"]:
            full_node = self.cfg.get("tron", "full_node")
            solidity_node = self.cfg.get("tron", "solidity_node")
            event_server = self.cfg.get("tron", "event_server")

            if full_node:
                kwargs["full_node"] = full_node
            if solidity_node:
                kwargs["solidity_node"] = solidity_node
            if event_server:
                kwargs["event_server"] = event_server

        super().__init__(**self.kwargs)

        if kwargs["check"]:
            self.check_server()

    def check_server(self):
        status = self.manager.is_connected()
        if not all(value is True for value in status.values()):
            servers = self.cfg.get("tron", "server_list")
            current_server = self.kwargs["full_node"]

            for i in range(3):
                new_server = random.choice(servers)
                if new_server is not current_server:
                    host = new_server
                    break

            # TODO: How to set this?
            host = host if host.startswith("https://") else "https://" + host
            logging.info(f"New TRON API host set: {host}")
