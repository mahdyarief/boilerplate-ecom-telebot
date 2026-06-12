# ADR-002: SSOT Governance

## Status
Accepted

## Context
Duplicate definitions of configuration, command names, and data models lead to inconsistencies and bugs.

## Decision
We will enforce **Single Source of Truth (SSOT)** principles across the codebase.

## Rationale
- **Consistency**: Changes in one place propagate throughout the system.
- **Reliability**: Reduces the risk of "desync" bugs.
- **Clarity**: Developers know exactly where to find and update specific concerns.

## Ownership Map
- **Environment variables**: `src/bot_app/core/config.py` (using Pydantic Settings).
- **Command definitions**: `src/bot_app/app/routing/command_registry.py`.
- **Telegram payload schema**: `src/bot_app/shared/models/telegram.py`.
- **Parsed command model**: `src/bot_app/shared/models/command.py`.
- **Repository contracts**: `src/bot_app/shared/protocols/*.py`.
- **Error taxonomy**: `src/bot_app/core/errors.py`.

## Consequences
- No `os.getenv()` outside the config module.
- No hardcoded command strings in feature handlers.
- Strict adherence to defined models and protocols.
