#!/usr/bin/env python3
"""Idempotently create Stripe products and prices for Livermore Alpha.

Usage:
    STRIPE_SECRET_KEY=sk_test_... python3 scripts/setup_stripe.py

Run once per environment (test, production). Safe to re-run — products and
prices are looked up by metadata before creating, so you won't get duplicates.
"""
from __future__ import annotations

import os
import sys

import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
if not stripe.api_key:
    print("ERROR: STRIPE_SECRET_KEY env var is required.", file=sys.stderr)
    sys.exit(1)

PRODUCTS = {
    "strategist": {"name": "Livermore Strategist", "metadata": {"tier": "strategist"}},
    "quant":      {"name": "Livermore Quant",       "metadata": {"tier": "quant"}},
}

PRICES_SPEC: dict[tuple[str, str], dict] = {
    ("strategist", "monthly"): {"unit_amount": 2400,  "recurring": {"interval": "month"}},
    ("strategist", "annual"):  {"unit_amount": 22800, "recurring": {"interval": "year"}},
    ("quant",       "monthly"): {"unit_amount": 7900,  "recurring": {"interval": "month"}},
    ("quant",       "annual"):  {"unit_amount": 70800, "recurring": {"interval": "year"}},
}


def get_or_create_product(tier: str, spec: dict) -> str:
    existing = stripe.Product.search(query=f'metadata["tier"]:"{tier}"')
    if existing.data:
        product = existing.data[0]
        print(f"  Product exists: {product.id} ({product.name})")
        return product.id

    product = stripe.Product.create(
        name=spec["name"],
        metadata=spec["metadata"],
    )
    print(f"  Created product: {product.id} ({product.name})")
    return product.id


def get_or_create_price(product_id: str, tier: str, cycle: str, spec: dict) -> str:
    existing = stripe.Price.list(product=product_id, active=True, limit=10)
    interval = spec["recurring"]["interval"]
    for price in existing.data:
        if (
            price.unit_amount == spec["unit_amount"]
            and price.recurring
            and price.recurring.interval == interval
        ):
            print(f"  Price exists: {price.id} (${price.unit_amount/100:.0f}/{interval})")
            return price.id

    price = stripe.Price.create(
        product=product_id,
        unit_amount=spec["unit_amount"],
        currency="usd",
        recurring=spec["recurring"],
        metadata={"tier": tier, "cycle": cycle},
    )
    print(f"  Created price: {price.id} (${price.unit_amount/100:.0f}/{interval})")
    return price.id


def main() -> None:
    print("Setting up Stripe products and prices for Livermore Alpha...")
    env_lines: list[str] = []

    for tier, product_spec in PRODUCTS.items():
        print(f"\n[{tier.upper()}]")
        product_id = get_or_create_product(tier, product_spec)

        for cycle in ("monthly", "annual"):
            price_spec = PRICES_SPEC[(tier, cycle)]
            price_id = get_or_create_price(product_id, tier, cycle, price_spec)
            env_key = f"STRIPE_PRICE_{tier.upper()}_{cycle.upper()}"
            env_lines.append(f"{env_key}={price_id}")

    print("\n\nAdd these to your .env file:")
    print("─" * 50)
    for line in env_lines:
        print(line)
    print("─" * 50)
    print("\nDone!")


if __name__ == "__main__":
    main()
