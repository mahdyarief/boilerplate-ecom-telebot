# ADR-001: Feature-Based Modular Monolith

## Status
Accepted

## Context
The previous TypeScript implementation was a relatively flat structure. To ensure scalability and maintainability as the bot grows, we need a more robust architectural pattern.

## Decision
We will adopt a **Feature-Based Modular Monolith** architecture. This structure organizes code by functional features (e.g., `basic`, `notes`) rather than just technical layers (e.g., `controllers`, `models`).

## Rationale
- **High Cohesion**: Related logic stays together within a feature module.
- **Loose Coupling**: Features communicate through well-defined shared protocols and models.
- **Scalability**: New features can be added in isolation without tangling with existing ones.
- **Maintainability**: Smaller, focused modules are easier to understand and test.

## Consequences
- Clear separation between infrastructure, application logic, and domain models.
- Development requires following the modular structure, avoiding cross-module imports where possible.
