"""Simple Books API used by the "My Business" home screen.

Everything runs as the signed-in client with their normal permissions, so company isolation
(User Permission on Company + rpa_company on masters) always applies.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_first_day, getdate, nowdate

from rpa_integration.printing import LAYOUTS

STYLE_FIELDS = {
	"rpa_inv_layout": "select", "rpa_inv_colour": "colour", "rpa_inv_font": "select",
	"rpa_inv_second_language": "select", "rpa_inv_show_hsn": "check", "rpa_inv_show_discount": "check",
	"rpa_inv_show_uom": "check", "rpa_inv_upi_id": "text", "rpa_inv_logo": "file", "rpa_inv_signature": "file",
	"rpa_inv_letterhead_header": "file", "rpa_inv_letterhead_footer": "file", "rpa_inv_bank_details": "text",
	"rpa_inv_terms": "text", "rpa_inv_header_note": "text", "rpa_inv_footer_note": "text",
}


# ------------------------------------------------------------------ who / which company

def client_company(user=None):
	"""The client's own company (their default User Permission on Company)."""
	user = user or frappe.session.user
	rows = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"},
	                      fields=["for_value", "is_default"], order_by="is_default desc")
	if not rows:
		frappe.throw(_("Your books are not set up yet. Please contact your CA."), frappe.PermissionError)
	return rows[0].for_value


def is_client(user=None):
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):
		return False
	return bool(frappe.db.get_value("Company", {"rpa_portal_user": user}, "name"))


def _features(company):
	return json.loads(frappe.db.get_value("Company", company, "rpa_enabled_features") or "[]")


def _require(company, feature):
	if feature not in _features(company):
		frappe.throw(_("This needs the {0} plan. You can add it from Online Books on the portal.").format(feature),
		             frappe.PermissionError)


# ------------------------------------------------------------------ home screen

@frappe.whitelist()
def dashboard():
	company = client_company()
	features = _features(company)
	month_start, today = get_first_day(nowdate()), nowdate()
	q = lambda sql, *a: flt((frappe.db.sql(sql, a) or [[0]])[0][0])
	numbers = {
		"sales_month": q("""select sum(base_grand_total) from `tabSales Invoice` where company=%s and docstatus=1
			and is_return=0 and posting_date between %s and %s""", company, month_start, today),
		"to_collect": q("""select sum(outstanding_amount) from `tabSales Invoice` where company=%s and docstatus=1
			and outstanding_amount > 0""", company),
		"received_month": q("""select sum(base_paid_amount) from `tabPayment Entry` where company=%s and docstatus=1
			and payment_type='Receive' and posting_date between %s and %s""", company, month_start, today),
		"overdue": q("""select count(*) from `tabSales Invoice` where company=%s and docstatus=1
			and outstanding_amount > 0 and due_date < %s""", company, today),
	}
	if "accounting" in features:
		numbers["expenses_month"] = q("""select sum(gle.debit - gle.credit) from `tabGL Entry` gle
			join `tabAccount` acc on acc.name = gle.account
			where gle.company=%s and gle.is_cancelled=0 and acc.root_type='Expense'
			and gle.posting_date between %s and %s""", company, month_start, today)
	recent = frappe.get_list("Sales Invoice", filters={"company": company},
	                         fields=["name", "customer_name", "posting_date", "grand_total", "outstanding_amount",
	                                 "status", "docstatus", "is_return"],
	                         order_by="creation desc", limit_page_length=12)
	quotes = frappe.get_list("Quotation", filters={"company": company},
	                         fields=["name", "customer_name", "transaction_date", "grand_total", "status", "docstatus"],
	                         order_by="creation desc", limit_page_length=5)
	uploads = frappe.get_list("RPA Bill Upload", filters={"company": company},
	                          fields=["name", "supplier_name", "amount", "status", "bill_date", "bill_file", "creation"],
	                          order_by="creation desc", limit_page_length=6) \
		if set(features) & {"accounting", "purchase"} else []
	user = frappe.get_cached_doc("User", frappe.session.user)
	return {"uploads": uploads, "lang": user.language or "en",
		"company": company, "features": features, "numbers": numbers, "recent": recent, "quotes": quotes,
		"first_name": user.first_name, "has_address": bool(_company_address(company)),
		"customers": frappe.db.count("Customer", {"rpa_company": company}),
		"products": frappe.db.count("Item", {"rpa_company": company}),
	}


