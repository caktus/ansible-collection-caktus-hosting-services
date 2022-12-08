from plugins.module_utils import statuscake


class TestStatusCakeAPI:
    def test_too_many_requests_api_call(self, requests_mock):
        requests_mock.get("/v1/uptime", status_code=429, reason="Too Many Requests")
        client = statuscake.StatusCakeAPI(api_key="", state="")
        client._request("get", "/v1/uptime")
        assert "Too Many Requests" in client.status.message

    def test_failed_status_code_api_call(self, requests_mock):
        requests_mock.get("/v1/uptime", status_code=400, json={"message": "Bad Error"})
        client = statuscake.StatusCakeAPI(api_key="", state="")
        client._request("get", "/v1/uptime")
        assert "Bad Error" in client.status.message


class TestUptimeTest:
    def test_contact_groups(self):
        client = statuscake.UptimeTest(
            api_key="", state="", contact_groups=[100000, 110000]
        )
        assert client.config == {"contact_groups[]": [100000, 110000]}

    def test_status_codes_csv(self):
        client = statuscake.UptimeTest(api_key="", state="", status_codes=[200, 201])
        assert client.config == {"status_codes_csv": "200,201"}

    def test_tags(self):
        client = statuscake.UptimeTest(api_key="", state="", tags=["prod"])
        assert client.config == {"tags[]": ["prod"]}


class TestSSLTest:
    def test_alert_at(self):
        client = statuscake.SSLTest(
            api_key="",
            state="",
            website_url="https://example.com/",
            alert_at=[10, 20, 30],
        )
        assert client.config == {
            "website_url": "https://example.com/",
            "alert_at[]": [10, 20, 30],
        }

    def test_contact_groups(self):
        client = statuscake.SSLTest(
            api_key="",
            state="",
            website_url="https://example.com/",
            contact_groups=[100000, 110000],
        )
        assert client.config == {
            "website_url": "https://example.com/",
            "contact_groups[]": [100000, 110000],
        }
