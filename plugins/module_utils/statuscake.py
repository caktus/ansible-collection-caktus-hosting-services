import logging
import requests
import yaml
import argparse

logger = logging.getLogger(__name__)

class StatusCakeAPI:

    def __init__(self, api_key, **kwargs) -> None:
        self.api_key = api_key
        self.data = kwargs
        self.client = requests.Session()
        self.client.headers["Authorization"] = f"Bearer {self.api_key}"

    def full_url(self, path):
        return f"https://api.statuscake.com{path}"

    def _request(self, method, path, **kwargs):
        requests_method = getattr(self.client, method)
        response = requests_method(self.full_url(path), **kwargs)
        self.response = response
        return response


class UptimeTest(StatusCakeAPI):

    url = "/v1/uptime"

    def fetch(self):
        self._request("get", self.url)
        for test in self.response.json()['data']:
            if test["name"] == self.data["name"]:
                return test

    def add_key(self, key):
        return f"{self.url}/{key}"

    def update(self,):
        self._request("put", self.add_key())
        

    def save(self):
        # exists = self.fetch()
        # if exists:
            # self.update()
        # else:
            # self.create()
        pass



if __name__ == '__main__':

    # argparse argument
    parser = argparse.ArgumentParser(description="change file if congfig.yml is not an argument")
    parser.add_argument("--file", metavar='file', type=str, default='config.yml', help="enter filename if not using config.yml")
    args = parser.parse_args()

    file = args.file

    data_loaded = yaml.safe_load(open(file, 'r'))

    for uptime_test in data_loaded["uptime_tests"]:
        test = UptimeTest(api_key=data_loaded['api_key'], **uptime_test)
        test.fetch()
    print(data_loaded["uptime_tests"])
    # breakpoint()