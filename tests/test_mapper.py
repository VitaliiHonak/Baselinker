import pytest

from mapper import MappingConfig, map_order

_BASE_CONFIG = MappingConfig(
    user_id=10,
    seller_id=5,
    merchant_id=30,
    distribution_id=40,
    payment_method_id=1,
    payment_method_type="cash",
    default_delivery_service_mdm_id="5498e0a0-ae1b-488c-89d5-3ea6db053edf",
    default_delivery_service_id=1,
    default_delivery_method_id=1,
    default_city_id=1,
    default_city_mdm_id="b205dde2-2e2e-4eb9-aef2-a67c82bbdf27",
)

_BASE_ORDER = {
    "order_id": 8124,
    "user_login": "john@example.com",
    "email": "john@example.com",
    "phone": "+380501234567",
    "delivery_fullname": "John Doe",
    "delivery_city": "Kyiv",
    "delivery_address": "Khreshchatyk 1",
    "delivery_price": "50.00",
    "delivery_method": "courier",
    "order_status_id": None,
    "user_comments": "Please call before delivery",
    "products": [
        {
            "product_id": "227633791",
            "name": "Test Product",
            "quantity": 2,
            "price_brutto": "199.99",
            "price_brutto_after_discount": "179.99",
            "images": ["https://img.example.com/p.jpg"],
        }
    ],
}


# --- helpers ------------------------------------------------------------------

def _order_fields(result: dict) -> dict:
    key = next(iter(result["orders"]))
    return result["orders"][key]["orders"]["fields"]

def _delivery_fields(result: dict) -> dict:
    key = next(iter(result["orders"]))
    return result["orders"][key]["orders_deliveries"]["fields"]

def _merchandises(result: dict) -> list:
    key = next(iter(result["orders"]))
    return result["orders"][key]["orders_merchandises"]

def _additional_fields(result: dict) -> list:
    key = next(iter(result["orders"]))
    return result["orders"][key]["additional_fields"]


# --- structure ----------------------------------------------------------------

def test_top_level_structure():
    result = map_order(_BASE_ORDER, _BASE_CONFIG)
    assert "orders" in result
    key = next(iter(result["orders"]))
    assert key == "5_8124"
    inner = result["orders"][key]
    assert "orders" in inner
    assert "orders_deliveries" in inner
    assert "orders_merchandises" in inner
    assert "additional_fields" in inner

def test_orders_wrapped_in_fields():
    result = map_order(_BASE_ORDER, _BASE_CONFIG)
    key = next(iter(result["orders"]))
    assert "fields" in result["orders"][key]["orders"]

def test_delivery_wrapped_in_fields_not_array():
    result = map_order(_BASE_ORDER, _BASE_CONFIG)
    key = next(iter(result["orders"]))
    delivery = result["orders"][key]["orders_deliveries"]
    assert isinstance(delivery, dict)
    assert "fields" in delivery
    assert not isinstance(delivery, list)

def test_merchandise_items_have_record_type_and_fields():
    result = map_order(_BASE_ORDER, _BASE_CONFIG)
    for item in _merchandises(result):
        assert item["record_type"] == "0"
        assert "fields" in item


# --- order fields -------------------------------------------------------------

def test_required_order_fields_present():
    f = _order_fields(map_order(_BASE_ORDER, _BASE_CONFIG))
    for key in ("user_id", "user_title", "user_phone", "discount_cost",
                "checkout_type", "seller_id", "payment_method_id",
                "payment_method_type", "merchant_id", "distribution_id", "lang"):
        assert key in f, f"Missing required order field: {key}"

def test_amounts_calculated_correctly():
    f = _order_fields(map_order(_BASE_ORDER, _BASE_CONFIG))
    assert f["amount"] == 399.98          # 2 × 199.99
    assert f["discount_amount"] == 359.98  # 2 × 179.99
    assert f["cost"] == 449.98            # amount + 50 delivery
    assert f["discount_cost"] == 409.98   # discount_amount + 50 delivery

def test_status_defaults_to_new():
    assert _order_fields(map_order(_BASE_ORDER, _BASE_CONFIG))["status"] == "new"

def test_status_mapped():
    config = MappingConfig(**{**_BASE_CONFIG.__dict__, "status_map": {10: "processing"}})
    order = {**_BASE_ORDER, "order_status_id": 10}
    assert _order_fields(map_order(order, config))["status"] == "processing"

def test_comment_included():
    assert _order_fields(map_order(_BASE_ORDER, _BASE_CONFIG))["comment"] == "Please call before delivery"

def test_comment_omitted_when_empty():
    order = {**_BASE_ORDER, "user_comments": ""}
    assert "comment" not in _order_fields(map_order(order, _BASE_CONFIG))


# --- delivery fields ----------------------------------------------------------

def test_delivery_uses_phone_not_recipient_phone():
    f = _delivery_fields(map_order(_BASE_ORDER, _BASE_CONFIG))
    assert f["phone"] == "+380501234567"
    assert "recipient_phone" not in f

def test_delivery_city_resolved():
    f = _delivery_fields(map_order(_BASE_ORDER, _BASE_CONFIG))
    assert f["city"] == "Kyiv"
    assert f["city_id"] == _BASE_CONFIG.default_city_id

def test_city_map_lookup():
    config = MappingConfig(
        **{**_BASE_CONFIG.__dict__, "city_map": {"kyiv": {"city_id": 999, "city_mdm_id": "mdm-999"}}}
    )
    f = _delivery_fields(map_order(_BASE_ORDER, config))
    assert f["city_id"] == 999
    assert f["city_mdm_id"] == "mdm-999"

def test_city_fallback_when_not_in_map():
    config = MappingConfig(**{**_BASE_CONFIG.__dict__, "city_map": {}})
    order = {**_BASE_ORDER, "delivery_city": "Unknown City"}
    f = _delivery_fields(map_order(order, config))
    assert f["city_id"] == config.default_city_id

def test_delivery_null_fields_present():
    f = _delivery_fields(map_order(_BASE_ORDER, _BASE_CONFIG))
    for null_key in ("place_number", "street_id", "house", "flat", "parcel_locker_id",
                     "customs_duty", "recipient_id"):
        assert null_key in f
        assert f[null_key] is None


# --- merchandise fields -------------------------------------------------------

def test_merchandise_mapped():
    items = _merchandises(map_order(_BASE_ORDER, _BASE_CONFIG))
    assert len(items) == 1
    f = items[0]["fields"]
    assert f["goods_id"] == "227633791"
    assert f["quantity"] == 2
    assert f["price"] == 199.99
    assert f["cost"] == 399.98
    assert f["cost_with_discount"] == 359.98

def test_merchandise_has_seller_id():
    f = _merchandises(map_order(_BASE_ORDER, _BASE_CONFIG))[0]["fields"]
    assert f["seller_id"] == _BASE_CONFIG.seller_id

def test_merchandise_has_charge_bonuses():
    f = _merchandises(map_order(_BASE_ORDER, _BASE_CONFIG))[0]["fields"]
    assert f["charge_bonuses"] is True

def test_merchandise_has_old_price():
    f = _merchandises(map_order(_BASE_ORDER, _BASE_CONFIG))[0]["fields"]
    assert f["old_price"] == 199.99

def test_merchandise_no_sla_id():
    f = _merchandises(map_order(_BASE_ORDER, _BASE_CONFIG))[0]["fields"]
    assert "sla_id" not in f


# --- additional fields --------------------------------------------------------

def test_additional_fields_is_list():
    assert isinstance(_additional_fields(map_order(_BASE_ORDER, _BASE_CONFIG)), list)
