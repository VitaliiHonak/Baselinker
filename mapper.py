"""
Maps a Baselinker order dict to an OrderService POST body.

The expected payload structure is:
{
    "orders": {
        "<seller_id>_<bl_order_id>": {
            "orders":               {"fields": {...}},
            "orders_deliveries":    {"fields": {...}},
            "orders_merchandises":  [{"record_type": "0", "fields": {...}}, ...],
            "additional_fields":    [{"fields": {"field_id": ..., "field_value": ...}}, ...]
        }
    }
}

Business-specific IDs (seller_id, merchant_id, etc.) have no equivalent in
Baselinker — supply them via MappingConfig.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MappingConfig:
    # --- required business identifiers ----------------------------------------
    user_id: int
    seller_id: int
    merchant_id: int
    distribution_id: int
    payment_method_id: int
    payment_method_type: str        # e.g. "card", "cash"
    default_delivery_service_mdm_id: str
    default_delivery_service_id: int
    default_delivery_method_id: int
    default_city_id: int
    default_city_mdm_id: str
    checkout_type: str = "baselinker"
    default_lang: str = "ua"

    # --- optional lookup tables -----------------------------------------------
    # Maps Baselinker delivery_method string → delivery_service_id
    delivery_service_map: dict[str, int] = field(default_factory=dict)
    # Maps city name (lowercase) → {"city_id": int, "city_mdm_id": str}
    city_map: dict[str, dict] = field(default_factory=dict)
    # Maps Baselinker order_status_id → OrderService status string
    status_map: dict[int, str] = field(default_factory=dict)


def _resolve_city(config: MappingConfig, city_name: str) -> tuple[int, str]:
    entry = config.city_map.get(city_name.lower())
    if entry:
        return entry["city_id"], entry["city_mdm_id"]
    logger.warning("City %r not in city_map; using defaults", city_name)
    return config.default_city_id, config.default_city_mdm_id


def _map_merchandises(products: list[dict], config: MappingConfig) -> list[dict]:
    items = []
    for p in products:
        price = float(p.get("price_brutto") or 0)
        qty = int(p.get("quantity") or 1)
        discounted = float(p.get("price_brutto_after_discount") or price)

        merch_fields: dict = {
            "goods_id": p.get("product_id") or p.get("variant_id"),
            "quantity": qty,
            "price": price,
            "cost": round(price * qty, 2),
            "cost_with_discount": round(discounted * qty, 2),
            "seller_id": config.seller_id,
            "charge_bonuses": True,
        }

        if p.get("price_brutto"):
            merch_fields["old_price"] = float(p["price_brutto"])
        if p.get("name"):
            merch_fields["goods_title"] = p["name"]
        if p.get("images") and isinstance(p["images"], list) and p["images"]:
            merch_fields["goods_image"] = p["images"][0]

        items.append({"record_type": "0", "fields": merch_fields})
    return items


def _map_delivery(order: dict, config: MappingConfig) -> dict:
    city_name = order.get("delivery_city") or ""
    city_id, city_mdm_id = _resolve_city(config, city_name)

    delivery_service_id = config.delivery_service_map.get(
        order.get("delivery_method", ""), config.default_delivery_service_id
    )
    delivery_cost = float(order.get("delivery_price") or 0)

    delivery_fields: dict = {
        "delivery_service_mdm_id": config.default_delivery_service_mdm_id,
        "delivery_service_id": delivery_service_id,
        "delivery_method_id": config.default_delivery_method_id,
        "cost": delivery_cost,
        "cost_with_discount": delivery_cost,
        "city_id": city_id,
        "city": city_name,
        "city_mdm_id": city_mdm_id,
        # Baselinker has no structured delivery window; caller should override
        "delivery_window": "",
        "recipient_title": order.get("delivery_fullname") or order.get("user_login", ""),
        "recipient_change": 0,
        "recipient_id": None,
        # "phone" (not "recipient_phone") per the API contract
        "phone": order.get("phone"),
        "place_id": None,
        "place_number": None,
        "place_street": None,
        "place_house": None,
        "street": None,
        "street_id": None,
        "house": None,
        "flat": None,
        "street_mdm_id": None,
        "parcel_locker_id": None,
        "customs_duty": None,
    }

    if order.get("delivery_address"):
        delivery_fields["street"] = order["delivery_address"]
    if order.get("delivery_point_id"):
        delivery_fields["place_id"] = order["delivery_point_id"]
    if order.get("delivery_postcode"):
        delivery_fields["postal_code"] = order["delivery_postcode"]

    return delivery_fields


def map_order(order: dict, config: MappingConfig) -> dict:
    """
    Convert a single Baselinker order dict into an OrderService POST body.

    The outer key is "<seller_id>_<bl_order_id>" — this lets the caller
    correlate OrderService records back to Baselinker without a separate table.
    """
    products: list[dict] = order.get("products", [])
    bl_order_id = order["order_id"]

    amount = sum(
        float(p.get("price_brutto") or 0) * int(p.get("quantity") or 1)
        for p in products
    )
    discount_amount = sum(
        float(p.get("price_brutto_after_discount") or p.get("price_brutto") or 0)
        * int(p.get("quantity") or 1)
        for p in products
    )
    delivery_cost = float(order.get("delivery_price") or 0)

    bl_status_id: Optional[int] = order.get("order_status_id")
    os_status = config.status_map.get(bl_status_id, "new") if bl_status_id else "new"

    order_fields: dict = {
        "user_id": config.user_id,
        "user_title": order.get("delivery_fullname") or order.get("user_login", ""),
        "user_phone": order.get("phone", ""),
        "amount": round(amount, 2),
        "discount_amount": round(discount_amount, 2),
        "cost": round(amount + delivery_cost, 2),
        "discount_cost": round(discount_amount + delivery_cost, 2),
        "checkout_type": config.checkout_type,
        "seller_id": config.seller_id,
        "payment_method_id": config.payment_method_id,
        "payment_method_type": config.payment_method_type,
        "merchant_id": config.merchant_id,
        "distribution_id": config.distribution_id,
        "lang": config.default_lang,
        "status": os_status,
    }

    if order.get("email"):
        order_fields["email"] = order["email"]
    if order.get("user_comments"):
        order_fields["comment"] = order["user_comments"]

    key = f"{config.seller_id}_{bl_order_id}"
    return {
        "orders": {
            key: {
                "orders": {"fields": order_fields},
                "orders_deliveries": {"fields": _map_delivery(order, config)},
                "orders_merchandises": _map_merchandises(products, config),
                "additional_fields": [],
            }
        }
    }
