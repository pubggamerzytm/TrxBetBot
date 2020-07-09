import os
import random
import logging
import trxbetbot.constants as con

from tronapi import Tron
from requests import Session
from trxbetbot.config import ConfigManager as Cfg
from requests.exceptions import ConnectionError, ReadTimeout


class TRXAPI(Tron):

    cfg = Cfg(os.path.join(con.DIR_CFG, con.FILE_CFG))

    def __init__(self, **kwargs):
        super().__init__(**self.enrich_kwargs(**kwargs))

    def enrich_kwargs(self, **kwargs):
        if "full_node" not in kwargs:
            full_node = self.cfg.get("tron", "default_full_node")
            if full_node:
                kwargs["full_node"] = full_node
        if "solidity_node" not in kwargs:
            solidity_node = self.cfg.get("tron", "default_solidity_node")
            if solidity_node:
                kwargs["solidity_node"] = solidity_node

        return kwargs

    def full_node_connected(self):
        data = {
            'method': 'get',
            'url': f'{self.manager.full_node.node_url}/wallet/getnowblock',
            'timeout': 1
        }

        return self._node_connected(data)

    def solidity_node_connected(self):
        data = {
            'method': 'get',
            'url': f'{self.manager.solidity_node.node_url}/walletsolidity/getnowblock',
            'timeout': 1
        }

        return self._node_connected(data)

    def _node_connected(self, data):
        try:
            response = Session().request(**data)
        except (ConnectionError, ReadTimeout):
            return False

        if not (200 <= response.status_code < 300):
            return False

        try:
            data = response.json()
        except ValueError:
            return False

        if 'blockID' in data or data == 'OK':
            return True

        return False

    def re(self, fun, *args, **kwargs):
        result = None

        try:
            return fun(*args, **kwargs)
        except Exception as e:
            logging.error(
                f"TRON API: Can't execute: {fun}({args}, {kwargs}) - "
                f"Result: {result} - "
                f"Error: {e} - "
                f"Changing nodes...")

            if not self.full_node_connected():
                self.change_full_node()
            if not self.solidity_node_connected():
                self.change_solidity_node()

            try:
                return fun(*args, **kwargs)
            except:
                logging.error(
                    f"TRON API: Can't execute: {fun}({args}, {kwargs}) - "
                    f"Result: {result} - "
                    f"Error: {e} - "
                    f"Giving up...")
                return None

    def change_full_node(self, retry=3):
        # Get server list from config
        full_nodes = self.cfg.get("tron", "full_node_list")

        for i in range(retry):
            # Choose random server
            new_node = random.choice(full_nodes)
            if new_node is not self.manager.full_node.node_url:
                self.manager.full_node.node_url = new_node
                if self.full_node_connected():
                    #self.cfg.set(new_node, "tron", "default_full_node")
                    logging.info(f"TRON API: Changed Full Node to {new_node}")
                    return
                else:
                    logging.warning(f"TRON API: Full Node #{i+1} not available: {new_node}")

        self.manager.full_node.node_url = self.enrich_kwargs(**{})["full_node"]
        logging.warning("TRON API: Reset Full Node to default")

    def change_solidity_node(self, retry=3):
        # Get server list from config
        solidity_nodes = self.cfg.get("tron", "solidity_node_list")

        for i in range(retry):
            # Choose random server
            new_node = random.choice(solidity_nodes)
            if new_node is not self.manager.solidity_node.node_url:
                self.manager.solidity_node.node_url = new_node
                if self.solidity_node_connected():
                    #self.cfg.set(new_node, "tron", "default_solidity_node")
                    logging.info(f"TRON API: Changed Solidity Node to {new_node}")
                    return
                else:
                    logging.warning(f"TRON API: Solidity Node #{i+1} not available: {new_node}")

        self.manager.full_node.node_url = self.enrich_kwargs(**{})["solidity_node"]
        logging.warning("TRON API: Reset Solidity Node to default")
