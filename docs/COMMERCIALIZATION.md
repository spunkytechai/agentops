# Commercialization Strategy

## Purpose

AgentOps is an open-source, provider-agnostic foundation for governing and operating AI agents. The commercial strategy is to earn revenue from hosted operations, enterprise capabilities, implementation, and support while keeping the existing Apache-2.0 SDK core useful and independently deployable.

This document describes a proposed business model and validation plan. It does not claim that hosted services, enterprise controls, billing, or paid support are currently implemented.

## Product and licensing boundary

- **Open-source core:** Keep the Python and TypeScript SDKs, conformance fixtures, core policy and approval primitives, local persistence adapters, worker adapters, and documented interfaces under Apache-2.0.
- **Commercial services:** Charge for hosted infrastructure, managed operations, enterprise administration, integrations, implementation, training, and support only when those services exist and are deliverable.
- **No artificial breakage:** Do not disable core features, add license checks to the SDK, or weaken security in the free edition to force an upgrade.
- **Clear separation:** Any future proprietary hosted control plane must live in a separately identified service/repository, with a documented API boundary. Do not move existing public core code into a private repository or change its license retroactively.
- **Customer portability:** Provide documented export paths for traces, evaluation results, policies, and configuration. Do not make proprietary storage the only way to use the SDK.

## Target customers

1. **Independent developers and AI builders** who need reliable evaluation, approval gates, and worker execution without assembling multiple tools.
2. **AI product teams and startups** operating customer-facing agents and needing shared visibility, regression gates, and deployment support.
3. **Regulated and larger organizations** that need access controls, retention policy, audit evidence, deployment options, and contractual support.
4. **AI implementation partners and consultancies** that integrate AgentOps into customer environments.

Initial customer discovery should focus on teams already running agents with consequential tool access. Do not assume broad demand from GitHub stars or downloads alone.

## Competitive pricing snapshot

Public vendor pricing pages reviewed on 8 November 2026 show a consistent pattern: a free developer entry point, a low-cost paid tier for production teams, usage or retention-based expansion, and custom enterprise pricing.

