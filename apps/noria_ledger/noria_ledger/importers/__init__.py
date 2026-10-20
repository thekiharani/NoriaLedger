"""Pluggable bank-statement parsers.

Each parser turns an uploaded statement into normalised rows. Adding a bank
format means adding a module and registering it in PARSERS; nothing else changes.
"""

from noria_ledger.importers.base import StatementRow
from noria_ledger.importers.generic_csv import GenericCSVParser
from noria_ledger.importers.mpesa import MpesaCSVParser

PARSERS = {
	GenericCSVParser.code: GenericCSVParser,
	MpesaCSVParser.code: MpesaCSVParser,
}


def get_parser(code: str):
	try:
		return PARSERS[code]
	except KeyError:
		raise ValueError(f"Unknown statement format '{code}'. Known: {', '.join(sorted(PARSERS))}") from None


__all__ = ["PARSERS", "StatementRow", "get_parser"]
