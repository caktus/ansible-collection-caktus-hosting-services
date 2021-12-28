import logging
import requests

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
    data = {"name":"Caktus Group", "state": "present", "test_type": "HTTP", "website_url": "https://www.caktusgroup.com/services/", "check_rate": "1800"}
    test = UptimeTest(api_key="", **data)
    test.fetch()
    breakpoint()
    
    # client._request("post", "/v1/uptime", data=data)

    # client._request("get", "/v1/uptime/6230254")
    # breakpoint()


    # get_new_uptime_id()