def _company_address(company):
	rows = frappe.db.sql("""select a.name from `tabAddress` a join `tabDynamic Link` l on l.parent=a.name
		where l.link_doctype='Company' and l.link_name=%s and a.is_your_company_address=1 limit 1""", company)
	return rows[0][0] if rows else None


@frappe.whitelist()
def options():
	"""Lists for the simple forms: GST rates, states, expense categories, payment modes."""
	company = client_company()
	abbr = frappe.get_cached_value("Company", company, "abbr")
	rates = []
	for r in (0, 5, 12, 18, 28):
		if r == 0 or frappe.db.exists("Item Tax Template", f"GST {r}% - {abbr}"):
			rates.append(r)
	states = frappe.get_meta("Address").get_field("state")
	out = {"gst_rates": rates or [0, 5, 12, 18, 28], "uoms": ["Nos", "Kg", "Litre", "Meter", "Box", "Hour", "Day"],
	       "states": [s for s in (states.options or "").split("\n") if s] if states and states.fieldtype == "Select" else []}
	if "accounting" in _features(company):
		out["expense_accounts"] = frappe.get_all("Account", filters={"company": company, "root_type": "Expense",
		                                         "is_group": 0, "disabled": 0}, pluck="name", order_by="account_name")
	return out


# ------------------------------------------------------------------ customers and products

@frappe.whitelist()
def create_customer(customer_name, gstin=None, phone=None, email=None, address_line1=None, city=None,
                    state=None, pincode=None):
	company = client_company()
	customer_name = (customer_name or "").strip()
	if len(customer_name) < 2:
		frappe.throw(_("Please enter the customer's name"))
	gstin = (gstin or "").strip().upper() or None
	doc = frappe.get_doc({"doctype": "Customer", "customer_name": customer_name, "rpa_company": company,
	                      "customer_type": "Company" if gstin else "Individual",
	                      "customer_group": _leaf("Customer Group", prefer="Commercial" if gstin else "Individual"),
	                      "territory": _leaf("Territory", prefer="India"),
	                      "mobile_no": phone, "email_id": email})
	if gstin:
		doc.gstin = gstin
		doc.gst_category = "Registered Regular"
	else:
		doc.gst_category = "Unregistered"
	doc.insert()
	if address_line1 and city and state:
		frappe.get_doc({"doctype": "Address", "address_title": customer_name, "address_type": "Billing",
		                "address_line1": address_line1, "city": city, "state": state, "pincode": pincode,
		                "country": "India", "gstin": gstin, "gst_category": doc.gst_category,
		                "is_primary_address": 1, "rpa_company": company, "phone": phone, "email_id": email,
		                "links": [{"link_doctype": "Customer", "link_name": doc.name}]}).insert()
	return {"name": doc.name, "customer_name": doc.customer_name}


@frappe.whitelist()
def create_product(item_name, rate=0, hsn=None, gst_rate=18, unit="Nos", is_service=0):
	company = client_company()
	abbr = frappe.get_cached_value("Company", company, "abbr")
	item_name = (item_name or "").strip()
	if len(item_name) < 2:
		frappe.throw(_("Please enter the product or service name"))
	if unit and not frappe.db.exists("UOM", unit):
		unit = "Nos"
	base = f"{abbr}-" + (re.sub(r"[^A-Z0-9]+", "-", item_name.upper()).strip("-")[:24] or "ITEM")
	code, n = base, 1
	while frappe.db.exists("Item", code):
		n += 1
		code = f"{base}-{n}"
	doc = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": item_name, "description": item_name,
	                      "item_group": _leaf("Item Group", prefer="Services" if cint(is_service) else "Products"),
	                      "stock_uom": unit or "Nos", "is_stock_item": 0, "include_item_in_manufacturing": 0,
	                      "gst_hsn_code": (hsn or "").strip() or None, "rpa_company": company,
	                      "standard_rate": flt(rate)})
	template = f"GST {cint(gst_rate)}% - {abbr}"
	if cint(gst_rate) and frappe.db.exists("Item Tax Template", template):
		doc.append("taxes", {"item_tax_template": template})
	doc.insert()
	return {"name": doc.name, "item_name": doc.item_name, "rate": flt(rate)}


