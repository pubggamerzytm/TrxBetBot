import trxbetbot.constants as con

from tronapi import Tron


class TRC20:

    # Smart Contracts
    SC = {
        "WIN": "TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7"
    }

    def send(self, ticker: str, tron: Tron, to_address: str, amount: float):
        cont_kwargs = dict()
        cont_kwargs["contract_address"] = tron.address.to_hex(self.SC[ticker.upper()])
        cont_kwargs["function_selector"] = "transfer(address,uint256)"
        cont_kwargs["fee_limit"] = tron.toSun(con.TRX_FEE)
        cont_kwargs["call_value"] = 0
        cont_kwargs["parameters"] = [
            {
                'type': 'address',
                'value': tron.address.to_hex(to_address)
            },
            {
                'type': 'uint256',
                'value': tron.toSun(amount)
            }
        ]

        try:
            # Create raw transaction
            raw_tx = tron.transaction_builder.trigger_smart_contract(**cont_kwargs)
            # Sign the raw transaction
            sig_tx = tron.trx.sign(raw_tx["transaction"])
            # Broadcast the signed transaction
            result = tron.trx.broadcast(sig_tx)

            return result
        except Exception as e:
            return {"error": e}