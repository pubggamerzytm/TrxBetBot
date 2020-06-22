import json
import requests

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


class Trongrid:

    __API_URL_BASE = "https://api.trongrid.io/v1/"

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

    def get_account(self, address):
        api_url = f"{self.api_base_url}accounts/{address}"
        return self.__request(api_url)
