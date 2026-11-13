"""Phase 1 of the Online Books simplification: clean desk, per-client numbering and defaults, invoice layouts.

Everything here is idempotent and runs on every migrate (setup.ensure_setup -> ensure).
"""

import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from rpa_integration.numbering import SERIES, series_options
from rpa_integration.printing import LAYOUTS

PORTAL = "https://caronakpatel.com"
LOGO_FILE = "rpa-books-icon-m.png"  # letterhead ring with "Books" in the letterhead's script style
GST_ICON_FILE = "rpa-gst-icon-m.png"  # letterhead ring with "GST"
WORDMARK_FILE = "rpa-letterhead-logo.png"  # the firm letterhead header, used as is
OLD_LOGO_FILES = ("ca-books-logo.png", "books-mark.png", "books-logo.png", "rpa-books-mark.png", "rpa-books-logo.png", "rpa-letterhead-ring.png", "rpa-books-icon.png", "rpa-gst-icon.png")

INVOICE_FORMATS = {f"Books - {label}": key for key, label in LAYOUTS.items()}
MY_STYLE = {"Sales Invoice": "Books Invoice - My style", "Quotation": "Books Quote - My style"}


def ensure():
	style_fields()
	numbering()
	print_formats()
	desk()
	from rpa_integration import branding, phase2
	branding.ensure()
	phase2.ensure()
	for company in frappe.get_all("Company", pluck="name"):
		company_defaults(company)


# ------------------------------------------------------------------ invoice style fields on Company

def style_fields():
	layouts = "\n".join(LAYOUTS.values())
	create_custom_fields({"Company": [
		{"fieldname": "rpa_inv_section", "label": "Invoice style", "fieldtype": "Section Break",
		 "insert_after": "rpa_portal_user", "collapsible": 1},
		{"fieldname": "rpa_inv_layout", "label": "Layout", "fieldtype": "Select", "options": layouts,
		 "default": "Classic GST", "insert_after": "rpa_inv_section"},
		{"fieldname": "rpa_inv_colour", "label": "Brand colour", "fieldtype": "Color", "default": "#003366",
		 "insert_after": "rpa_inv_layout"},
		{"fieldname": "rpa_inv_font", "label": "Font", "fieldtype": "Select", "options": "Sans\nSerif\nRounded",
		 "default": "Sans", "insert_after": "rpa_inv_colour"},
		{"fieldname": "rpa_inv_second_language", "label": "Second language", "fieldtype": "Select",
		 "options": "Hindi\nMarathi", "default": "Hindi", "insert_after": "rpa_inv_font",
		 "description": "Used by the Bilingual layout"},
		{"fieldname": "rpa_inv_show_hsn", "label": "Show HSN/SAC", "fieldtype": "Check", "default": "1",
		 "insert_after": "rpa_inv_second_language"},
		{"fieldname": "rpa_inv_show_discount", "label": "Show discount column", "fieldtype": "Check",
		 "default": "1", "insert_after": "rpa_inv_show_hsn"},
		{"fieldname": "rpa_inv_show_uom", "label": "Show unit", "fieldtype": "Check", "default": "1",
		 "insert_after": "rpa_inv_show_discount"},
		{"fieldname": "rpa_inv_upi_id", "label": "UPI ID for payment QR", "fieldtype": "Data",
		 "insert_after": "rpa_inv_show_uom", "description": "e.g. business@okhdfcbank"},
		{"fieldname": "rpa_inv_col_1", "fieldtype": "Column Break", "insert_after": "rpa_inv_upi_id"},
		{"fieldname": "rpa_inv_logo", "label": "Logo", "fieldtype": "Attach Image", "insert_after": "rpa_inv_col_1"},
		{"fieldname": "rpa_inv_signature", "label": "Signature", "fieldtype": "Attach Image",
		 "insert_after": "rpa_inv_logo"},
		{"fieldname": "rpa_inv_letterhead_header", "label": "Letterhead header image", "fieldtype": "Attach Image",
		 "insert_after": "rpa_inv_signature"},
		{"fieldname": "rpa_inv_letterhead_footer", "label": "Letterhead footer image", "fieldtype": "Attach Image",
		 "insert_after": "rpa_inv_letterhead_header"},
		{"fieldname": "rpa_inv_section_2", "fieldtype": "Section Break", "insert_after": "rpa_inv_letterhead_footer"},
		{"fieldname": "rpa_inv_bank_details", "label": "Bank details", "fieldtype": "Small Text",
		 "insert_after": "rpa_inv_section_2"},
		{"fieldname": "rpa_inv_terms", "label": "Terms and conditions", "fieldtype": "Small Text",
		 "insert_after": "rpa_inv_bank_details"},
		{"fieldname": "rpa_inv_col_2", "fieldtype": "Column Break", "insert_after": "rpa_inv_terms"},
		{"fieldname": "rpa_inv_header_note", "label": "Note above items", "fieldtype": "Small Text",
		 "insert_after": "rpa_inv_col_2"},
		{"fieldname": "rpa_inv_footer_note", "label": "Footer note", "fieldtype": "Small Text",
		 "insert_after": "rpa_inv_header_note"},
	]}, update=True)


# ------------------------------------------------------------------ numbering

def numbering():
	for dt in SERIES:
		if not frappe.db.exists("DocType", dt):
			continue
		field = frappe.get_meta(dt).get_field("naming_series")
		if not field:
			continue
		ours = series_options(dt)
		existing = [o for o in (field.options or "").split("\n") if o.strip() and o not in ours]
		make_property_setter(dt, "naming_series", "options", "\n".join(ours + existing), "Text",
		                     validate_fields_for_doctype=False)
		make_property_setter(dt, "naming_series", "default", ours[0], "Text", validate_fields_for_doctype=False)


