# ServiceNow ITAM Add-on Discovery Questions (Pre-Blueprint)

These clarifying questions must be answered before producing the build-ready MVP + v1 architecture blueprint.

## 1) Telemetry source and collection constraints
- Which MVP telemetry source do you want to commit to first: **Intune/Defender**, **Tanium**, or a **custom Windows collector**?
- If using an existing source, what exact fields are currently available for GPU utilization, VRAM usage, disk latency, and thermal/throttle events?
- Are there endpoint performance/agent overhead limits we must stay under (e.g., CPU <2%, memory <150MB, network budget/day)?

## 2) Tenant and identity model
- Is this a **single enterprise tenant** in MVP or true multi-tenant SaaS from day one?
- What should be the canonical device identity key across systems (e.g., serial number, BIOS UUID, Azure AD device ID, ServiceNow sys_id mapping table)?
- Do users/devices ever move between business units that require logical tenant/sub-tenant boundaries?

## 3) ServiceNow integration boundaries
- Which ServiceNow modules are licensed and in scope now: ITAM only, ITOM/Discovery, Performance Analytics, IntegrationHub, Flow Designer?
- Are we allowed to extend `cmdb_ci_computer` and `alm_hardware` directly with `u_*` fields, or do you prefer related extension tables only?
- Should integration run via ServiceNow Table API directly, Import Set API + Transform Maps, or MID Server-mediated flow (network/security policy dependent)?

## 4) Recommendation and action policy
- Who is the decision authority for automatic actions (e.g., DOWNSIZE/UPSIZE), and do we require human approval for all actions in MVP?
- What are acceptable risk tolerances for false-positive downsizing (e.g., max 2% users impacted)?
- Do you already have hardware catalog tiers (A/B/C/D definitions), or should we propose baseline tier specs by persona?

## 5) Privacy, legal, and governance
- Do you require **strict mode** to be globally enforced, opt-in by department, or configurable per policy?
- Any jurisdictions/data residency requirements (EU-only, US-only, region pinning) we must enforce in MVP?
- What retention limits are mandated for raw telemetry vs daily aggregates (e.g., 30 days raw, 1 year aggregate)?

## 6) Security and enterprise auth
- Which identity provider and SSO standard should the web app use (Azure AD/Entra ID, Okta; SAML vs OIDC)?
- Is mTLS required for collector-to-ingestion traffic, and do you already have PKI/certificate rotation standards?
- Any mandatory controls to align with (SOC 2, ISO 27001, FedRAMP, HIPAA, internal secure baseline)?

## 7) UX, workflows, and operating model
- Primary MVP users: ITAM analysts only, or also desktop engineering and finance/procurement stakeholders?
- Which workflows are highest priority at launch: **reallocation**, **upgrade**, **exception handling**, **refresh planning**?
- Do you need executive dashboarding in ServiceNow only, or also in the add-on web app?

## 8) Scale, SLOs, and rollout
- Expected endpoint count at MVP go-live and 12-month horizon (within 5k–100k range)?
- Data freshness/SLA expectations (daily batch by 6 AM local vs near-real-time)?
- Rollout strategy: pilot group first (which departments/workloads), then phased expansion?

## 9) Learning layer readiness
- Do you have historical outcomes (upgrade tickets, user satisfaction, incident rates) that can label training data for supervised models in v1?
- Are there approved model governance requirements (explainability templates, approval board, retraining cadence)?
- Should the model be allowed to abstain when confidence is low and default to rules-only recommendations?

## 10) Program constraints
- What is the target MVP date in the 8–12 week window?
- Team composition available (backend, data, ServiceNow admin/dev, frontend, security) and any skill gaps to design around?
- Any non-negotiable technology constraints (cloud provider, database standard, queue standard, no-new-infra rule)?
