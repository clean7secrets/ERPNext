"""Simple Books API used by the "My Business" home screen.

Everything runs as the signed-in client with their normal permissions, so company isolation
(User Permission on Company + rpa_company on masters) always applies.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_first_day, getdate, nowdate, nowtime

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
	if "purchase" in features:
		numbers["to_pay"] = q("""select sum(outstanding_amount) from `tabPurchase Invoice` where company=%s
			and docstatus=1 and outstanding_amount > 0""", company)
	if "inventory" in features:
		numbers["stock_value"] = q("""select sum(b.stock_value) from `tabBin` b join `tabWarehouse` w on w.name=b.warehouse
			where w.company=%s""", company)
	bills = frappe.get_all("Purchase Invoice", filters={"company": company},
	                        fields=["name", "supplier_name", "bill_no", "posting_date", "grand_total", "outstanding_amount",
	                                "status", "docstatus"], order_by="creation desc", limit_page_length=6) \
		if "purchase" in features else []
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
	return {"uploads": uploads, "bills": bills, "lang": user.language or "en",
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
	                      "stock_uom": unit or "Nos",
	                      "is_stock_item": 1 if ("inventory" in _features(company) and not cint(is_service)) else 0,
	                      "include_item_in_manufacturing": 0,
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

def _lines(items, own=None):
	items = json.loads(items) if isinstance(items, str) else items
	rows = []
	for it in items or []:
		if not it.get("item_code") or flt(it.get("qty")) <= 0:
			continue
		if own and frappe.db.get_value("Item", it["item_code"], "rpa_company") != own:
			frappe.throw(_("Please pick one of your products"), frappe.PermissionError)
		rows.append({"item_code": it["item_code"], "qty": flt(it["qty"]), "rate": flt(it.get("rate")),
		             "discount_percentage": flt(it.get("discount"))})
	if not rows:
		frappe.throw(_("Add at least one product or service"))
	return rows


@frappe.whitelist()
def create_invoice(customer, items, posting_date=None, due_days=15, notes=None, finalise=1):
	company = client_company()
	posting_date = posting_date or nowdate()
	lines = _lines(items)
	stock = "inventory" in _features(company) and any(
		frappe.db.get_value("Item", r["item_code"], "is_stock_item") for r in lines)
	doc = frappe.get_doc({"doctype": "Sales Invoice", "company": company, "customer": customer,
	                      "posting_date": posting_date, "set_posting_time": 1, "posting_time": nowtime(),
	                      "due_date": add_days(posting_date, cint(due_days)), "items": lines,
	                      "terms": notes or None, "update_stock": 1 if stock else 0})
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


# ------------------------------------------------------------------ purchase (feature "purchase")

def _as_client_doc(doc, company):
	"""Insert on the client's behalf: the company is always theirs, checked above."""
	doc.company = company
	doc.flags.ignore_permissions = True
	return doc


@frappe.whitelist()
def create_supplier(supplier_name, gstin=None, phone=None, email=None, address_line1=None, city=None,
                    state=None, pincode=None):
	company = client_company()
	if not set(_features(company)) & {"purchase", "accounting"}:
		frappe.throw(_("Suppliers come with the Purchase plan."), frappe.PermissionError)
	supplier_name = (supplier_name or "").strip()
	if len(supplier_name) < 2:
		frappe.throw(_("Please enter the supplier's name"))
	gstin = (gstin or "").strip().upper() or None
	doc = frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier_name, "rpa_company": company,
	                      "supplier_type": "Company" if gstin else "Individual",
	                      "supplier_group": _leaf("Supplier Group", prefer="Local"),
	                      "mobile_no": phone, "email_id": email,
	                      "gstin": gstin, "gst_category": "Registered Regular" if gstin else "Unregistered"})
	doc.flags.ignore_permissions = True
	doc.insert()
	if address_line1 and city and state:
		frappe.get_doc({"doctype": "Address", "address_title": supplier_name, "address_type": "Billing",
		                "address_line1": address_line1, "city": city, "state": state, "pincode": pincode,
		                "country": "India", "gstin": gstin, "gst_category": doc.gst_category,
		                "is_primary_address": 1, "rpa_company": company,
		                "links": [{"link_doctype": "Supplier", "link_name": doc.name}]}).insert(ignore_permissions=True)
	return {"name": doc.name, "supplier_name": doc.supplier_name}


