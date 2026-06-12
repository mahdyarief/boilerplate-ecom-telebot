#!/usr/bin/env python
"""Seed the database with demo data.

Usage (from project root):
    PYTHONPATH=src python scripts/seed_demo_data.py

Requires a running database whose URL is in .env / DATABASE_URL.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure src is on sys.path so that ``bot_app`` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bot_app.infrastructure.persistence.engine import create_engine, create_session_factory
from bot_app.infrastructure.persistence.models import Base
from bot_app.infrastructure.persistence.repositories import (
    CategoryRepository,
    ProductRepository,
    UserRepository,
)


async def seed() -> None:
    engine = create_engine()

    # Create tables (idempotent for SQLite dev; in prod use `alembic upgrade head`).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        user_repo = UserRepository(session)
        cat_repo = CategoryRepository(session)
        prod_repo = ProductRepository(session)

        # ── Users ────────────────────────────────────────────
        admin = await user_repo.get_or_create(1_000_001, language="id")
        await user_repo.toggle_admin(admin.id, is_admin=True)

        await user_repo.get_or_create(2_000_002, language="id")

        # ── Categories ───────────────────────────────────────
        electronics = await cat_repo.create(name="Elektronik", slug="elektronik")
        fashion = await cat_repo.create(name="Fashion", slug="fashion")
        food = await cat_repo.create(name="Makanan & Minuman", slug="makanan-minuman")

        # Sub-category
        phones = await cat_repo.create(
            name="Handphone", slug="handphone", parent_id=electronics.id,
        )

        # ── Products ─────────────────────────────────────────
        await prod_repo.create(
            category_id=phones.id,
            name="Smartphone X",
            price_smallest_unit=3_500_000,
            description="Smartphone terbaru dengan kamera 108MP",
            stock=25,
        )
        await prod_repo.create(
            category_id=phones.id,
            name="Power Bank 20000mAh",
            price_smallest_unit=250_000,
            description="Power bank kapasitas besar",
            stock=100,
        )
        await prod_repo.create(
            category_id=fashion.id,
            name="Kaos Polos Premium",
            price_smallest_unit=89_000,
            description="Katun combed 30s nyaman dipakai",
            stock=200,
        )
        await prod_repo.create(
            category_id=food.id,
            name="Kopi Arabika 250g",
            price_smallest_unit=75_000,
            description="Single origin, medium roast",
            stock=50,
        )

        await session.commit()

    # ── Summary ─────────────────────────────────────────────
    async with session_factory() as session:
        user_repo = UserRepository(session)
        cat_repo = CategoryRepository(session)
        prod_repo = ProductRepository(session)

        users = [u async for u in await _all_users(session)]
        categories = await cat_repo.list_active()
        print(f"✓ Users: {len(users)}")
        print(f"✓ Categories: {len(categories)}")

        total_products = 0
        for cat in categories:
            prods = await prod_repo.list_by_category(cat.id, active_only=False)
            total_products += len(prods)
        print(f"✓ Products: {total_products}")

    await engine.dispose()
    print("\n🌱 Demo data seeded successfully!")


async def _all_users(session):
    from sqlalchemy import select

    from bot_app.infrastructure.persistence.models import User
    result = await session.execute(select(User))
    for row in result.scalars():
        yield row


if __name__ == "__main__":
    asyncio.run(seed())
