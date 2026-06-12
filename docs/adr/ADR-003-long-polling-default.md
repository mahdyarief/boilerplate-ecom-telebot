# ADR-003: Long Polling Default

## Status
Accepted

## Context
The bot needs to receive updates from Telegram. The two main methods are Webhooks and Polling. Webhooks require a public IP/domain and SSL, while Polling works everywhere.

## Decision
We will default to **Long Polling** (`getUpdates` with a timeout).

## Rationale
- **Simplicity**: No need for complex network setup or server infrastructure.
- **Efficiency**: Long polling reduces idle network traffic compared to short polling.
- **Resource Friendly**: Ideal for low-resource environments (e.g., Raspberry Pi, small VPS).
- **Portability**: Works behind NAT and without a public domain.

## Consequences
- The bot application is self-contained and doesn't require an incoming web server.
- Polling timeout (e.g., 30s) should be used to balance responsiveness and resource usage.
