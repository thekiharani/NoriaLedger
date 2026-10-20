import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_ROWS = 20000
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d %b %Y", "%d-%b-%Y", "%Y/%m/%d")
DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M")


class StatementError(ValueError):
	pass


@dataclass(frozen=True)
class StatementRow:
	line: int
	date: date
	description: str
	deposit: Decimal
	withdrawal: Decimal
	reference: str = ""
	transaction_id: str = ""
	party_name: str = ""

	def fingerprint(self, bank_account: str, occurrence: int = 0) -> str:
		"""Stable duplicate-detection key.

		Uses the bank's own transaction id when the format provides one (e.g. the
		M-PESA receipt number); otherwise date + amounts + reference + description.
		`occurrence` distinguishes genuinely identical lines inside one statement
		(e.g. two equal bank charges on the same day): the n-th identical line of a
		file always gets the same key, so re-importing the file is still detected.
		"""
		if self.transaction_id:
			basis = f"{bank_account}|id|{self.transaction_id.strip().upper()}"
		else:
			basis = "|".join(
				[
					bank_account,
					self.date.isoformat(),
					str(self.deposit),
					str(self.withdrawal),
					self.reference.strip().upper(),
					" ".join(self.description.split()).upper(),
				]
			)
		if occurrence and not self.transaction_id:
			basis = f"{basis}|#{occurrence}"
		return hashlib.sha256(basis.encode()).hexdigest()


def read_csv(content: str) -> list[dict]:
	content = content.lstrip("﻿")
	sample = content[:4096]
	try:
		dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
	except csv.Error:
		dialect = csv.excel
	reader = csv.DictReader(io.StringIO(content), dialect=dialect)
	if not reader.fieldnames:
		raise StatementError("The statement has no header row")
	reader.fieldnames = [(h or "").strip() for h in reader.fieldnames]
	rows = []
	for row in reader:
		if len(rows) >= MAX_ROWS:
			raise StatementError(f"Statements are limited to {MAX_ROWS} rows per import")
		rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None})
	return rows


def parse_amount(value: str, line: int, field: str) -> Decimal:
	raw = (value or "").strip()
	if raw in ("", "-"):
		return Decimal("0")
	negative = raw.startswith("(") and raw.endswith(")")
	cleaned = raw.strip("()").replace(",", "").replace("KES", "").replace("Ksh", "").replace(" ", "")
	try:
		amount = Decimal(cleaned)
	except InvalidOperation:
		raise StatementError(f"Line {line}: invalid {field} '{value}'") from None
	if not amount.is_finite():
		raise StatementError(f"Line {line}: invalid {field} '{value}'")
	amount = -amount if negative else amount
	return amount.quantize(Decimal("0.01"))


def parse_date(value: str, line: int, date_format: str | None = None) -> date:
	raw = (value or "").strip()
	formats = (date_format,) if date_format else DATETIME_FORMATS + DATE_FORMATS
	for fmt in formats:
		try:
			return datetime.strptime(raw, fmt).date()
		except (ValueError, TypeError):
			continue
	raise StatementError(f"Line {line}: unrecognised date '{value}'")


def find_column(headers: list[str], *candidates: str) -> str | None:
	normalised = {h.lower().replace(".", "").replace("_", " ").strip(): h for h in headers}
	for c in candidates:
		key = c.lower().replace(".", "").replace("_", " ").strip()
		if key in normalised:
			return normalised[key]
	return None