def _leaf(doctype, prefer=None):
	if prefer and frappe.db.exists(doctype, {"name": prefer, "is_group": 0}):
		return prefer
	return frappe.db.get_value(doctype, {"is_group": 0}, "name") or frappe.db.get_value(doctype, {}, "name")


# ------------------------------------------------------------------ invoices, quotes, payments

def _lines(items):
	items = json.loads(items) if isinstance(items, str) else items
	rows = []
	for it in items or []:
		if not it.get("item_code") or flt(it.get("qty")) <= 0:
			continue
		rows.append({"item_code": it["item_code"], "qty": flt(it["qty"]), "rate": flt(it.get("rate")),
		             "discount_percentage": flt(it.get("discount"))})
	if not rows:
		frappe.throw(_("Add at least one product or service"))
	return rows


@frappe.whitelist()
def create_invoice(customer, items, posting_date=None, due_days=15, notes=None, finalise=1):
	company = client_company()
	posting_date = posting_date or nowdate()
	doc = frappe.get_doc({"doctype": "Sales Invoice", "company": company, "customer": customer,
	                      "posting_date": posting_date, "set_posting_time": 1,
	                      "due_date": add_days(posting_date, cint(due_days)), "items": _lines(items),
	                      "terms": notes or None})
	doc.set_missing_values()
	doc.insert()
	if cint(finalise):
		doc.submit()
	return {"name": doc.name, "grand_total": doc.grand_total, "docstatus": doc.docstatus}


@frappe.whitelist()
def create_quote(customer, items, transaction_date=None, valid_days=30, notes=None):
	company = client_company()
	transaction_date = transaction_date or nowdate()
	doc = frappe.get_doc({"doctype": "Quotation", "company": company, "quotation_to": "Customer",
	                      "party_name": customer, "transaction_date": transaction_date,
	                      "valid_till": add_days(transaction_date, cint(valid_days)), "items": _lines(items),
	                      "terms": notes or None})
	doc.run_method("set_missing_values")
	doc.insert()
	doc.submit()
	return {"name": doc.name, "grand_total": doc.grand_total}


@frappe.whitelist()
def receive_money(invoice, amount=None, mode="Cash", payment_date=None, reference=None):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	company = client_company()
	si = frappe.get_doc("Sales Invoice", invoice)
	if si.company != company:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	pe = get_payment_entry("Sales Invoice", invoice)
	amount = flt(amount) or flt(si.outstanding_amount)
	if amount <= 0 or amount > flt(si.outstanding_amount) + 0.01:
		frappe.throw(_("Amount must be between 1 and the amount due ({0})").format(si.outstanding_amount))
	pe.posting_date = payment_date or nowdate()
	if mode != "Cash":
		bank = frappe.get_cached_value("Company", company, "default_bank_account")
		if bank:
			pe.paid_to = bank
		pe.mode_of_payment = "Wire Transfer" if frappe.db.exists("Mode of Payment", "Wire Transfer") else None
		pe.reference_no = reference or mode
		pe.reference_date = pe.posting_date
	else:
		pe.mode_of_payment = "Cash" if frappe.db.exists("Mode of Payment", "Cash") else None
	pe.paid_amount = pe.received_amount = amount
	for ref in pe.references:
		ref.allocated_amount = amount
	pe.insert()
	pe.submit()
	return {"name": pe.name, "amount": amount}


@frappe.whitelist()
def record_expense(category, amount, paid_from="Cash", expense_date=None, note=None):
	company = client_company()
	_require(company, "accounting")
	return _expense_entry(company, category, amount, paid_from, expense_date, note)


def _expense_entry(company, category, amount, paid_from="Cash", expense_date=None, note=None, ignore_permissions=False):
	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Please enter the amount"))
	acc = frappe.db.get_value("Account", {"name": category, "company": company, "root_type": "Expense", "is_group": 0})
	if not acc:
		frappe.throw(_("Please pick a category"))
	field = "default_cash_account" if paid_from == "Cash" else "default_bank_account"
	paid = frappe.get_cached_value("Company", company, field)
	if not paid:
		frappe.throw(_("No {0} account is set up yet. Please ask your CA.").format(paid_from.lower()))
	je = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": company,
	                     "posting_date": expense_date or nowdate(), "user_remark": note or f"Expense: {category}",
	                     "accounts": [
		                     {"account": acc, "debit_in_account_currency": amount,
		                      "cost_center": frappe.get_cached_value("Company", company, "cost_center")},
		                     {"account": paid, "credit_in_account_currency": amount},
	                     ]})
	je.flags.ignore_permissions = ignore_permissions
	je.insert()
	je.submit()
	return {"name": je.name, "amount": amount}


