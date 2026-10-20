# Kenya Tax & Compliance — Status and Design

**What exists today:** statutory work is tracked as configurable task templates; VAT is calculated by ERPNext tax
templates; M-PESA statement import exists. **There is no automatic KRA filing and no eTIMS integration.** Noria
does not claim either.

## 1. Verification status of key rules

Sources found during the audit were secondary (vendor guides, law-firm notes); KRA's own calendar was not
retrieved. Treat every value below as **"verify against KRA/iTax before relying on it."** That is why the due-date
offsets are *data* (Task Templates editable by operators), not code.

| Obligation | Default in Noria (editable) | Basis found | Status |
|---|---|---|---|
| VAT return (VAT3) | due 20 days after period end | vendor guide: "by the 20th" | to verify with KRA |
| PAYE (P10) | due 9 days after period end | vendor guide: "by the 9th" | to verify with KRA |
| Withholding tax | not templated | sources disagree on "20th" vs. "within 5 working days of deduction" | **verify before adding** |
| Instalment tax | not templated | — | roadmap |
| Corporate income tax | Year-End Closing template only | — | roadmap |
| VAT standard rate 16 % | ERPNext `Kenya Tax` template (upstream data) | ERPNext `country_wise_tax.json` | verify per client (exempt/zero-rated supplies need extra templates) |

Source used: [Odoo Kenya localization guide 2026 (ecosire)](https://ecosire.com/blog/odoo-kenya-localization-guide-2026) —
a vendor publication, not KRA.

## 2. eTIMS

Secondary sources state that eTIMS e-invoicing is mandatory for VAT-registered taxpayers and is offered as Online,
Lite, OSCU and VSCU integration modes. A system-to-system integration needs KRA's official OSCU/VSCU
specification, sandbox credentials and (typically) integrator approval. **None of these were available**, so no
eTIMS code was written. Do not imply eTIMS compliance in sales material until an approved integration exists and
is tested.

Planned design (not implemented):

* `noria_ledger` module `etims`: on Sales Invoice submit, enqueue a job that signs/transmits the invoice through
  the approved OSCU/VSCU interface. Store the KRA control unit invoice number and QR data on custom fields. Retry
  idempotently using the invoice name as the key.
* Never block ERPNext posting on KRA availability; show "pending eTIMS" status and alert instead.
* Per-client device and credential configuration stored encrypted on the client site.

## 3. iTax filing

KRA iTax has no public filing API. Noria supports **preparation and evidence**: tasks, working papers (ERPNext
reports and exports), document upload of acknowledgement receipts, and statuses. Filing itself stays manual.

## 4. M-PESA

* **Implemented:** CSV statement import (`noria_ledger/importers/mpesa.py`) for the column layout
  *Receipt No., Completion Time, Details, Transaction Status, Paid In, Withdrawn, Balance*. Failed transactions are
  skipped and the receipt number is the duplicate key. **This layout must be validated with real customer exports**
  (Org Portal and personal statements differ, and statements often arrive as password-protected PDFs, which are not
  supported).
* **Not implemented:** Daraja API (C2B/B2C) payment integrations. These require Safaricom credentials and callback
  validation (IP allow-listing and/or signature checks per Daraja documentation) and will be added as a separate,
  explicitly labelled module.

## 5. Payroll / statutory deductions

Not implemented (module `payroll` exists only as an entitlement). Payroll would use Frappe HRMS on client sites;
PAYE bands, personal relief, NSSF, SHIF and the Housing Levy must be configured from official sources at
implementation time, not hard-coded.
