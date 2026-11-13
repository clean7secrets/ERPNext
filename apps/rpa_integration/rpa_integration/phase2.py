"""Phase 2: the simple client experience.

- Masters (customers, products, suppliers, addresses, contacts) carry rpa_company, so a client only
  ever sees their own; strict user permissions hide records that belong to no company.
- Customers, suppliers and products get series names, so two clients can both have "Shree Traders".
- Each company has a bank ledger so "Receive money" by UPI or bank works from day one.
- Client users land on the My Business page instead of the full ERPNext desk.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

OWNED_DOCTYPES = ["Customer", "Supplier", "Item", "Item Price", "Address", "Contact"]


def ensure():
	owned_fields()
	frappe.db.set_single_value("System Settings", "apply_strict_user_permissions", 1)
	if frappe.get_meta("Stock Settings").has_field("item_naming_by"):
		frappe.db.set_single_value("Stock Settings", "item_naming_by", "Item Code")
	for doctype, field in (("Selling Settings", "cust_master_name"), ("Buying Settings", "supp_master_name")):
		if frappe.get_meta(doctype).has_field(field):
			frappe.db.set_single_value(doctype, field, "Naming Series")
	for company in frappe.get_all("Company", pluck="name"):
		bank_ledger(company)


def owned_fields():
	fields = {}
	for dt in OWNED_DOCTYPES:
		insert_after = {"Customer": "customer_name", "Supplier": "supplier_name", "Item": "item_name",
		                "Item Price": "item_code", "Address": "address_title", "Contact": "last_name"}[dt]
		fields[dt] = [{"fieldname": "rpa_company", "label": "Client company", "fieldtype": "Link",
		               "options": "Company", "insert_after": insert_after, "read_only": 1, "in_standard_filter": 1,
		               "no_copy": 1}]
	create_custom_fields(fields, update=True)


def set_owner_company(doc, method=None):
	"""before_insert on owned masters: a client's new record belongs to their company."""
	if doc.get("rpa_company") or not doc.meta.has_field("rpa_company"):
		return
	from rpa_integration.books_api import client_company, is_client

	if is_client():
		doc.rpa_company = client_company()


def bank_ledger(company):
	if frappe.get_cached_value("Company", company, "default_bank_account"):
		return
	abbr = frappe.get_cached_value("Company", company, "abbr")
	parent = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name") \
		or frappe.db.get_value("Account", {"company": company, "account_name": "Bank Accounts", "is_group": 1}, "name")
	if not parent:
		return
	name = f"Bank - {abbr}"
	if not frappe.db.exists("Account", name):
		acc = frappe.get_doc({"doctype": "Account", "account_name": "Bank", "parent_account": parent,
		                      "company": company, "account_type": "Bank", "is_group": 0})
		acc.flags.ignore_permissions = True
		acc.insert()
		name = acc.name
	frappe.db.set_value("Company", company, "default_bank_account", name)


# ------------------------------------------------------------------ boot + routing

def boot_session(bootinfo):
	from rpa_integration.books_api import client_company, is_client

	if is_client():
		bootinfo.rpa_client = {"company": client_company()}
