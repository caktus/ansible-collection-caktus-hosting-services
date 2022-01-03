import logging
import requests
import yaml
import sys
import argparse

logger = logging.getLogger("statuscake")

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
        if self.response.status_code == 200:
            logger.debug("All uptime checks in StatusCake: %s", self.response.json()['data'])
            for test in self.response.json()["data"]:
                if test["name"] == self.data["name"]:
                    logger.debug(f"Fetched data: {test}")
                    return test

    def create(self):
        if "test_type" not in self.data:
            self.data["test_type"] = "HTTP"
        if "check_rate" not in self.data:
            self.data["check_rate"] = 300
        self._request("post", self.url, data=self.data)

    def update(self, item_id):
        if "test_type" not in self.data:
            self.data["test_type"] = "HTTP"
        if "check_rate" not in self.data:
            self.data["check_rate"] = 300
        self._request("put", f"{self.url}/{item_id}", data=self.data)

    def save(self):
        fetch_data = self.fetch()
        logger.debug(f"Does '{self.data['name']}' exists in StatusCake? {bool(fetch_data)}.")
        if not fetch_data:
            self.create()
            logger.info(f"A new test for {self.data['name']} was created.")
        if fetch_data:
            self.update(fetch_data["id"])
            logger.info(f"The test for '{fetch_data['name']}' was updated.")



if __name__ == '__main__':
    # argparse argument
    parser = argparse.ArgumentParser(description="change file if congfig.yml is not an argument")
    parser.add_argument("--file", metavar='file', type=str, default='config.yml', help="enter filename if not using config.yml")
    parser.add_argument("--verbose", action="store_true", help="increase output verbosity")
    args = parser.parse_args()
    parser_file = args.file

    # Logging config
    formatter = logging.Formatter("%(levelname)s %(asctime)s %(name)s %(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    
    data_loaded = yaml.safe_load(open(parser_file, 'r'))

    for uptime_test in data_loaded["uptime_tests"]:
        if uptime_test['state'] == 'present' and uptime_test['name']:
            logger.info(uptime_test["name"])
            logger.info(uptime_test["website_url"])
            test = UptimeTest(api_key=data_loaded['api_key'], **uptime_test)
            test.save()