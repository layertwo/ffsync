---
inclusion: always
---

# Product Overview

Firefox Sync (ffsync) is a self-hosted implementation of the Mozilla Firefox Sync protocol on AWS infrastructure. It serves as a drop-in replacement for Mozilla's hosted servers.

## Services

**Storage Service** (`/storage/...`)
- REST API for Firefox browser sync data (bookmarks, tabs, history, passwords, etc.)
- Data organized as Basic Storage Objects (BSOs) within named collections
- Supports CRUD operations, batch updates, and collection-level queries

**Token Service** (`/1.0/sync/1.5`)
- Authentication endpoint exchanging OIDC Bearer tokens for HAWK credentials
- Returns: `id` (HAWK identifier), `key` (shared secret), `api_endpoint`, `uid`, `duration` (300s), `hashalg` ("sha256")

## Domain Model

| Concept | Description |
|---------|-------------|
| **BSO** | Basic Storage Object: `id`, `payload` (JSON string), `modified` (epoch seconds, 2 decimal precision), optional `sortindex`, optional `ttl` |
| **Collection** | Named group of BSOs (e.g., "bookmarks", "tabs", "history", "passwords", "forms") |
| **User** | Identified by OIDC subject claim; storage isolated per user |
| **HAWK** | HTTP authentication scheme used by Firefox Sync clients |

## API Conventions

- Timestamps use seconds since epoch with 2 decimal places (e.g., `1702345678.12`)
- `X-Last-Modified` header returns collection/object modification time
- `X-If-Unmodified-Since` header enables optimistic concurrency control
- HTTP 412 (Precondition Failed) when concurrent modification detected
- HTTP 409 (Conflict) for conflicting operations
- HTTP 413 (Request Too Large) when payload exceeds limits
- HTTP 429 (Quota Exceeded) when storage quota reached

## Authentication Flow

1. Client presents OIDC Bearer token to Token Service
2. Token Service validates token via OIDC provider
3. Token Service returns HAWK credentials (valid 300 seconds)
4. Client uses HAWK credentials to authenticate Storage API requests
