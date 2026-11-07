# Security Policy

AgentOps is early-stage software. No component should be assumed to have undergone an independent security audit or to be production-ready.

## Reporting a vulnerability
Do not publish exploitable details, credentials, tokens, or private data in a public issue. Use GitHub's **Report a vulnerability** feature on this repository for private disclosure. Include the affected version or commit, component, impact, reproduction steps, and suggested mitigation.

## Security principles
- Deny tool execution unless an explicit policy permits it.
- Explicit deny rules take precedence over allow rules.
- Treat model output, tool arguments, and external content as untrusted.
- Do not record prompts, arguments, results, or secrets by default.
- Apply timeouts, resource limits, and least-privilege credentials at integration boundaries.
- Review optional integrations independently.

## Scope
The project's code and official release artifacts are in scope. Third-party services and user deployments are outside direct project control.
