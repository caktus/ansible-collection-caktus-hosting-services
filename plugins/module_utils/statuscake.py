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
        self.config = self.prepare_data(kwargs)
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

    def prepare_data(self, data):
        cleaned_data = {}
        for key, val in data.items():
            if val:
                cleaned_data[key] = val
        return cleaned_data

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
    CSV_PARAMETERS = ("tags", "contact_groups", "dns_ip", "status_codes")

    def fetch_all(self):
        self._request("get", self.url, params={"page": 1, "limit": 100})
        if self.response.status_code == 200:
            logger.debug(
                "All uptime checks in StatusCake: %s", self.response.json()
            )
            return self.response.json()["data"]
        return []

    def find_by_name(self):
        for test in self.fetch_all():
            if test["name"] == self.config["name"]:
                logger.debug(f"Fetched data: {test}")
                self.id = test["id"]
                return test

    def prepare_data(self, data):
        data = super().prepare_data(data)
        for key in self.CSV_PARAMETERS:
            if key in data:
                key_csv = f"{key}_csv"
                item = [str(_val) for _val in data[key]]
                item_csv = ",".join(item)
                data[key_csv] = item_csv
                data.pop(key)
        return data

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
            # Convert all _csv arguments to expect lists rather than strings
            self._request("post", self.url, data=self.config)
            if self.response.status_code == 201:
                self.id = int(self.response.json()["data"]["new_id"])
                msg = f"A new test for '{self.config['name']}' was created."
                logger.info(msg)
                self.status.success = True
                self.status.changed = True
                self.status.message = msg

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
                    return

            self._request("put", f"{self.url}/{self.id}", data=self.config)
            if self.response.status_code == 204:
                fetch_updated_tests = self.retrieve()
                difference = dic_difference(fetch_tests, fetch_updated_tests)
                self.status.success = True
                self.status.changed = bool(difference)
                msg = f"Changes (old, new): {difference}" if difference else ""
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
                msg = f"The test for '{self.config['name']}' was deleted"
                self.status.success = True
                self.status.changed = True
        else:
            self.status.success = True
            msg = f"'{self.config['name']}' test not found for deletion"
        logger.info(msg)
        self.status.message = msg

    def sync(self):
        self.find_by_name()
        logger.info(
            f"Does '{self.config['name']}' exist in StatusCake? {bool(self.id)}."
        )
        if self.state == "present":
            if self.id:
                self.update()
            else:
                self.create()
        else:
            self.delete()
        return self.status


class SSLTest(StatusCakeAPI):

    url = "/v1/ssl"
    CSV_PARAMETERS = ("alert_at", "contact_groups")

    def fetch_all(self):
        """
        Retrieve all SSL tests
        https://www.statuscake.com/api/v1/#operation/list-ssl-tests
        """
        self._request("get", self.url)
        if self.response.status_code == 200:
            logger.debug(
                "All SSL checks in StatusCake: %s", self.response.json()["data"]
            )
            return self.response.json()["data"]
        return []

    def find_by_website_url(self):
        """Retrieve test using website_url"""
        provided_url = self.config["website_url"]
        for test in self.fetch_all():
            if test["website_url"] == provided_url:
                logger.debug(f"Fetched data: {test}")
                self.id = test["id"]
                return test

    def prepare_data(self, data):
        data = super().prepare_data(data)
        for key in self.CSV_PARAMETERS:
            if key in data:
                key_csv = f"{key}_csv"
                item = [str(_val) for _val in data[key]]
                item_csv = ",".join(item)
                data[key_csv] = item_csv
                data.pop(key)
        if not data["website_url"].endswith("/"):
            data["website_url"] = data["website_url"] + "/"
        return data

    def retrieve(self):
        """
        Rerieve an SSL test via its id.
        https://www.statuscake.com/api/v1/#operation/get-ssl-test
        """
        self.find_by_website_url()
        if self.id:
            self._request("get", f"{self.url}/{self.id}", data=self.config)
            if self.response.status_code == 200:
                return self.response.json()["data"]

    def create(self):
        """
        Create an SSL test.
        https://www.statuscake.com/api/v1/#operation/create-ssl-test
        """
        if not self.id:
            if "check_rate" not in self.config:
                self.config["check_rate"] = 1800
            if "alert_reminder" not in self.config:
                self.config["alert_reminder"] = True
            if "alert_expiry" not in self.config:
                self.config["alert_expiry"] = True
            if "alert_broken" not in self.config:
                self.config["alert_broken"] = True
            if "alert_mixed" not in self.config:
                self.config["alert_mixed"] = True
            # All _csv parameters (CSV_PARAMETERS) are converted to expect lists rather than strings
            self._request("post", self.url, data=self.config)
            if self.response.status_code == 201:
                self.id = int(self.response.json()["data"]["new_id"])
                msg = f"A new SSL test for '{self.config['website_url']}' was created."
                logger.info(msg)
                self.status.success = True
                self.status.changed = True
                self.status.message = msg

    def update(self):
        """
        Update an existing SSL test
        https://www.statuscake.com/api/v1/#operation/update-ssl-test
        """
        self.find_by_website_url()
        if self.id:
            pre_update_tests = self.retrieve()
            self._request("put", f"{self.url}/{self.id}", data=self.config)
            if self.response.status_code == 204:
                fetch_updated_tests = self.retrieve()
                difference = dic_difference(pre_update_tests, fetch_updated_tests)
                self.status.success = True
                self.status.changed = bool(difference)
                msg = f"Changes (old, new): {difference}" if difference else ""
                self.status.message = msg
                if msg:
                    logger.info(msg)

    def delete(self):
        """
        Delete a SSL test.
        https://www.statuscake.com/api/v1/#operation/delete-ssl-test
        """
        if self.id:
            self._request("delete", f"{self.url}/{self.id}")
            if self.response.status_code == 204:
                msg = f"The test for '{self.config['website_url']}' was deleted"
                self.status.success = True
                self.status.changed = True
        else:
            self.status.success = True
            msg = f"'{self.config['website_url']}' SSL test not found for deletion"
        self.status.message = msg

    def sync(self):
        self.find_by_website_url()
        logger.info(
            f"Does '{self.config['website_url']}' exist in StatusCake? {bool(self.id)}."
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

    for ssl_test in data_loaded["ssl_tests"]:
        if ssl_test["website_url"]:
            test = SSLTest(api_key=data_loaded["api_key"], **ssl_test)
            print(test.sync())
            # print(test.retrieve())
            # print(test.create())
            # print(test.find_by_website_url())