# ------------------------------------------------------------------ bill uploads ("Snap a bill")

@frappe.whitelist()
def upload_bill(file_url, bill_date=None, supplier_name=None, amount=None, paid_from=None, note=None):
	company = client_company()
	if not set(_features(company)) & {"accounting", "purchase"}:
		frappe.throw(_("Bill uploads come with the Accounting or Purchase plan."), frappe.PermissionError)
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(_("Please attach the bill again"))
	doc = frappe.get_doc({"doctype": "RPA Bill Upload", "company": company, "bill_file": file_url,
	                      "bill_date": bill_date or None, "supplier_name": (supplier_name or "").strip() or None,
	                      "amount": flt(amount) or None, "paid_from": paid_from or None, "note": note})
	doc.insert()
	frappe.db.set_value("File", file_name, {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
	                                       "is_private": 1})
	return {"name": doc.name}


@frappe.whitelist()
def enter_upload_as_expense(upload, category, amount, paid_from="Bank", expense_date=None):
	doc = frappe.get_doc("RPA Bill Upload", upload)
	if is_client():
		if doc.company != client_company():
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		_require(doc.company, "accounting")
	elif not frappe.has_permission("RPA Bill Upload", "write", doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if doc.status != "New":
		frappe.throw(_("This bill is already entered"))
	note = " · ".join(x for x in (doc.supplier_name, doc.note, f"Bill {doc.name}") if x)
	res = _expense_entry(doc.company, category, amount, paid_from, expense_date or doc.bill_date, note)
	frappe.db.set_value("RPA Bill Upload", doc.name, {"status": "Entered", "entered_as_doctype": "Journal Entry",
	                                                  "entered_as": res["name"]})
	if doc.bill_file:
		frappe.get_doc({"doctype": "File", "file_url": doc.bill_file, "attached_to_doctype": "Journal Entry",
		                "attached_to_name": res["name"], "is_private": 1}).insert(ignore_permissions=True)
	return res


@frappe.whitelist()
def set_language(lang):
	if lang not in ("en", "hi", "mr"):
		frappe.throw(_("Language not available"))
	frappe.db.set_value("User", frappe.session.user, "language", lang)
	frappe.clear_cache(user=frappe.session.user)
	return lang


# ------------------------------------------------------------------ invoice style

@frappe.whitelist()
def get_style():
	company = client_company()
	values = frappe.db.get_value("Company", company, list(STYLE_FIELDS), as_dict=True) or {}
	return {"company": company, "values": values, "layouts": list(LAYOUTS.values())}


@frappe.whitelist()
def save_style(values):
	company = client_company()
	values = json.loads(values) if isinstance(values, str) else values
	clean = {}
	for field, kind in STYLE_FIELDS.items():
		if field not in values:
			continue
		v = values[field]
		if kind == "check":
			v = 1 if cint(v) else 0
		elif kind == "file":
			v = v or None
			if v and not frappe.db.exists("File", {"file_url": v}):
				frappe.throw(_("Please upload the image again"))
		elif kind == "select" and field == "rpa_inv_layout" and v not in LAYOUTS.values():
			continue
		else:
			v = (str(v).strip() if v is not None else None) or None
		clean[field] = v
	frappe.db.set_value("Company", company, clean)  # only the style fields above, never other company data
	frappe.clear_document_cache("Company", company)
	return get_style()


@frappe.whitelist()
def save_address(address_line1, city, state, pincode, phone=None):
	"""The client's own business address (needed on every GST invoice)."""
	from rpa_integration.phase1 import ensure_company_address

	company = client_company()
	gstin = frappe.db.get_value("Company", company, "gstin") if frappe.get_meta("Company").has_field("gstin") else None
	name = ensure_company_address(company, address_line1, city, state, pincode, gstin=gstin, phone=phone)
	return {"address": name}
