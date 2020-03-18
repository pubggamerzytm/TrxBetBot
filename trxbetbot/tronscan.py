import json
import requests

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


class Tronscan:

    __API_URL_BASE = "https://apilist.tronscan.org/api/"

    def __init__(self, api_base_url=__API_URL_BASE):
        self.api_base_url = api_base_url
        self.request_timeout = 60

        self.session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[502, 503, 504])
        self.session.mount('http://', HTTPAdapter(max_retries=retries))

    def __request(self, url):
        try:
            response = self.session.get(url, timeout=self.request_timeout)
            content = json.loads(response.content.decode("utf-8"))
            response.raise_for_status()
            return content
        except Exception:
            try:
                raise ValueError(content)
            except UnboundLocalError:
                pass
            raise

    def __api_url_params(self, api_url, params):
        if params:
            api_url += '?'
            for key, value in params.items():
                api_url += "{0}={1}&".format(key, value)
            api_url = api_url[:-1]
        return api_url

    def get_transactions_for(self, address):
        api_url = f"{self.api_base_url}transaction"
        api_url = self.__api_url_params(api_url, {"address": address})
        return self.__request(api_url)
