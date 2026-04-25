import pytest
import responses as rsps_lib

from orderservice import OrderServiceClient, OrderServiceAPIError

_URL = "http://vm-orders-api.dev.rozetka.com.ua/orders"


@rsps_lib.activate
def test_create_order_success():
    rsps_lib.add(rsps_lib.POST, _URL, json={"id": 999}, status=201)

    client = OrderServiceClient("user", "pass", environment="test")
    result = client.create_order({"user_id": 1, "discount_cost": 100})

    assert result == {"id": 999}
    assert len(rsps_lib.calls) == 1
    assert rsps_lib.calls[0].request.headers["Authorization"].startswith("Basic ")


@rsps_lib.activate
def test_create_order_with_expand():
    rsps_lib.add(rsps_lib.POST, _URL, json={"id": 1, "orders_merchandises": []}, status=201)

    client = OrderServiceClient("user", "pass", environment="test")
    client.create_order({}, expand=["orders_merchandises", "orders_deliveries"])

    url_called = rsps_lib.calls[0].request.url
    assert "expand=orders_merchandises" in url_called
    assert "orders_deliveries" in url_called


@rsps_lib.activate
def test_create_order_api_error():
    rsps_lib.add(rsps_lib.POST, _URL, json={"message": "Validation failed"}, status=422)

    client = OrderServiceClient("user", "pass", environment="test")
    with pytest.raises(OrderServiceAPIError) as exc_info:
        client.create_order({})
    assert exc_info.value.status_code == 422
