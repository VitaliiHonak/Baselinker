import json
from urllib.parse import parse_qs, unquote_plus

import pytest
import responses as rsps_lib

from baselinker import BaselinkerClient, BaselinkerAPIError, BaselinkerError

_URL = "https://api.baselinker.com/connector.php"


def _success(extra: dict) -> dict:
    return {"status": "SUCCESS", **extra}


@rsps_lib.activate
def test_get_orders_single_page():
    orders = [{"order_id": 1, "products": []}, {"order_id": 2, "products": []}]
    rsps_lib.add(rsps_lib.POST, _URL, json=_success({"orders": orders}))

    client = BaselinkerClient(token="test-token")
    result = client.get_orders()

    assert result == orders
    assert len(rsps_lib.calls) == 1


@rsps_lib.activate
def test_get_orders_paginates():
    # First page has 100 orders; second page has 1 → should stop
    page1 = [{"order_id": i, "products": []} for i in range(1, 101)]
    page2 = [{"order_id": 101, "products": []}]

    rsps_lib.add(rsps_lib.POST, _URL, json=_success({"orders": page1}))
    rsps_lib.add(rsps_lib.POST, _URL, json=_success({"orders": page2}))

    client = BaselinkerClient(token="test-token")
    result = client.get_orders()

    assert len(result) == 101
    assert len(rsps_lib.calls) == 2
    # Second call must include id_from = max of first page (100)
    second_params = parse_qs(rsps_lib.calls[1].request.body)
    assert json.loads(second_params["parameters"][0])["id_from"] == 100


@rsps_lib.activate
def test_api_error_raises():
    rsps_lib.add(
        rsps_lib.POST,
        _URL,
        json={"status": "ERROR", "error_code": "ERR_TOKEN_INVALID", "error_message": "Bad token"},
    )
    client = BaselinkerClient(token="bad-token")
    with pytest.raises(BaselinkerAPIError) as exc_info:
        client.get_orders()
    assert exc_info.value.error_code == "ERR_TOKEN_INVALID"


@rsps_lib.activate
def test_http_error_raises():
    rsps_lib.add(rsps_lib.POST, _URL, status=500, body="Internal Server Error")
    client = BaselinkerClient(token="test-token")
    with pytest.raises(BaselinkerError):
        client.get_orders()


@rsps_lib.activate
def test_set_order_status():
    rsps_lib.add(rsps_lib.POST, _URL, json=_success({}))
    client = BaselinkerClient(token="test-token")
    client.set_order_status(42, 3)  # should not raise
    body_params = parse_qs(rsps_lib.calls[0].request.body)
    assert body_params["method"][0] == "setOrderStatus"
    params = json.loads(body_params["parameters"][0])
    assert params["order_id"] == 42
    assert params["status_id"] == 3