| Product | Public entry point | Paid entry point | Monetization emphasis |
|---|---:|---:|---|
| [Langfuse](https://langfuse.com/pricing) | Free Hobby | Core USD 29/month; Pro USD 199/month; Enterprise USD 2,499/month | Billable trace/observation units, retention, support and enterprise controls |
| [LangSmith](https://www.langchain.com/pricing) | Free Developer | Plus USD 39/seat/month; Enterprise custom | Seats plus traces, compute/storage usage, deployment and enterprise options |
| [Arize AX](https://arize.com/pricing) | Free AX | Pro USD 50/month; Enterprise custom | Trace volume, ingestion, retention, security and support |
| [Portkey](https://portkey.ai/pricing) | Free, 10k recorded logs/month | Production USD 49/month, with usage overage | Recorded request/log volume, gateway controls and production support |
| [Braintrust](https://www.braintrust.dev/pricing) | Free Starter | Pro USD 249/month; Enterprise custom | Processed data, evaluation scores, retention, RBAC and support |

These are vendor-listed prices and allowances, not like-for-like feature comparisons. Pricing, usage definitions, discounts, and plan contents can change; re-check the official pages before making a commercial decision.

### What this means for AgentOps

1. **Do not compete as another generic tracing dashboard.** The SDK already has metadata-only event recording, OTLP export, and evaluation primitives, but it does not yet provide a hosted observability UI or a full OpenTelemetry SDK.
2. **Differentiate around runtime governance and execution boundaries:** deny-by-default tool policy, principal- and action-bound one-time approvals, cross-language conformance, and hardened subprocess/Docker worker adapters. Communicate their limits honestly; they are not a complete identity platform or escape-proof sandbox.
3. **Keep self-hosted SDK use free.** The market includes open-source/self-hosted alternatives, so monetization should be tied to genuinely delivered managed operations, team administration, support, and integration—not a paywall around the core runtime.
4. **Start with services, not a premature SaaS build.** Implementation and readiness engagements can earn revenue before the hosted control plane exists and reveal which repeatable features customers will pay for.
5. **Treat the suggested USD 19–499 monthly bands as experiments only.** They sit around observed developer/team price points, but AgentOps must validate its own willingness-to-pay and infrastructure economics with design partners before publishing a tariff.

## Revenue streams

### 1. Implementation and readiness services — first revenue priority

Sell a defined, fixed-scope engagement using the current SDK:

- AgentOps architecture and threat-model review.
- Tool-policy and principal-boundary design.
- Human-approval workflow integration.
- Evaluation suite and regression-gate setup.
- Worker/container deployment review.
- Telemetry integration and operational handover.

**Pricing hypotheses to test, not published price commitments:**

| Package | Indicative scope | Initial test range |
|---|---|---:|
| Developer setup | One agent, one environment, quickstart and handover | USD 500–1,500 |
| AgentOps readiness sprint | One production workflow, policy/approval/evaluation setup, security findings report | USD 2,000–7,500 |
| Enterprise implementation | Multiple teams/environments, integration and deployment plan | USD 7,500–25,000+ |

For India-based customers, test equivalent scope-based proposals in INR rather than mechanically converting list prices. Quote only after discovery and a written scope.

### 2. Hosted AgentOps control plane — medium-term recurring revenue

A separately operated hosted service could provide:

- Team workspaces and organization-level access control.
- Hosted trace ingestion, search, dashboards, and retention controls.
- Evaluation history, scheduled evaluation, regression alerts, and CI integrations.
- Central policy and approval administration.
- Usage metering, team-level quotas, and audit exports.
- Managed connectors and deployment health monitoring.

None of these hosted capabilities should be advertised as available until implemented, secured, and operated.

**Pricing experiments after a working private beta:**

| Tier | Candidate customer | Monthly hypothesis |
|---|---|---:|
| Community | Individual developer; local SDK use | Free |
| Builder | Solo builder with hosted history and basic alerts | USD 19–29 |
| Team | Small product team, collaboration and longer retention | USD 79–149 |
| Business | Multiple projects, advanced controls and support | USD 249–499 |
| Enterprise | Dedicated deployment, contractual controls and support | Custom annual contract |

These are discovery anchors only. Validate willingness to pay, infrastructure cost, support burden, and gross margin before publishing prices.

### 3. Enterprise support and assurance

Potential paid offerings once the operating capability exists:

- Priority response and named technical contact.
- Supported deployment patterns and upgrade assistance.
- Security architecture workshops and deployment reviews.
- Custom retention, identity, audit, and integration requirements.
- Long-term support windows for tagged SDK releases.

Do not promise certifications, regulatory compliance, or service-level guarantees without the relevant controls, evidence, legal review, and operational capacity.

### 4. Training and partner enablement

Offer paid workshops for engineering teams and integration partners. Publish the core learning material openly where practical; charge for live delivery, tailored labs, and customer-specific implementation.

## Packaging and positioning

**Category:** Open-source AgentOps infrastructure for AI agent governance, evaluation, and execution operations.

**Core promise:** Make agent behavior testable, permissioned, traceable, and safer to operate—without forcing a model-provider or cloud-provider choice.

**Proof points to earn before making strong claims:**

- Reproducible Python and TypeScript SDK releases.
- Cross-language conformance tests.
- Real Docker integration tests and documented trust boundaries.
- Independent security review with published findings and remediation evidence.
- Real customer case studies with permission and measurable outcomes.
- Clear performance, reliability, and data-retention documentation.

Avoid unsupported claims such as “fully secure,” “enterprise-ready,” “compliant,” “zero risk,” or “production-ready.”

## Go-to-market sequence

### Stage 1 — Developer adoption

- Keep quickstarts runnable and short.
- Publish versioned packages and tagged releases only after release checks pass.
- Provide copy-paste examples for policy, approval, evaluation, and worker use.
- Maintain a public issue triage process and contribution guide.
- Measure successful installs, first successful execution, repeat use, and external contributions.

### Stage 2 — Design partners

Recruit 5–10 AI teams for structured discovery and hands-on pilots. Ask each team to bring one real workflow, one operational pain point, and a measurable success criterion. Obtain explicit permission before publishing any logo, quote, metric, or case study.

### Stage 3 — Paid implementation

Convert qualified pilots into fixed-scope readiness and integration engagements. Use services to learn which capabilities are repeatedly requested before building a hosted product.

### Stage 4 — Hosted beta

Build only after design partners demonstrate repeated demand for shared history, collaboration, hosted evaluation, and centralized governance. Start with a narrow multi-tenant boundary, tenant isolation tests, authentication, authorization, data deletion/export, billing controls, incident response, and observability.

### Stage 5 — Enterprise expansion

Add self-hosted or dedicated deployment, SSO, audit export, retention controls, support commitments, and contractual assurance only after their security and operational requirements are independently validated.

## Metrics and decision gates

Track these metrics monthly:

- Acquisition: qualified visitors, documentation-to-install conversion, package downloads.
- Activation: first successful policy check, approval flow, evaluation run, and worker execution.
- Retention: weekly active projects and repeat evaluations.
- Product value: regression findings caught before deployment, approval decisions, and time to integrate.
- Community: external contributors, issue response time, merged external PRs.
- Commercial: qualified discovery calls, paid pilots, conversion rate, recurring revenue, churn, support hours, and gross margin.
- Reliability: CI pass rate, release rollback rate, incident count, and time to remediate security findings.

Do not use GitHub stars as the primary product-market-fit metric.

## Immediate execution priorities

1. Close the release-readiness gaps in `docs/SECURITY_MODEL.md` and the Phase 15 tracker before making production-readiness claims.
2. Commit and verify the npm lockfile; move CI to `npm ci`.
3. Publish versioned Python and TypeScript packages with provenance and release notes after reproducible builds are in place.
4. Add end-to-end tutorials and a minimal production-style sample application.
5. Conduct structured customer discovery and sell the first implementation sprint before investing in a full hosted platform.
6. Create a separate hosted-service architecture only after design-partner evidence supports it.

## Commercial integrity

- Apache-2.0 remains the license for the existing open-source core.
- Do not claim that planned hosted features already exist.
- Do not collect prompts, tool arguments, results, secrets, or customer data for analytics by default.
- Document data processing, retention, deletion, residency, subprocess/container trust boundaries, and subprocessors before hosting customer data.
- Keep customer data private; never use customer workloads as public demos without explicit written permission.
- Obtain legal and tax advice for applicable jurisdictions before selling subscriptions or enterprise services.
