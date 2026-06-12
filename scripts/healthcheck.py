#!/usr/bin/env python
"""Docker HEALTHCHECK entry point.

Returns exit 0 if the bot process is healthy, exit 1 otherwise.

Checks performed:
1. Core modules can be imported (syntax and dependency integrity).
2. (Optional) Database connectivity — only if DATABASE_URL is set.

Usage in Dockerfile:
    HEALTHCHECK CMD python scripts/healthcheck.py
"""

from __future__ import annotations

import sys


def main() -> int:
    # ── 1. Import check ───────────────────────────────────
    try:
        import bot_app.main  # noqa: F401
        import bot_app.bootstrap  # noqa: F401
        import bot_app.core.config  # noqa: F401
        from bot_app.core.config import settings
    except Exception as exc:
        print(f"IMPORT_FAIL: {exc}")
        return 1

    # ── 2. Database connectivity check (optional) ─────────
    # Only run if explicitly requested via env var to avoid
    # slow healthchecks for simple container liveness.
    import os

    if os.getenv("HEALTHCHECK_DB", "").lower() in ("1", "true", "yes"):
        try:
            import asyncio

            async def _check_db() -> None:
                from bot_app.infrastructure.persistence.engine import create_engine

                engine = create_engine()
                async with engine.connect() as conn:
                    result = await conn.execute(
                        __import__("sqlalchemy").text("SELECT 1")
                    )
                    row = result.scalar()
                    assert row == 1
                await engine.dispose()

            asyncio.run(_check_db())
        except Exception as exc:
            print(f"DB_FAIL: {exc}")
            return 1

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
