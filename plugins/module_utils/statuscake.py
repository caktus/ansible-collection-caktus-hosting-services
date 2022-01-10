import logging
import requests
import yaml
import sys
import argparse
from dataclasses import dataclass

logger = logging.getLogger("statuscake")


def flatten(obj):
    flat = set()
    for key, val in obj.items():
        flat.add((key, str(val)))
    return flat


def dic_difference(dic1, dic2):
    set_pre = set(flatten(dic1))
    set_post = set(flatten(dic2))
    return set_pre ^ set_post


@dataclass
class Status:
    success: bool = False
    changed: bool = False
    message: str = ""


class StatusCakeAPI:
    def __init__(self, api_key, state, log_file=None, **kwargs) -> None:
        self.api_key = api_key
        self.state = state
        self.id = None
        self.config = kwargs
        self.client = requests.Session()
        self.client.headers["Authorization"] = f"Bearer {self.api_key}"
        self.status = Status()
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
        try:
            logger.debug(f"Request data: {kwargs['data']}")
        except KeyError:
            pass
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

    def find_by_name(self):
        for test in self.fetch_all():
            if test["name"] == self.config["name"]:
                logger.debug(f"Fetched data: {test}")
                self.id = test["id"]
                return test

    def retrieve(self):
        """
        Rerieve an uptime test with an id
        https://www.statuscake.com/api/v1/#operation/get-uptime-test
        """
        self.find_by_name()
        if self.id:
            self._request("get", f"{self.url}/{self.id}", data=self.config)
            if self.response.status_code == 200:
                return self.response.json()["data"]

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
            # Website_url and test_type are immutable in Statuscake API
            # Notifies user if they attempt to change them
            fetch_tests = self.retrieve()
            if fetch_tests:
                if fetch_tests["website_url"] != self.config[
                    "website_url"
                ] or fetch_tests["test_type"] != self.config.get("test_type", "HTTP"):
                    self.status.success = False
                    self.status.changed = False
                    msg = f"You attempted to change {fetch_tests['name']}'s 'website_url' or 'test_type' - they are immutable. To successfuly change them, delete the current test and create a new uptime test with the new parameters."
                    logger.info(msg)
                    self.status.message = msg

            # Does put request on tests
            self._request("put", f"{self.url}/{self.id}", data=self.config)
            if self.response.status_code == 204:
                fetch_updated_tests = self.retrieve()
                difference = dic_difference(fetch_tests, fetch_updated_tests)
                self.status.success = True
                self.status.changed = bool(difference)
                if difference:
                    msg = f"Changes (previous, current): {difference}"
                else:
                    msg = ""
                self.status.message = msg
                if msg:
                    logger.info(msg)

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
        fetch_data = self.retrieve()
        logger.info(
            f"Does '{self.config['name']}' exists in StatusCake? {bool(fetch_data)}."
        )
        if self.state == "present":
            if self.id:
                self.update()
            else:
                self.create()
        else:
            self.delete()
        return self.status


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
            # result = test.retrieve()
            status = test.sync()
            if status.changed:
                logger.info(status)
            # if result.success:
            #     module.exit_json(changed=result.changed, msg=result.msg)
            # else:
            #     module.fail_json(msg=result.msg)