# ------------------------------------------------------------------ print formats

def print_formats():
	for name, key in INVOICE_FORMATS.items():
		_print_format(name, "Sales Invoice", f"{{{{ rpa_invoice(doc, '{key}') }}}}", thermal=key == "thermal")
	for dt, name in MY_STYLE.items():
		_print_format(name, dt, "{{ rpa_invoice(doc) }}")
		make_property_setter(dt, None, "default_print_format", name, "Data", for_doctype=True,
		                     validate_fields_for_doctype=False)
	settings = frappe.get_single("Print Settings")
	settings.allow_print_for_draft = 1
	settings.add_draft_heading = 1
	settings.send_print_as_pdf = 1
	settings.flags.ignore_permissions = True
	settings.save()


def _print_format(name, doctype, html, thermal=False):
	values = {
		"doc_type": doctype, "module": "RPA Integration", "standard": "No", "custom_format": 1,
		"print_format_type": "Jinja", "html": html, "disabled": 0,
		"margin_top": 3 if thermal else 10, "margin_bottom": 3 if thermal else 10,
		"margin_left": 3 if thermal else 10, "margin_right": 3 if thermal else 10,
	}
	if frappe.get_meta("Print Format").has_field("paper_size"):
		values["paper_size"] = "Receipt 80 mm" if thermal else "A4"
	if frappe.db.exists("Print Format", name):
		doc = frappe.get_doc("Print Format", name)
		doc.update(values)
		doc.flags.ignore_permissions = True
		doc.save()
	else:
		doc = frappe.get_doc({"doctype": "Print Format", "name": name, **values})
		doc.flags.ignore_permissions = True
		doc.insert(set_name=name)


# ------------------------------------------------------------------ desk clean-up

def desk():
	if frappe.get_meta("System Settings").has_field("enable_onboarding"):
		frappe.db.set_single_value("System Settings", "enable_onboarding", 0)

	nav = frappe.get_single("Navbar Settings")
	for row in nav.get("help_dropdown") or []:
		if row.is_standard:
			row.hidden = 1
	_nav_item(nav, "help_dropdown", "Message your CA", f"{PORTAL}/messages")
	_nav_item(nav, "help_dropdown", "Client portal", f"{PORTAL}/dashboard")
	_nav_item(nav, "settings_dropdown", "Back to client portal", f"{PORTAL}/books", first=True)
	logo = _logo_url(WORDMARK_FILE)
	if logo:
		nav.app_logo = logo
	nav.flags.ignore_permissions = True
	nav.save()


def _nav_item(nav, table, label, url, first=False):
	rows = nav.get(table) or []
	if any(r.item_label == label for r in rows):
		return
	nav.append(table, {"item_label": label, "item_type": "Route", "route": url, "is_standard": 0, "hidden": 0})
	if first:
		rows = nav.get(table)
		rows.insert(0, rows.pop())
		for i, r in enumerate(rows, start=1):
			r.idx = i


def _logo_url(file_name=LOGO_FILE):
	"""Upload one of our brand images once as a public file and return its URL."""
	for old in OLD_LOGO_FILES:
		for name in frappe.get_all("File", filters={"file_name": old}, pluck="name"):
			frappe.delete_doc("File", name, ignore_permissions=True, force=True)
	existing = frappe.db.get_value("File", {"file_name": file_name, "is_private": 0}, "file_url")
	if existing:
		return existing
	path = os.path.join(os.path.dirname(__file__), "public", "images", file_name)
	if not os.path.exists(path):
		return None
	with open(path, "rb") as fh:
		f = frappe.get_doc({"doctype": "File", "file_name": file_name, "is_private": 0, "content": fh.read()})
		f.flags.ignore_permissions = True
		f.insert()
	return f.file_url


# ------------------------------------------------------------------ per-company defaults

def company_defaults(company):
	"""In-state GST templates as defaults; India Compliance switches to out-state by place of supply."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	for dt, prefix in (("Sales Taxes and Charges Template", "Output GST In-state"),
	                   ("Purchase Taxes and Charges Template", "Input GST In-state")):
		name = f"{prefix} - {abbr}"
		if not frappe.db.exists(dt, name):
			continue
		if not frappe.db.exists(dt, {"company": company, "is_default": 1}):
			frappe.db.set_value(dt, name, "is_default", 1)


def ensure_company_address(company, address_line1, city, state, pincode, gstin=None, phone=None, email=None):
	"""The company's own billing address: India Compliance needs it for GSTIN and place of supply."""
	if not (address_line1 and city and state):
		return None
	existing = frappe.db.sql("""select a.name from `tabAddress` a join `tabDynamic Link` l on l.parent = a.name
		where l.link_doctype = 'Company' and l.link_name = %s and a.is_your_company_address = 1 limit 1""", company)
	if existing:
		return existing[0][0]
	doc = frappe.get_doc({
		"doctype": "Address", "address_title": company, "address_type": "Billing",
		"address_line1": address_line1, "city": city, "state": state, "pincode": pincode,
		"country": "India", "is_your_company_address": 1, "is_primary_address": 1,
		"phone": phone, "email_id": email,
		"links": [{"link_doctype": "Company", "link_name": company}],
	})
	if doc.meta.has_field("rpa_company"):
		doc.rpa_company = company
	if gstin and doc.meta.has_field("gstin"):
		doc.gstin = gstin
		if doc.meta.has_field("gst_category"):
			doc.gst_category = "Registered Regular"
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name
