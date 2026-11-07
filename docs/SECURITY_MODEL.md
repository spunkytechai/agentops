# Security Model (0.1)

## Authorization
- Default decision is deny.
- Tool identifiers are exact strings; wildcard expansion is not supported.
- Explicit deny takes precedence over explicit allow.
- A denied operation is not invoked and emits no execution event.

## Limitations
The initial SDK is not a process sandbox, secret manager, network firewall, prompt-injection detector, model-output validator, or distributed audit log. An allow-list does not replace least-privilege credentials or infrastructure isolation.

## Integration checklist
1. Give each tool a stable namespaced identifier (for example, `calendar.read`).
2. Authorize before invocation.
3. Scope credentials to minimum required actions.
4. Validate arguments independently of model output.
5. Apply timeouts and resource limits at integration boundaries.
6. Redact sensitive data before exporting telemetry.
7. Require human approval for consequential actions where appropriate.

The threat model is preliminary and will evolve with the runtime and integration surface.