@frappe.whitelist()
def create_purchase_bill(supplier, items, bill_no=None, bill_date=None, due_days=30, upload=None, update_stock=0):
	company = client_company()
	_require(company, "purchase")
	if frappe.db.get_value("Supplier", supplier, "rpa_company") != company:
		frappe.throw(_("Please pick one of your suppliers"), frappe.PermissionError)
	bill_date = bill_date or nowdate()
	doc = frappe.get_doc({"doctype": "Purchase Invoice", "supplier": supplier, "bill_no": (bill_no or "").strip() or None,
	                      "bill_date": bill_date, "posting_date": nowdate(), "set_posting_time": 1, "posting_time": nowtime(),
	                      "due_date": add_days(bill_date, cint(due_days)), "items": _lines(items, own=company),
	                      "update_stock": 1 if cint(update_stock) and "inventory" in _features(company) else 0})
	_as_client_doc(doc, company)
	# GST (input credit) only on bills from GST-registered suppliers; India Compliance refuses it otherwise.
	registered = bool(frappe.db.get_value("Supplier", supplier, "gstin"))
	default_tax = frappe.db.get_value("Purchase Taxes and Charges Template", {"company": company, "is_default": 1}, "name")
	if registered and default_tax:
		doc.taxes_and_charges = default_tax
	doc.set_missing_values()
	if not registered:
		doc.taxes_and_charges = None
		doc.set("taxes", [])
		for it in doc.items:
			it.item_tax_template = None
			it.item_tax_rate = "{}"
	elif default_tax and not doc.get("taxes"):
		doc.set_taxes() if hasattr(doc, "set_taxes") else None
	doc.insert()
	doc.submit()
	if upload:
		up = frappe.get_doc("RPA Bill Upload", upload)
		if up.company == company and up.status == "New":
			frappe.db.set_value("RPA Bill Upload", up.name, {"status": "Entered", "entered_as_doctype": "Purchase Invoice",
			                                                 "entered_as": doc.name})
			frappe.get_doc({"doctype": "File", "file_url": up.bill_file, "attached_to_doctype": "Purchase Invoice",
			                "attached_to_name": doc.name, "is_private": 1}).insert(ignore_permissions=True)
	return {"name": doc.name, "grand_total": doc.grand_total}


@frappe.whitelist()
def pay_supplier(bill, amount=None, mode="Bank transfer", payment_date=None, reference=None):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	company = client_company()
	_require(company, "purchase")
	pi = frappe.get_doc("Purchase Invoice", bill)
	if pi.company != company:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	amount = flt(amount) or flt(pi.outstanding_amount)
	if amount <= 0 or amount > flt(pi.outstanding_amount) + 0.01:
		frappe.throw(_("Amount must be between 1 and the amount due ({0})").format(pi.outstanding_amount))
	pe = get_payment_entry("Purchase Invoice", bill)
	pe.posting_date = payment_date or nowdate()
	field = "default_cash_account" if mode == "Cash" else "default_bank_account"
	paid_from = frappe.get_cached_value("Company", company, field)
	if paid_from:
		pe.paid_from = paid_from
	if mode != "Cash":
		pe.reference_no = reference or mode
		pe.reference_date = pe.posting_date
	pe.paid_amount = pe.received_amount = amount
	for ref in pe.references:
		ref.allocated_amount = amount
	_as_client_doc(pe, company)
	pe.insert()
	pe.submit()
	return {"name": pe.name, "amount": amount}


# ------------------------------------------------------------------ stock (feature "inventory")

def _store(company):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"Stores - {abbr}"
	if frappe.db.exists("Warehouse", name):
		return name
	return frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")


@frappe.whitelist()
def stock_move(item_code, qty, direction="in", rate=None, move_date=None, note=None):
	company = client_company()
	_require(company, "inventory")
	if frappe.db.get_value("Item", item_code, "rpa_company") != company:
		frappe.throw(_("Please pick one of your products"), frappe.PermissionError)
	if not frappe.db.get_value("Item", item_code, "is_stock_item"):
		frappe.db.set_value("Item", item_code, "is_stock_item", 1)
	qty = flt(qty)
	if qty <= 0:
		frappe.throw(_("Please enter the quantity"))
	store = _store(company)
	uom = frappe.db.get_value("Item", item_code, "stock_uom")
	row = {"item_code": item_code, "qty": qty, "uom": uom, "stock_uom": uom, "conversion_factor": 1, "transfer_qty": qty}
	if direction == "in":
		purpose, row["t_warehouse"] = "Material Receipt", store
		if flt(rate):
			row["basic_rate"] = flt(rate)
	else:
		purpose, row["s_warehouse"] = "Material Issue", store
	se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": purpose, "purpose": purpose,
	                     "posting_date": move_date or nowdate(), "set_posting_time": 1, "posting_time": nowtime(), "remarks": note,
	                     "items": [row]})
	_as_client_doc(se, company)
	se.set_missing_values() if hasattr(se, "set_missing_values") else None
	se.insert()
	se.submit()
	return {"name": se.name, "in_hand": _in_hand(item_code, store)}


