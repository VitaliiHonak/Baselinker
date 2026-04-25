import json
import logging
from typing import Any, Optional

import requests

from .exceptions import BaselinkerAPIError, BaselinkerError

logger = logging.getLogger(__name__)

_API_URL = "https://api.baselinker.com/connector.php"


class BaselinkerClient:
    """
    Thin wrapper around the Baselinker REST API.

    All requests are HTTP POST with form fields:
        token      – API token
        method     – method name
        parameters – JSON-encoded parameter object
    """

    def __init__(self, token: str, timeout: int = 30) -> None:
        self._token = token
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/x-www-form-urlencoded"

    def _call(self, method: str, parameters: Optional[dict] = None) -> dict:
        payload = {
            "token": self._token,
            "method": method,
            "parameters": json.dumps(parameters or {}),
        }
        try:
            response = self._session.post(_API_URL, data=payload, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BaselinkerError(f"HTTP error calling {method}: {exc}") from exc

        data = response.json()
        if data.get("status") != "SUCCESS":
            raise BaselinkerAPIError(
                error_code=data.get("error_code", "UNKNOWN"),
                message=data.get("error_message", "Unknown error"),
            )
        return data

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_orders(
        self,
        *,
        date_from: Optional[int] = None,
        date_to: Optional[int] = None,
        id_from: Optional[int] = None,
        status_id: Optional[int] = None,
        get_unconfirmed_orders: bool = False,
        filter_email: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch orders from Baselinker.  Returns a flat list of order dicts.

        Baselinker returns at most 100 orders per call; this method pages
        automatically using id_from until all orders are retrieved.
        """
        params: dict[str, Any] = {
            "get_unconfirmed_orders": get_unconfirmed_orders,
        }
        if date_from is not None:
            params["date_from"] = date_from
        if date_to is not None:
            params["date_to"] = date_to
        if id_from is not None:
            params["id_from"] = id_from
        if status_id is not None:
            params["status_id"] = status_id
        if filter_email is not None:
            params["filter_email"] = filter_email

        all_orders: list[dict] = []
        while True:
            data = self._call("getOrders", params)
            batch: list[dict] = data.get("orders", [])
            all_orders.extend(batch)
            logger.debug("Fetched %d orders (total so far: %d)", len(batch), len(all_orders))

            # Baselinker caps at 100 per page; stop when we get fewer
            if len(batch) < 100:
                break
            params["id_from"] = max(o["order_id"] for o in batch)

        return all_orders

    def get_order_status_list(self) -> list[dict]:
        """Return all configured order statuses."""
        data = self._call("getOrderStatusList")
        return data.get("statuses", [])

    def set_order_status(self, order_id: int, status_id: int) -> None:
        """Update the status of a single Baselinker order."""
        self._call("setOrderStatus", {"order_id": order_id, "status_id": status_id})
        logger.debug("Set Baselinker order %s status → %s", order_id, status_id)

    def set_order_fields(self, order_id: int, fields: dict) -> None:
        """Update arbitrary fields on a Baselinker order."""
        self._call("setOrderFields", {"order_id": order_id, **fields})
        logger.debug("Updated fields for Baselinker order %s", order_id)

    def add_order_comment(self, order_id: int, comment: str) -> None:
        self._call("addOrderComment", {"order_id": order_id, "comment": comment})
