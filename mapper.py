"""
Maps a Baselinker order dict to an OrderService POST body.

Many OrderService fields are business-specific (seller_id, merchant_id,
distribution_id, SLA IDs, city MDM IDs, etc.) and have no equivalent in
Baselinker.  Pass a MappingConfig to supply those fixed values and any
lookup tables you maintain externally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MappingConfig:
    # --- required business identifiers ----------------------------------------
    user_id: int                  # OrderService user_id (buyer account in your system)
    seller_id: int                # OrderService seller_id
    merchant_id: int              # OrderService merchant_id
    distribution_id: int          # OrderService distribution_id
    payment_method_id: int        # OrderService payment_method_id
    payment_method_type: str      # e.g. "card", "cash", "cod"
    default_sla_id: int           # SLA applied to every merchandise line
    default_delivery_service_mdm_id: str   # MDM ID from LocationService
    default_delivery_service_id: int
    default_delivery_method_id: int
    default_city_id: int          # fallback when city cannot be resolved
    default_city_mdm_id: str      # fallback MDM city ID
    checkout_type: str = "baselinker"
    default_lang: str = "ua"

    # --- optional lookup tables ------------------------------------------------
    # Maps Baselinker delivery_method (string) → delivery_service_id
    delivery_service_map: dict[str, int] = field(default_factory=dict)
    # Maps city name (lowercase) → {"city_id": int, "city_mdm_id": str}
    city_map: dict[str, dict] = field(default_factory=dict)
    # Maps Baselinker order_status_id → OrderService status string
    status_map: dict[int, str] = field(default_factory=dict)


def _resolve_city(config: MappingConfig, city_name: str) -> tuple[int, str]:
    """Return (city_id, city_mdm_id) for city_name, falling back to defaults."""
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

        item: dict = {
            "goods_id": p.get("product_id") or p.get("variant_id"),
            "quantity": qty,
            "price": price,
            "cost": round(price * qty, 2),
            "cost_with_discount": round(discounted * qty, 2),
            "sla_id": config.default_sla_id,
        }

        if p.get("name"):
            item["goods_title"] = p["name"]
        if p.get("images") and isinstance(p["images"], list) and p["images"]:
            item["goods_image"] = p["images"][0]

        items.append(item)
    return items


def _map_delivery(order: dict, config: MappingConfig) -> dict:
    city_name = order.get("delivery_city") or ""
    city_id, city_mdm_id = _resolve_city(config, city_name)

    delivery_service_id = config.delivery_service_map.get(
        order.get("delivery_method", ""), config.default_delivery_service_id
    )

    delivery_cost = float(order.get("delivery_price") or 0)

    delivery: dict = {
        "delivery_service_mdm_id": config.default_delivery_service_mdm_id,
        "delivery_service_id": delivery_service_id,
        "delivery_method_id": config.default_delivery_method_id,
        "cost": delivery_cost,
        "cost_with_discount": delivery_cost,
        "city_id": city_id,
        "city": city_name,
        "city_mdm_id": city_mdm_id,
        # Baselinker has no structured delivery window; use empty string
        # so the caller can fill it in if needed
        "delivery_window": "",
        "recipient_title": order.get("delivery_fullname") or order.get("user_login", ""),
        "recipient_change": 0,
    }

    if order.get("delivery_address"):
        delivery["street"] = order["delivery_address"]
    if order.get("delivery_point_id"):
        delivery["place_id"] = order["delivery_point_id"]
        delivery["place_number"] = str(order["delivery_point_id"])
    if order.get("delivery_postcode"):
        delivery["postal_code"] = order["delivery_postcode"]
    if order.get("phone"):
        delivery["recipient_phone"] = order["phone"]

    return delivery


def map_order(order: dict, config: MappingConfig) -> dict:
    """
    Convert a single Baselinker order dict into an OrderService POST body.

    Fields that cannot be derived from Baselinker data (seller_id,
    merchant_id, etc.) are taken from MappingConfig.
    """
    products: list[dict] = order.get("products", [])

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

    body: dict = {
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
        "orders_merchandises": _map_merchandises(products, config),
        "orders_deliveries": [_map_delivery(order, config)],
    }

    if order.get("email"):
        body["email"] = order["email"]
    if order.get("user_comments"):
        body["comment"] = order["user_comments"]

    # Store the Baselinker order_id in orders_external_partner so you can
    # correlate records without a separate mapping table.
    body["orders_external_partner"] = {
        "ext_order_id": str(order["order_id"]),
        "partner_id": 2,  # id=2 = Prom/external; adjust to your Baselinker partner_id
    }

    return body
