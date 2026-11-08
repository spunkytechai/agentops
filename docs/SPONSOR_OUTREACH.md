# Corporate Sponsor Outreach Kit

This document is a prospecting aid. The organizations below are potential prospects only; none is represented as a sponsor, partner, customer, or endorser.

## Current positioning

AgentOps is an early-stage Apache-2.0 project with Python and TypeScript SDKs. Its implemented foundation includes tool policy, action-bound human approvals, evaluation and regression comparison, operational event/OTLP export, and subprocess/Docker worker adapters.

Be candid about maturity: the repository is 0.x, has no published stable release, no public customer case studies, and has not completed its independent security review. The initial ask is to fund open-source engineering and/or provide scoped developer infrastructure credits—not to underwrite a production service that does not yet exist.

## Prospect segments

Prioritize sponsors whose developer ecosystem benefits from safer AI-agent infrastructure:

1. **Cloud and compute:** AWS, Google Cloud, Microsoft Azure, Cloudflare, DigitalOcean, NVIDIA, and Modal. Ask for time-bounded compute, CI, artifact storage, or GPU credits with clear limits.
2. **Model/API ecosystem:** OpenAI, Anthropic, Mistral AI, Cohere, Together AI, and Fireworks AI. Ask for modest API credits for public examples and conformance work, with spend caps and no requirement to expose private data.
3. **Developer infrastructure:** GitHub, Docker, Sentry, and security tooling providers. Ask for CI minutes, container tooling, security review capacity, or developer tooling credits.
4. **AI developer ecosystem programmes:** open-source funds, startup programmes, incubators, and developer grants that accept independent open-source projects.

Prioritize programmes with published open-source or developer-infrastructure support criteria. Do not send mass generic requests.

## Sponsor qualification

Before outreach, score each prospect on:

- Strategic fit with agent governance, security, evaluation, or developer infrastructure.
- Whether it has a public open-source sponsorship or credits programme.
- Whether the benefit is actually useful to this repository.
- Application requirements, geography, stage, and deadline.
- Restrictions, expiry, renewal, and whether the credit creates vendor lock-in.
- Whether the sponsor requires exclusivity, product endorsement, data access, or roadmap control (normally decline these terms).

Start with 10 well-matched prospects, not a large scraped email list. Use public programme application forms or published partnership contacts. Do not guess personal email addresses.

## Suggested first ask

For the first 90 days, ask for one of:

- USD 1,000–5,000 equivalent in unrestricted project sponsorship, subject to an agreed written scope and compliant payment route; or
- USD 1,000–5,000 in clearly scoped cloud/compute/CI/API credits with a 6–12 month validity window; or
- A sponsored independent security review with a written findings report and permission to publish a sanitized summary.

These are exploratory asks, not an established rate card. Adjust to each programme's actual grant size and application rules. Avoid representing in-kind credits as cash revenue.

## Outreach email

**Subject:** Open-source sponsorship proposal — AgentOps (Python + TypeScript)

Hello [Name / Developer Relations Team],

I'm building AgentOps at Spunky Tech, an Apache-2.0 open-source project focused on the operational foundations for AI agents.

The repository provides Python and TypeScript SDK foundations for deny-by-default tool policy, action-bound human approvals, evaluation and regression checks, execution telemetry, and isolated worker adapters. We are currently in early development and are working through reproducible releases and an independent security review.

We are inviting a small number of ecosystem sponsors to support the next stage of open development: cross-language reliability, security review and remediation, documentation, and developer infrastructure.

Would [Company] consider supporting the project through a modest open-source sponsorship, a scoped developer-credits grant, or security-review support? We can share the public roadmap, agree on transparent recognition, and provide periodic progress updates. Sponsorship would not provide control over the roadmap, access to customer data, or product endorsement.

Project: https://github.com/spunkytechai/agentops  
Sponsorship information: https://github.com/spunkytechai/agentops/blob/main/docs/SPONSORSHIP.md

If this is relevant, I'd be glad to send a short project brief and discuss a suitable scope.

Regards,  
S Haider  
Spunky Tech

## Follow-up sequence

- Day 0: send a personalized note through the official programme or contact route.
- Day 5–7: send one concise follow-up with a specific use of funds/credits.
- Day 12–14: close the loop politely if there is no response.
- Record outcomes and programme restrictions. Do not repeatedly contact people who decline or opt out.

## What to send with the request

- Repository and Apache-2.0 license.
- Current architecture and security model.
- Release roadmap and explicit known limitations.
- Exact budget or credit request with line-item use.
- 90-day milestones and measurable outputs.
- Sponsorship recognition policy.
- Legal entity / contracting and tax details only after the prospect's official process requests them.

## 90-day sponsor-funded milestone proposal

| Period | Work | Evidence |
|---|---|---|
| Days 1–30 | Reproducible TypeScript install, package release checks, sample workflows | Locked install, green CI, tagged candidate |
| Days 31–60 | Independent security assessment and remediation | Findings register, fixes, sanitized report |
| Days 61–90 | Documentation, compatibility, community adoption | Examples, release notes, issue/contribution metrics |

The milestones are proposed; commit only after sponsor scope, resources, and acceptance criteria are agreed.

## Sponsor pipeline

Track prospects in a private CRM or spreadsheet with: company, programme URL, fit score, contact route, requested support, amount/credit value, application date, follow-up date, status, restrictions, and next action. Do not store confidential sponsor correspondence in public repository issues.
