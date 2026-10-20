"""M-PESA statement CSV.

Targets the CSV statement layout with the columns
  Receipt No. | Completion Time | Details | Transaction Status | Paid In | Withdrawn | Balance
(optionally Initiation Time, Reason Type, Other Party Info, Linked Transaction ID,
A/C No.) as exported for M-PESA business (organisation portal) and personal
statements converted to CSV. Header matching is case/punctuation tolerant.

This layout must be validated against real customer exports before relying on it
(see docs/KNOWN_LIMITATIONS.md); there is no public, versioned specification.
Only rows with Transaction Status "Completed" (or no status column) are imported.
The receipt number is used as the duplicate-detection key.
"""

from noria_ledger.importers.base import StatementError, StatementRow, find_column, parse_amount, parse_date, read_csv


class MpesaCSVParser:
	code = "mpesa_csv"
	label = "M-PESA statement (CSV)"

	def __init__(self, mapping: dict | None = None, date_format: str | None = None):
		self.date_format = date_format or None

	def parse(self, content: str) -> list[StatementRow]:
		rows = read_csv(content)
		if not rows:
			return []
		headers = list(rows[0].keys())
		receipt = find_column(headers, "receipt no", "receipt number", "receipt")
		completed = find_column(headers, "completion time", "completion date", "date")
		details = find_column(headers, "details", "description")
		status = find_column(headers, "transaction status", "status")
		paid_in = find_column(headers, "paid in", "paid in (ksh)", "credit")
		withdrawn = find_column(headers, "withdrawn", "withdrawn (ksh)", "withdrawal", "debit")
		other_party = find_column(headers, "other party info", "other party")
		missing = [n for n, c in (("Receipt No.", receipt), ("Completion Time", completed), ("Paid In", paid_in), ("Withdrawn", withdrawn)) if not c]
		if missing:
			raise StatementError("Not an M-PESA statement: missing columns " + ", ".join(missing))

		parsed = []
		for i, row in enumerate(rows, start=2):
			if not row.get(receipt):
				continue
			if status and row.get(status, "").strip().lower() not in ("completed", ""):
				continue
			deposit = abs(parse_amount(row.get(paid_in, ""), i, "Paid In"))
			withdrawal = abs(parse_amount(row.get(withdrawn, ""), i, "Withdrawn"))
			if not deposit and not withdrawal:
				continue
			parsed.append(
				StatementRow(
					line=i,
					date=parse_date(row.get(completed, ""), i, self.date_format),
					description=row.get(details, "") if details else "",
					deposit=deposit,
					withdrawal=withdrawal,
					reference=row.get(receipt, ""),
					transaction_id=row.get(receipt, ""),
					party_name=row.get(other_party, "") if other_party else "",
				)
			)
		return parsed
