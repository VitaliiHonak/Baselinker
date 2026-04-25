import logging
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

from .exceptions import OrderServiceAPIError, OrderServiceError

logger = logging.getLogger(__name__)

# Available environments
ENVIRONMENTS = {
    "test": "http://vm-orders-api.dev.rozetka.com.ua/orders",
    "preprod": "https://orders.preprod.rozetka.company/orders",
    "prod": "https://orders.rozetka.company/orders",
}


class OrderServiceClient:
    """
    Client for the internal OrderService API.

    Authentication: HTTP Basic Auth
    Content-Type:   application/json
    """

    def __init__(
        self,
        username: str,
        password: str,
        environment: str = "prod",
        base_url: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self._auth = HTTPBasicAuth(username, password)
        self._timeout = timeout
        self._base_url = base_url or ENVIRONMENTS[environment]

        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"
        self._session.auth = self._auth

    def create_order(self, payload: dict, expand: Optional[list[str]] = None) -> dict:
        """
        POST /orders

        Pass expand=[...] to receive nested relations in the response,
        e.g. expand=["orders_merchandises", "orders_deliveries"].
        """
        url = self._base_url
        params = {}
        if expand:
            params["expand"] = ",".join(expand)

        try:
            response = self._session.post(
                url, json=payload, params=params, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise OrderServiceError(f"HTTP error creating order: {exc}") from exc

        if not response.ok:
            raise OrderServiceAPIError(response.status_code, response.text)

        logger.debug("Created OrderService order, status=%s", response.status_code)
        return response.json()
