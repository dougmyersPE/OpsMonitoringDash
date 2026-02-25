import pytest
from app.clients.prophetx import ProphetXClient
from app.clients.sportsdataio import SportsDataIOClient, SPORTSDATAIO_BASE_URL


class TestProphetXClient:
    def test_client_instantiates_with_api_key(self):
        client = ProphetXClient(api_key="test-key")
        assert client._api_key == "test-key"
        assert client._headers == {"Authorization": "Bearer test-key"}

    def test_client_uses_bearer_auth_not_query_param(self):
        client = ProphetXClient(api_key="test-key")
        # Confirm auth is in headers, NOT embedded in base_url as a query param
        assert "Authorization" in client._headers
        assert "test-key" not in str(client._client.base_url)


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
