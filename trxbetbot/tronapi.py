import random
import logging

from tronapi import Tron


class TronAPI:

    def __init__(self, connect=False, **kwargs):
        self.kwargs = self.choose_server(kwargs)
        self.tron = Tron(**self.kwargs)

    def choose_server(self, kwargs):
        if not kwargs["full_node"]:
            current_server = self.trx_kwargs["full_node"]
            servers = self.config.get("tron", "server_list")

            while True:
                new_server = random.choice(servers)
                if new_server is not current_server:
                    host = new_server
                    break

        host = host if host.lower().startswith("https://") else "https://" + host

        kwargs["full_node"] = host
        kwargs["solidity_node"] = host
        kwargs["event_server"] = host

        logging.info(f"New TRON API host set: {host}")

        return kwargs

    # TODO: Add 'while-do'
    def _(self, tron: Tron):
        """ Try to find a TRON API server that we can connect to """
        status = tron.manager.is_connected()
        if not all(value is True for value in status.values()):
            self._tgb.set_tron_server(tron)
        return tron
