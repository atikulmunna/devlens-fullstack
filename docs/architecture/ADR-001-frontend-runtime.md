# ADR-001: Frontend Runtime for v1.1

- Status: Accepted
- Date: 2026-02-24

## Context

SRD v1.1 originally referenced a Next.js App Router frontend scaffold for DEV-040.
The implemented v1.1 product runtime is a lightweight Node.js server-rendered shell
(`frontend/server.js`) with the required SRD routes and API proxy behavior.

## Decision

For v1.1, keep the Node.js shell runtime as the canonical frontend implementation.
Treat framework choice as non-blocking for DEV-040 as long as route scaffolding,
global loading/error states, and route-level functionality are delivered.

## Consequences

- DEV-040 acceptance is validated by delivered routes and behavior, not by framework brand.
- Migration to Next.js can be tracked as a future architecture ticket if needed.
- Existing frontend routes remain stable for all completed tickets (`DEV-041` to `DEV-044`).
