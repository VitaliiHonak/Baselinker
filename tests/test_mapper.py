import pytest

from mapper import MappingConfig, map_order

_BASE_CONFIG = MappingConfig(
    user_id=10,
    seller_id=20,
    merchant_id=30,
    distribution_id=40,
    payment_method_id=5,
    payment_method_type="card",
    default_sla_id=7,
    default_delivery_service_mdm_id="mdm-delivery-001",
    default_delivery_service_id=1,
    default_delivery_method_id=2,
    default_city_id=100,
    default_city_mdm_id="mdm-city-kyiv",
)

_BASE_ORDER = {
    "order_id": 555,
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
            "product_id": "1001",
            "name": "Test Product",
            "quantity": 2,
            "price_brutto": "199.99",
            "price_brutto_after_discount": "179.99",
            "images": ["https://img.example.com/p.jpg"],
        }
    ],
}


def test_required_fields_present():
    body = map_order(_BASE_ORDER, _BASE_CONFIG)
    for key in ("user_id", "user_title", "user_phone", "discount_cost",
                "checkout_type", "seller_id", "payment_method_id",
                "payment_method_type", "merchant_id", "distribution_id", "lang"):
        assert key in body, f"Missing required field: {key}"


def test_amounts_calculated_correctly():
    body = map_order(_BASE_ORDER, _BASE_CONFIG)
    # 2 × 199.99 = 399.98 (amount), 2 × 179.99 = 359.98 (discount_amount)
    # delivery = 50
    assert body["amount"] == 399.98
    assert body["discount_amount"] == 359.98
    assert body["cost"] == 449.98       # amount + delivery
    assert body["discount_cost"] == 409.98  # discount_amount + delivery


def test_merchandise_mapped():
    body = map_order(_BASE_ORDER, _BASE_CONFIG)
    merch = body["orders_merchandises"]
    assert len(merch) == 1
    assert merch[0]["goods_id"] == "1001"
    assert merch[0]["quantity"] == 2
    assert merch[0]["price"] == 199.99
    assert merch[0]["cost"] == 399.98
    assert merch[0]["cost_with_discount"] == 359.98
    assert merch[0]["sla_id"] == _BASE_CONFIG.default_sla_id
    assert merch[0]["goods_image"] == "https://img.example.com/p.jpg"


def test_delivery_mapped():
    body = map_order(_BASE_ORDER, _BASE_CONFIG)
    delivery = body["orders_deliveries"][0]
    assert delivery["city"] == "Kyiv"
    assert delivery["city_id"] == _BASE_CONFIG.default_city_id
    assert delivery["cost"] == 50.0
    assert delivery["recipient_title"] == "John Doe"
    assert delivery["recipient_phone"] == "+380501234567"


def test_city_map_lookup():
    config = MappingConfig(
        **{**_BASE_CONFIG.__dict__, "city_map": {"kyiv": {"city_id": 999, "city_mdm_id": "mdm-999"}}}
    )
    body = map_order(_BASE_ORDER, config)
    assert body["orders_deliveries"][0]["city_id"] == 999
    assert body["orders_deliveries"][0]["city_mdm_id"] == "mdm-999"


def test_city_fallback_when_not_in_map():
    config = MappingConfig(**{**_BASE_CONFIG.__dict__, "city_map": {}})
    order = {**_BASE_ORDER, "delivery_city": "Unknown City"}
    body = map_order(order, config)
    assert body["orders_deliveries"][0]["city_id"] == config.default_city_id


def test_status_mapped():
    config = MappingConfig(**{**_BASE_CONFIG.__dict__, "status_map": {10: "processing"}})
    order = {**_BASE_ORDER, "order_status_id": 10}
    body = map_order(order, config)
    assert body["status"] == "processing"


def test_status_defaults_to_new():
    body = map_order(_BASE_ORDER, _BASE_CONFIG)
    assert body["status"] == "new"


def test_external_partner_stored():
    body = map_order(_BASE_ORDER, _BASE_CONFIG)
    assert body["orders_external_partner"]["ext_order_id"] == "555"


def test_comment_included():
    body = map_order(_BASE_ORDER, _BASE_CONFIG)
    assert body["comment"] == "Please call before delivery"


def test_comment_omitted_when_empty():
    order = {**_BASE_ORDER, "user_comments": ""}
    body = map_order(order, _BASE_CONFIG)
    assert "comment" not in body
