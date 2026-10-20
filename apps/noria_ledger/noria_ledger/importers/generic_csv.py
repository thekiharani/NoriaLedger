"""Generic bank CSV.

Column mapping may be supplied explicitly; otherwise common header names are
detected. Supports either separate deposit/withdrawal columns or a single signed
amount column (positive = money in).
"""

from decimal import Decimal

from noria_ledger.importers.base import StatementError, StatementRow, find_column, parse_amount, parse_date, read_csv


class GenericCSVParser:
	code = "generic_csv"
	label = "Bank statement (CSV)"

	def __init__(self, mapping: dict | None = None, date_format: str | None = None):
		self.mapping = mapping or {}
		self.date_format = date_format or None

	def parse(self, content: str) -> list[StatementRow]:
		rows = read_csv(content)
		if not rows:
			return []
		headers = list(rows[0].keys())

		def col(key, *candidates):
			explicit = self.mapping.get(key)
			if explicit:
				if explicit not in headers:
					raise StatementError(f"Mapped column '{explicit}' for {key} is not in the file")
				return explicit
			return find_column(headers, *candidates)

		date_col = col("date", "date", "transaction date", "posting date", "value date", "txn date")
		desc_col = col("description", "description", "narration", "details", "particulars", "transaction details")
		ref_col = col("reference", "reference", "ref", "reference number", "cheque no", "chq/ref no")
		id_col = col("transaction_id", "transaction id", "transaction ref", "bank reference")
		dep_col = col("deposit", "deposit", "credit", "money in", "paid in", "credit amount")
		wd_col = col("withdrawal", "withdrawal", "debit", "money out", "withdrawn", "debit amount")
		amt_col = col("amount", "amount", "transaction amount")

		if not date_col:
			raise StatementError("Could not find a date column; provide a column mapping")
		if not ((dep_col and wd_col) or amt_col):
			raise StatementError("Need deposit and withdrawal columns, or a signed amount column")

		parsed = []
		for i, row in enumerate(rows, start=2):
			if not any(row.values()):
				continue
			if dep_col and wd_col:
				deposit = parse_amount(row.get(dep_col, ""), i, "deposit")
				withdrawal = parse_amount(row.get(wd_col, ""), i, "withdrawal")
				deposit, withdrawal = abs(deposit), abs(withdrawal)
			else:
				amount = parse_amount(row.get(amt_col, ""), i, "amount")
				deposit = amount if amount > 0 else Decimal("0")
				withdrawal = -amount if amount < 0 else Decimal("0")
			if deposit == 0 and withdrawal == 0:
				continue
			if deposit and withdrawal:
				raise StatementError(f"Line {i}: both deposit and withdrawal are set")
			parsed.append(
				StatementRow(
					line=i,
					date=parse_date(row.get(date_col, ""), i, self.date_format),
					description=row.get(desc_col, "") if desc_col else "",
					deposit=deposit,
					withdrawal=withdrawal,
					reference=row.get(ref_col, "") if ref_col else "",
					transaction_id=row.get(id_col, "") if id_col else "",
				)
			)
		return parsed
