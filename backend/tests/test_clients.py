import time
import pytest
from app.clients.prophetx import ProphetXClient
from app.clients.sportsdataio import SportsDataIOClient, SPORTSDATAIO_BASE_URL


class TestProphetXClient:
    def test_client_instantiates_with_credentials(self):
        client = ProphetXClient(access_key="ak-test", secret_key="sk-test")
        assert client._access_key == "ak-test"
        assert client._secret_key == "sk-test"
        assert client._access_token is None  # lazy — not fetched until first request

    def test_token_considered_expired_before_first_auth(self):
        client = ProphetXClient(access_key="ak-test", secret_key="sk-test")
        # _token_expires_at=0.0 means time.time() >= 0 is always True → will re-auth
        assert time.time() >= client._token_expires_at

    def test_base_url_is_sandbox(self):
        client = ProphetXClient(
            access_key="ak-test",
            secret_key="sk-test",
            base_url="https://api-ss-sandbox.betprophet.co/partner",
        )
        assert "sandbox" in str(client._client.base_url)
        assert "betprophet.co" in str(client._client.base_url)


class TestSportsDataIOClient:
    def test_client_instantiates_with_api_key(self):
        client = SportsDataIOClient(api_key="test-key")
        assert client._api_key == "test-key"

    def test_client_uses_header_auth_not_query_param(self):
        """Per research Pitfall 5: SportsDataIO auth must use header, not query param."""
        client = SportsDataIOClient(api_key="test-key")
        assert "Ocp-Apim-Subscription-Key" in client._headers
        assert client._headers["Ocp-Apim-Subscription-Key"] == "test-key"
        # Confirm key is NOT in the base URL
        assert "test-key" not in str(SPORTSDATAIO_BASE_URL)

    def test_base_url_is_v3(self):
        assert "v3" in SPORTSDATAIO_BASE_URL
