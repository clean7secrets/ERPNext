"""Per-client document numbering.

Every client company gets its own number sequence, e.g. JGE-2627-0001 for Jay Gurudev Enterprises'
first invoice of financial year 2026-27. Sequences restart each financial year (April-March) and stay
within the GST limit of 16 characters for invoices, credit notes and debit notes.
"""

import frappe
from frappe.utils import getdate, nowdate

# doctype -> series, or a function of the document returning the series.
SERIES = {
	"Sales Invoice": lambda d: (
		"C-.ABBR.-.FYS.-.###" if d.get("is_return")
		else "D-.ABBR.-.FYS.-.###" if d.get("is_debit_note")
		else ".ABBR.-.FYS.-.####"
	),
	"Quotation": lambda d: "QT-.ABBR.-.FYS.-.####",
	"Sales Order": lambda d: "SO-.ABBR.-.FYS.-.####",
	"Delivery Note": lambda d: "DC-.ABBR.-.FYS.-.####",
	"Payment Entry": lambda d: (
		"RCPT-.ABBR.-.FYS.-.####" if d.get("payment_type") == "Receive"
		else "PAY-.ABBR.-.FYS.-.####" if d.get("payment_type") == "Pay"
		else "TRF-.ABBR.-.FYS.-.####"
	),
	"Purchase Invoice": lambda d: "BILL-.ABBR.-.FYS.-.####",
	"Purchase Order": lambda d: "PO-.ABBR.-.FYS.-.####",
	"Purchase Receipt": lambda d: "GRN-.ABBR.-.FYS.-.####",
	"Journal Entry": lambda d: "JV-.ABBR.-.FYS.-.####",
	"Stock Entry": lambda d: "STK-.ABBR.-.FYS.-.####",
}

# Every series a doctype can produce, so the naming_series select accepts them.
ALL_SERIES = {
	"Sales Invoice": [".ABBR.-.FYS.-.####", "C-.ABBR.-.FYS.-.###", "D-.ABBR.-.FYS.-.###"],
	"Payment Entry": ["RCPT-.ABBR.-.FYS.-.####", "PAY-.ABBR.-.FYS.-.####", "TRF-.ABBR.-.FYS.-.####"],
}


def series_options(doctype):
	if doctype in ALL_SERIES:
		return ALL_SERIES[doctype]
	return [SERIES[doctype](frappe._dict())]


def set_series(doc, method=None):
	"""before_insert: pick the company's series. Amended documents keep ERPNext's own -1, -2 naming."""
	if doc.get("amended_from") or not doc.get("company") or not doc.meta.has_field("naming_series"):
		return
	rule = SERIES.get(doc.doctype)
	if rule:
		doc.naming_series = rule(doc)


def fiscal_year_short(doc, variable=None):
	"""Naming series variable FYS: 2026-27 -> '2627'."""
	from erpnext.accounts.utils import get_fiscal_year

	date = (doc and (doc.get("posting_date") or doc.get("transaction_date"))) or nowdate()
	company = doc.get("company") if doc else None
	fy = get_fiscal_year(date=date, company=company, as_dict=True)
	start, end = getdate(fy.year_start_date).year, getdate(fy.year_end_date).year
	return f"{start % 100:02d}{end % 100:02d}"
