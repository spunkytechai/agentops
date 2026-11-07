# Security Model (0.2)

## Authorization
- Default decision is deny.
- Tool identifiers are exact strings; wildcard expansion is not supported.
- Global and principal-scoped explicit deny rules take precedence over every allow rule.
- Principal-scoped rules match only the exact principal ID and tool name.
- A denied operation is not invoked and emits no execution event.
- Policy evaluation is an application-level control, not a substitute for infrastructure isolation.

## Registry
The initial agent registry is process-local, in-memory, and non-persistent. It is not a distributed source of truth and does not provide cryptographic identity, deployment approval, or artifact integrity verification. Do not treat registration as proof that an agent definition or its tools are trusted.

## Limitations
The initial SDK is not a process sandbox, secret manager, network firewall, prompt-injection detector, model-output validator, or distributed audit log. An allow-list does not replace least-privilege credentials or infrastructure isolation.

## Integration checklist
1. Give each tool a stable namespaced identifier (for example, `calendar.read`).
2. Bind authenticated principal IDs in trusted host code; never accept a model-generated principal as authority.
3. Authorize before invocation.
4. Scope credentials to minimum required actions.
5. Validate arguments independently of model output.
6. Apply timeouts and resource limits at integration boundaries.
7. Redact sensitive data before exporting telemetry.
8. Require human approval for consequential actions where appropriate.

The threat model is preliminary and will evolve with the runtime and integration surface.
