import logging
import requests
import yaml
import sys
import argparse

logger = logging.getLogger("statuscake")


class StatusCakeAPI:
    def __init__(self, api_key, state, log_file=None, **kwargs) -> None:
        self.api_key = api_key
        self.state = state
        self.id = None
        self.config = kwargs
        self.client = requests.Session()
        self.client.headers["Authorization"] = f"Bearer {self.api_key}"
        if log_file:
            logging.basicConfig(
                filename=log_file,
                format="%(asctime)s %(name)-22s %(levelname)-8s %(message)s",
                level=logging.DEBUG,
            )

    def full_url(self, path):
        return f"https://api.statuscake.com{path}"

    def _request(self, method, path, **kwargs):
        requests_method = getattr(self.client, method)
        response = requests_method(self.full_url(path), **kwargs)
        self.response = response
        return response


class UptimeTest(StatusCakeAPI):

    url = "/v1/uptime"

    def fetch_all(self):
        self._request("get", self.url)
        if self.response.status_code == 200:
            logger.debug(
                "All uptime checks in StatusCake: %s", self.response.json()["data"]
            )
            return self.response.json()["data"]
        return []

    def fetch(self):
        for test in self.fetch_all():
            if test["name"] == self.config["name"]:
                logger.debug(f"Fetched data: {test}")
                self.id = test["id"]
                return test

    def create(self):
        """
        Create an uptime test.
        https://www.statuscake.com/api/v1/#operation/create-uptime-test
        """
        if not self.id:
            if "test_type" not in self.config:
                self.config["test_type"] = "HTTP"
            if "check_rate" not in self.config:
                self.config["check_rate"] = 300
            self._request("post", self.url, data=self.config)
            if self.response.status_code == 201:
                self.id = int(self.response.json()["data"]["new_id"])
                logger.info(f"A new test for '{self.config['name']}' was created.")

    def update(self):
        """
        Update an uptime test.
        https://www.statuscake.com/api/v1/#operation/update-uptime-test
        """
        if self.id:
            self._request("put", f"{self.url}/{self.id}", data=self.config)
            if self.response.status_code == 204:
                logger.info(f"The test for '{self.config['name']}' was updated.")

    def delete(self):
        """
        Delete an uptime test.
        https://www.statuscake.com/api/v1/#operation/delete-uptime-test
        """
        if self.id:
            self._request("delete", f"{self.url}/{self.id}")
            if self.response.status_code == 204:
                logger.info(f"The test for '{self.config['name']}' was deleted")

    def sync(self):
        fetch_data = self.fetch()
        logger.info(
            f"Does '{self.config['name']}' exists in StatusCake? {bool(fetch_data)}."
        )
        # If test is 'present' update or create. Else delete.
        if self.state == "present":
            if self.id:
                self.update()
            else:
                self.create()
        else:
            self.delete()


if __name__ == "__main__":
    # argparse argument
    parser = argparse.ArgumentParser(
        description="change file if congfig.yml is not an argument"
    )
    parser.add_argument(
        "--file",
        metavar="file",
        type=str,
        default="config.yml",
        help="enter filename if not using config.yml",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="increase output verbosity"
    )
    args = parser.parse_args()
    parser_file = args.file

    # Logging config
    formatter = logging.Formatter("%(levelname)s %(asctime)s %(name)s %(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    data_loaded = yaml.safe_load(open(parser_file, "r"))

    for uptime_test in data_loaded["uptime_tests"]:
        if uptime_test["name"]:
            test = UptimeTest(api_key=data_loaded["api_key"], **uptime_test)
            test.sync()