@frappe.whitelist()
def stock_count(item_code, counted_qty, rate=None, count_date=None):
	company = client_company()
	_require(company, "inventory")
	if frappe.db.get_value("Item", item_code, "rpa_company") != company:
		frappe.throw(_("Please pick one of your products"), frappe.PermissionError)
	if not frappe.db.get_value("Item", item_code, "is_stock_item"):
		frappe.db.set_value("Item", item_code, "is_stock_item", 1)
	store = _store(company)
	valuation = flt(rate) or flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": store}, "valuation_rate")) \
		or flt(frappe.db.get_value("Item", item_code, "valuation_rate")) or flt(frappe.db.get_value("Item", item_code, "standard_rate")) or 1
	sr = frappe.get_doc({"doctype": "Stock Reconciliation", "purpose": "Stock Reconciliation",
	                     "posting_date": count_date or nowdate(), "set_posting_time": 1, "posting_time": nowtime(),
	                     "items": [{"item_code": item_code, "warehouse": store, "qty": flt(counted_qty),
	                                "valuation_rate": valuation}]})
	_as_client_doc(sr, company)
	sr.insert()
	sr.submit()
	return {"name": sr.name, "in_hand": _in_hand(item_code, store)}


def _in_hand(item_code, store):
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": store}, "actual_qty"))


@frappe.whitelist()
def stock_list():
	company = client_company()
	_require(company, "inventory")
	store = _store(company)
	return frappe.db.sql("""select i.name as item_code, i.item_name, i.stock_uom as unit,
		coalesce(b.actual_qty, 0) as in_hand, coalesce(b.stock_value, 0) as value
		from `tabItem` i left join `tabBin` b on b.item_code = i.name and b.warehouse = %s
		where i.rpa_company = %s and i.is_stock_item = 1 and i.disabled = 0
		order by i.item_name limit 200""", (store, company), as_dict=True)


# ------------------------------------------------------------------ CA team review

@frappe.whitelist()
def team_overview():
	"""One row per client company the team member may see (their User Permissions, or all for admins)."""
	if is_client():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	user = frappe.session.user
	allowed = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")
	filters = {"rpa_portal_user": ["is", "set"]}
	if allowed:
		filters["name"] = ["in", allowed]
	elif "System Manager" not in frappe.get_roles(user):
		return []
	out = []
	for c in frappe.get_all("Company", filters=filters, fields=["name", "rpa_enabled_features"], order_by="name"):
		n = lambda sql: (frappe.db.sql(sql, c.name) or [[0]])[0][0] or 0
		last = frappe.db.sql("""select max(creation) from (
			select creation from `tabSales Invoice` where company=%(c)s union all
			select creation from `tabPurchase Invoice` where company=%(c)s union all
			select creation from `tabJournal Entry` where company=%(c)s union all
			select creation from `tabPayment Entry` where company=%(c)s) t""", {"c": c.name})
		out.append({
			"company": c.name, "features": json.loads(c.rpa_enabled_features or "[]"),
			"uploads_new": n("select count(*) from `tabRPA Bill Upload` where company=%s and status='New'"),
			"drafts": n("select count(*) from `tabSales Invoice` where company=%s and docstatus=0"),
			"overdue": n("select count(*) from `tabSales Invoice` where company=%s and docstatus=1 and outstanding_amount>0 and due_date<curdate()"),
			"to_collect": flt(n("select sum(outstanding_amount) from `tabSales Invoice` where company=%s and docstatus=1")),
			"to_pay": flt(n("select sum(outstanding_amount) from `tabPurchase Invoice` where company=%s and docstatus=1")),
			"last_entry": last[0][0] if last and last[0][0] else None,
		})
	return out
