"""
Sync orders from Baselinker → OrderService.

Usage:
    python sync.py [--since <unix_ts>] [--status-id <id>] [--dry-run]

Environment variables (required):
    BL_TOKEN                  Baselinker API token
    OS_USERNAME               OrderService Basic Auth username
    OS_PASSWORD               OrderService Basic Auth password

Environment variables (optional):
    OS_ENV                    OrderService environment: test | preprod | prod  (default: prod)
    OS_USER_ID                Buyer user_id in OrderService             (default: 0)
    OS_SELLER_ID              seller_id                                 (default: 0)
    OS_MERCHANT_ID            merchant_id                               (default: 0)
    OS_DISTRIBUTION_ID        distribution_id                           (default: 0)
    OS_PAYMENT_METHOD_ID      payment_method_id                         (default: 0)
    OS_PAYMENT_METHOD_TYPE    payment_method_type                       (default: card)
    OS_DEFAULT_SLA_ID         SLA ID applied to every merchandise line  (default: 0)
    OS_DELIVERY_SVC_MDM_ID    MDM delivery service ID                   (default: "")
    OS_DELIVERY_SVC_ID        delivery_service_id                       (default: 0)
    OS_DELIVERY_METHOD_ID     delivery_method_id                        (default: 0)
    OS_CITY_ID                fallback city_id                          (default: 0)
    OS_CITY_MDM_ID            fallback city_mdm_id                      (default: "")
    OS_LANG                   interface language: ru | ua | pl           (default: ua)
    BL_SYNCED_STATUS_ID       Baselinker status_id to set after a successful sync
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from baselinker import BaselinkerClient, BaselinkerError
from mapper import MappingConfig, map_order
from orderservice import OrderServiceClient, OrderServiceError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
)
logger = logging.getLogger("bl-sync")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int = 0) -> int:
    val = os.environ.get(key)
    return int(val) if val else default


def build_config() -> MappingConfig:
    return MappingConfig(
        user_id=_env_int("OS_USER_ID"),
        seller_id=_env_int("OS_SELLER_ID"),
        merchant_id=_env_int("OS_MERCHANT_ID"),
        distribution_id=_env_int("OS_DISTRIBUTION_ID"),
        payment_method_id=_env_int("OS_PAYMENT_METHOD_ID"),
        payment_method_type=_env("OS_PAYMENT_METHOD_TYPE", "card"),
        default_sla_id=_env_int("OS_DEFAULT_SLA_ID"),
        default_delivery_service_mdm_id=_env("OS_DELIVERY_SVC_MDM_ID"),
        default_delivery_service_id=_env_int("OS_DELIVERY_SVC_ID"),
        default_delivery_method_id=_env_int("OS_DELIVERY_METHOD_ID"),
        default_city_id=_env_int("OS_CITY_ID"),
        default_city_mdm_id=_env("OS_CITY_MDM_ID"),
        default_lang=_env("OS_LANG", "ua"),
    )


def run_sync(
    bl: BaselinkerClient,
    os_client: OrderServiceClient,
    config: MappingConfig,
    *,
    since: int | None = None,
    status_id: int | None = None,
    synced_status_id: int | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Fetch Baselinker orders and push them to OrderService.

    Returns (success_count, error_count).
    """
    logger.info("Fetching orders from Baselinker (since=%s, status_id=%s)", since, status_id)
    orders = bl.get_orders(date_from=since, status_id=status_id)
    logger.info("Fetched %d orders", len(orders))

    success = error = 0
    for order in orders:
        bl_id = order["order_id"]
        try:
            payload = map_order(order, config)

            if dry_run:
                logger.info("[dry-run] Would create order for BL#%s", bl_id)
                success += 1
                continue

            result = os_client.create_order(
                payload, expand=["orders_merchandises", "orders_deliveries"]
            )
            os_id = result.get("id") or result.get("order_id", "?")
            logger.info("Created OS order %s for BL#%s", os_id, bl_id)
            success += 1

            if synced_status_id is not None:
                try:
                    bl.set_order_status(bl_id, synced_status_id)
                except BaselinkerError as exc:
                    logger.warning("Could not update BL#%s status: %s", bl_id, exc)

        except (OrderServiceError, Exception) as exc:
            logger.error("Failed to sync BL#%s: %s", bl_id, exc)
            error += 1

    return success, error


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Baselinker orders → OrderService")
    parser.add_argument("--since", type=int, help="Unix timestamp – fetch orders after this date")
    parser.add_argument("--status-id", type=int, help="Only fetch orders with this Baselinker status")
    parser.add_argument("--dry-run", action="store_true", help="Map orders but do not POST to OrderService")
    args = parser.parse_args()

    bl_token = _env("BL_TOKEN")
    os_user = _env("OS_USERNAME")
    os_pass = _env("OS_PASSWORD")

    missing = [k for k, v in [("BL_TOKEN", bl_token), ("OS_USERNAME", os_user), ("OS_PASSWORD", os_pass)] if not v]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    bl = BaselinkerClient(token=bl_token)
    os_client = OrderServiceClient(
        username=os_user,
        password=os_pass,
        environment=_env("OS_ENV", "prod"),
    )
    config = build_config()
    synced_status_id = _env_int("BL_SYNCED_STATUS_ID") or None

    success, error = run_sync(
        bl,
        os_client,
        config,
        since=args.since,
        status_id=args.status_id,
        synced_status_id=synced_status_id,
        dry_run=args.dry_run,
    )

    logger.info("Done. success=%d  error=%d", success, error)
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()
