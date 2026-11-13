import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

from rpa_integration.features import PROVISIONER_ROLE, READ_ONLY_ROLE

# The invoicing-only role: create and send invoices, quotations and receipts, nothing else.
INVOICING_FULL = ["Sales Invoice", "Quotation", "Payment Entry", "Customer", "Item", "Item Price", "Address", "Contact"]
INVOICING_READ = [
	"Account", "Cost Center", "Mode of Payment", "Sales Taxes and Charges Template", "Item Tax Template",
	"Price List", "Currency", "UOM", "Item Group", "Customer Group", "Territory", "Company", "Fiscal Year",
	"Terms and Conditions", "Letter Head", "Print Heading", "Warehouse", "Payment Terms Template",
	"Bank Account", "GST HSN Code", "Brand",
]
FULL_PTYPES = ["read", "write", "create", "submit", "cancel", "amend", "print", "email", "report", "export"]
MASTER_PTYPES = ["read", "write", "create", "print", "email", "report", "export"]
SUBMITTABLE = {"Sales Invoice", "Quotation", "Payment Entry"}

# What a lapsed client can still open: their records, read-only.
READ_ONLY_DOCTYPES = [
	"Sales Invoice", "Purchase Invoice", "Quotation", "Sales Order", "Purchase Order", "Delivery Note",
	"Purchase Receipt", "Payment Entry", "Journal Entry", "GL Entry", "Customer", "Supplier", "Item",
	"Account", "Cost Center", "Company", "Fiscal Year", "Bank Account", "Bank Transaction", "Stock Entry",
	"Stock Ledger Entry", "Warehouse", "Employee", "Salary Slip", "Project", "Timesheet", "Address", "Contact",
]


def after_install():
	ensure_setup()


def after_migrate():
	ensure_setup()


def ensure_setup():
	for role in ("RPA Invoicing", READ_ONLY_ROLE, PROVISIONER_ROLE):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

	_grant("RPA Invoicing", INVOICING_FULL, None)
	_grant("RPA Invoicing", INVOICING_READ, ["read", "report"])
	_grant(READ_ONLY_ROLE, READ_ONLY_DOCTYPES, ["read", "print", "report", "export"])
	# Purchase plan: clients see and print their purchase bills and supplier payments.
	_grant("Purchase User", ["Purchase Invoice", "Payment Entry"], ["read", "print", "report"])
	_grant("Stock User", ["Stock Entry", "Bin"], ["read", "print", "report"])
	_grant("Stock User", ["Stock Reconciliation"], ["read", "write", "create", "submit", "print", "report"])

	create_custom_fields({
		"Company": [
			{"fieldname": "rpa_section", "label": "Client portal", "fieldtype": "Section Break",
			 "insert_after": "default_holiday_list", "collapsible": 1},
			{"fieldname": "rpa_status", "label": "Portal status", "fieldtype": "Select",
			 "options": "\nActive\nRead only\nClosed", "read_only": 1, "insert_after": "rpa_section"},
			{"fieldname": "rpa_enabled_features", "label": "Features switched on", "fieldtype": "Small Text",
			 "read_only": 1, "insert_after": "rpa_status"},
			{"fieldname": "rpa_portal_user", "label": "Portal client user", "fieldtype": "Data",
			 "options": "Email", "read_only": 1, "insert_after": "rpa_enabled_features"},
		]
	}, update=True)
	for doctype in ("System Settings", "Website Settings"):
		if frappe.get_meta(doctype).has_field("app_name"):
			frappe.db.set_single_value(doctype, "app_name", "Books by Ronak Patel & Associates")

	from rpa_integration import phase1
	phase1.ensure()
	frappe.db.commit()


def _grant(role, doctypes, ptypes):
	for dt in doctypes:
		if not frappe.db.exists("DocType", dt):
			continue
		if ptypes is None:
			wanted = list(FULL_PTYPES if dt in SUBMITTABLE else MASTER_PTYPES)
		else:
			wanted = list(ptypes)
		if not frappe.db.exists("Custom DocPerm", {"parent": dt, "role": role, "permlevel": 0}):
			add_permission(dt, role, 0)
		for ptype in wanted:
			update_permission_property(dt, role, 0, ptype, 1, validate=False)
