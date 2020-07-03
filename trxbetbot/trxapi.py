import os
import random
import logging
import trxbetbot.constants as con

from tronapi import Tron, constants
from tronapi.manager import TronManager
from trxbetbot.config import ConfigManager as Cfg


class TRXAPI(Tron):

    cfg = Cfg(os.path.join(con.DIR_CFG, con.FILE_CFG))

    def __init__(self, check=False, **kwargs):
        super().__init__(**kwargs)
        self.kwargs = kwargs
        self.set_server()

        if check and not self.is_available():
            self.find_server()

    def set_server(self, host=None):
        if host:
            full_node = host
            solidity_node = host
            event_server = host
        else:
            # Get default API server from config
            full_node = self.cfg.get("tron", "full_node")
            solidity_node = self.cfg.get("tron", "solidity_node")
            event_server = self.cfg.get("tron", "event_server")

        if full_node and not full_node.lower().startswith("https://"):
            full_node = "https://" + full_node
        if solidity_node and not solidity_node.lower().startswith("https://"):
            solidity_node = "https://" + solidity_node
        if event_server and not event_server.lower().startswith("https://"):
            event_server = "https://" + event_server

        if full_node:
            self.kwargs["full_node"] = full_node
        if solidity_node:
            self.kwargs["solidity_node"] = solidity_node
        if event_server:
            self.kwargs["event_server"] = event_server

        self._refresh()

    def _refresh(self):
        self.kwargs.setdefault('full_node', constants.DEFAULT_NODES['full_node'])
        self.kwargs.setdefault('solidity_node', constants.DEFAULT_NODES['solidity_node'])
        self.kwargs.setdefault('event_server', constants.DEFAULT_NODES['event_server'])

        self.manager = TronManager(self, dict(
            full_node=self.kwargs.get('full_node'),
            solidity_node=self.kwargs.get('solidity_node'),
            event_server=self.kwargs.get('event_server')))

    def is_available(self):
        status = self.is_connected()
        return True if all(v is True for v in status.values()) else False

    def find_server(self, retry=3):
        # Get server list from config
        hosts = self.cfg.get("tron", "server_list")
        hosts = ["https://" + x for x in hosts if not x.lower().startswith("https://")]

        current_host = self.kwargs["full_node"]

        connected = False
        for i in range(retry):
            # Choose random server
            new_host = random.choice(hosts)
            if new_host is not current_host:
                self.set_server(new_host)
                if self.is_available():
                    connected = True
                    break

        if not connected:
            self.set_server()
            logging.error("Not possible to connect to TRON API")
