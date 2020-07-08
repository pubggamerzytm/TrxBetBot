import os
import random
import logging
import trxbetbot.constants as con

from tronapi import Tron, constants
from tronapi.manager import TronManager
from trxbetbot.config import ConfigManager as Cfg


# TODO: If current API endpoint != default endpoint, try default first
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
            full_node = self.cfg.get("tron", "default_full_node")
            solidity_node = self.cfg.get("tron", "default_solidity_node")
            event_server = self.cfg.get("tron", "default_event_server")

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
        try:
            status = self.is_connected()
        except Exception as e:
            logging.error(f"TRON API: Not possible to connect: {e}")
            return False
        return True if all(v is True for v in status.values()) else False

    def find_server(self, retry=3):
        # Get server list from config
        full_node_list = self.cfg.get("tron", "full_node_list")
        solidity_node_list = self.cfg.get("tron", "solidity_node_list")

        current_host = self.kwargs["full_node"]

        connected = False
        for i in range(retry):
            # Choose random server
            new_host = random.choice(full_node_list)
            if new_host is not current_host:
                self.set_server(new_host)
                if self.is_available():
                    connected = True
                    break
                else:
                    logging.error(f"TRON API: Host #{i} not available: {new_host}")

        if not connected:
            self.set_server()
            logging.error("TRON API: Reset to default host")
