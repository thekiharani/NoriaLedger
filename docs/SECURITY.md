# Security & Data Protection

## 1. Controls implemented (and how they are verified)

| Requirement | Implementation | Verified by |
|---|---|---|
| Secure authentication | Frappe login (`/api/method/login`), password hashing by Frappe, HttpOnly `sid` cookie | E2E, Playwright |
| MFA support | Frappe two-factor auth (System Settings → Enable Two Factor Auth). The SPA login handles Frappe's OTP step (`verification` + `tmp_id`). | Manual only — **not automated yet** |
| CSRF | Frappe CSRF token from `session.bootstrap`, sent as `X-Frappe-CSRF-Token` on every POST | curl smoke test: POST without token → 400 |
| Server-side authorization | `noria_practice/authz.py` used by every hub endpoint; hub DocTypes are System-Manager-only | 29 hub tests |
| Firm/client isolation | separate DB per client; access via engagement + assignment; no existence oracle | hub tests, E2E step 11 |
| Client sites not exposed | edge overwrites `Host`/`X-Frappe-Site-Name`; allow-listed `/api` paths only | curl smoke tests, infra checks |
| Least privilege between services | DB root secret only in `db` + `provisioner`; service user without System Manager | compose review |
| Entitlements | `require_module` on the server for every operation | hub tests |
| Audit trails | Hub: `Noria Audit Event` (views, writes, downloads, workflow transitions). Client site: `Noria Activity Log` + `noria_acting_user` on vouchers. ERPNext's own versioning remains. | hub tests |
| Protected file access | Files are private on the client site and downloaded only through authorized endpoints; every download is logged on both hub and site; SHA-256 integrity checked on download; extension + magic-byte checks on upload; 20 MB limit | hub tests |
| Input validation | Zod on the client; strict server validation (decimals ≤ 2 dp, balanced journals, account ownership, enums) | ledger tests |
| Rate limiting | Frappe login lockout (System Settings); `@rate_limit` on firm sign-up (5/hour/IP) | — |
| Security headers | CSP (no inline scripts), HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy | curl |
| HTTPS | Caddy automatic certificates when `NORIA_SITE_ADDRESS` is a domain | production setup |
| Backup encryption | `encrypt_backup` enabled on every site (GPG, per-site key in site config) | infra checks (encrypted backup + restore) |
| Secrets | Docker secrets / secret files, never in images or `.env`; build-time CA via BuildKit secret | review |
| Tracebacks | not shown to Noria users (Website Users); client-site errors reduced to messages by the broker | — |

## 2. Known gaps (must close before production)

1. **MFA enforcement policy:** decide whether MFA is mandatory for firm users; add an automated test of the OTP flow.
2. **Session hardening:** review `session_expiry`, deny multiple concurrent sessions for admins, cookie `Secure` behind
   TLS (automatic when served over HTTPS).
3. **Edge rate limiting** for login and uploads (needs a Caddy rate-limit plugin or an upstream WAF).
4. **Payment webhook validation:** no webhooks exist yet; the Daraja module must verify source and signatures.
5. **Credential rotation:** `noria_ledger.provisioning.rotate_service_credentials` exists; a scheduled rotation plus
   hub update is not automated.
6. **Image vulnerability scanning:** not run in this environment (no scanner available offline). Add `trivy image`
   or Docker Scout to CI and record results.
7. **Penetration test** by an independent party.
8. **Platform-operator access:** System Managers can use the Frappe desk (bound to `127.0.0.1` via
   `admin-frontend`). Add per-operator accounts, MFA and audit review procedures.

## 3. Kenya Data Protection Act 2019 — obligations to plan for

Secondary sources (law-firm notes and ODPC material) summarise the main obligations below. **Obtain legal advice;
this is not legal advice.**

* **Registration:** data controllers and processors must register with the Office of the Data Protection Commissioner
  (ODPC); certificates are time-limited (ODPC material indicates two years).
  [ODPC Z-card](https://www.odpc.go.ke/wp-content/uploads/2024/02/PERSONAL-DATA-PROTECTION-Z-CARD.pdf)
* **Roles:** for client books, the accounting firm (and the business) are typically controllers and Noria a processor.
  Contracts (DPAs) should reflect this, including sub-processors (hosting, email).
* **Breach notification:** controller → Data Commissioner within **72 hours** of becoming aware. A processor must notify
  the controller (sources cite 48 hours). Data subjects must be notified without undue delay when risk is high.
  [Bowmans](https://bowmanslaw.com/insights/kenya-a-few-insights-on-navigating-data-breaches-in-kenya-under-the-kenyan-data-protection-law/),
  [Securiti](https://securiti.ai/kenya-data-protection-act-dpa/)
* **DPIA** for high-risk processing; **data minimisation** and retention limits; **data-subject rights** (access,
  correction, deletion where lawful — tax law requires retaining books).
* **Cross-border transfers** need appropriate safeguards. Hosting location is therefore a product decision.
* **AI features:** no client data is sent to external AI services. Any future AI feature requires consent, contracts
  and access controls first.

Operational support already in place: per-client databases (scoped export/erasure), audit logs, encrypted backups,
and no external data flows.
