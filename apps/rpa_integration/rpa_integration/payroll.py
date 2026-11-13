"""Simple payroll for Online Books clients (feature "hr_payroll").

One standard monthly structure per company, worked out from the employee's monthly gross:
  Basic = 50% of gross, HRA = 40% of Basic, Special Allowance = the rest.
  PF  (if ticked) = 12% of Basic, Basic capped at 15,000   (employer adds the same)
  ESI (if ticked and gross <= 21,000) = 0.75% of gross      (employer adds 3.25%)
  PT  (if ticked and gross > 10,000) = 200 a month (Maharashtra; February 300 is not handled yet)
The CA team can still change any structure in the full ERPNext screens.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import add_days, cint, flt, get_first_day, get_last_day, getdate, nowdate

COMPONENTS = [
	# name, abbr, type, depends on payment days
	("Basic", "B", "Earning", 1),
	("House Rent Allowance", "HRA", "Earning", 1),
	("Special Allowance", "SA", "Earning", 1),
	("Provident Fund", "PF", "Deduction", 0),
	("ESI", "ESI", "Deduction", 0),
	("Professional Tax", "PT", "Deduction", 0),
]


def ensure_fields():
	create_custom_fields({"Employee": [
		{"fieldname": "rpa_payroll_section", "label": "Statutory deductions", "fieldtype": "Section Break",
		 "insert_after": "date_of_joining", "collapsible": 1},
		{"fieldname": "rpa_pf", "label": "Deduct PF", "fieldtype": "Check", "insert_after": "rpa_payroll_section"},
		{"fieldname": "rpa_esi", "label": "Deduct ESI", "fieldtype": "Check", "insert_after": "rpa_pf"},
		{"fieldname": "rpa_pt", "label": "Deduct Professional Tax", "fieldtype": "Check", "default": "1",
		 "insert_after": "rpa_esi"},
	]}, update=True)
	for name, abbr, kind, dep in COMPONENTS:
		if not frappe.db.exists("Salary Component", name):
			frappe.get_doc({"doctype": "Salary Component", "salary_component": name, "salary_component_abbr": abbr,
			                "type": kind, "depends_on_payment_days": dep}).insert(ignore_permissions=True)
		elif kind == "Deduction":
			frappe.db.set_value("Salary Component", name, "depends_on_payment_days", 0)


def _abbr(company):
	return frappe.get_cached_value("Company", company, "abbr")


def ensure_company(company):
	"""Holiday list (Sundays), payable ledgers and the standard monthly salary structure."""
	ensure_fields()
	abbr = _abbr(company)
	_holiday_list(company, abbr)
	for label in ("PF Payable", "ESI Payable", "Professional Tax Payable"):
		_liability(company, abbr, label)
	name = f"Books Monthly - {abbr}"
	if frappe.db.exists("Salary Structure", name):
		return name
	ss = frappe.get_doc({
		"doctype": "Salary Structure", "name": name, "company": company, "is_active": "Yes", "currency": "INR",
		"payroll_frequency": "Monthly",
		"earnings": [
			{"salary_component": "Basic", "abbr": "B", "amount_based_on_formula": 1, "formula": "base * 0.5", "depends_on_payment_days": 1},
			{"salary_component": "House Rent Allowance", "abbr": "HRA", "amount_based_on_formula": 1, "formula": "base * 0.2", "depends_on_payment_days": 1},
			{"salary_component": "Special Allowance", "abbr": "SA", "amount_based_on_formula": 1, "formula": "base - (base * 0.5) - (base * 0.2)", "depends_on_payment_days": 1},
		],
		"deductions": [
			{"salary_component": "Provident Fund", "abbr": "PF", "condition": "rpa_pf == 1", "amount_based_on_formula": 1,
			 "formula": "round(min(B, 15000) * 0.12)", "depends_on_payment_days": 0},
			{"salary_component": "ESI", "abbr": "ESI", "condition": "rpa_esi == 1 and base <= 21000", "amount_based_on_formula": 1,
			 "formula": "round(base * 0.0075 + 0.49)", "depends_on_payment_days": 0},
			{"salary_component": "Professional Tax", "abbr": "PT", "condition": "rpa_pt == 1 and base > 10000", "amount": 200,
			 "depends_on_payment_days": 0},
		],
	})
	ss.flags.ignore_permissions = True
	ss.insert(set_name=name)
	ss.submit()
	return name


def _holiday_list(company, abbr):
	existing = frappe.db.get_value("Company", company, "default_holiday_list")
	if existing:
		_assign_holidays(company, existing)
		return
	today = getdate(nowdate())
	start = getdate(f"{today.year if today.month >= 4 else today.year - 1}-04-01")
	end = getdate(f"{start.year + 1}-03-31")
	name = f"Books Holidays {start.year}-{str(start.year + 1)[2:]} - {abbr}"
	if not frappe.db.exists("Holiday List", name):
		hl = frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": name, "from_date": start, "to_date": end,
		                     "weekly_off": "Sunday"})
		d = start
		while d <= end:
			if d.weekday() == 6:
				hl.append("holidays", {"holiday_date": d, "description": "Sunday", "weekly_off": 1})
			d = add_days(d, 1)
		hl.flags.ignore_permissions = True
		hl.insert()
	frappe.db.set_value("Company", company, "default_holiday_list", name)
	_assign_holidays(company, name)


def _assign_holidays(company, holiday_list):
	"""HRMS v16 reads holidays from a Holiday List Assignment, not only the company default."""
	if not frappe.db.exists("DocType", "Holiday List Assignment"):
		return
	if frappe.db.exists("Holiday List Assignment", {"applicable_for": "Company", "assigned_to": company,
	                                                "holiday_list": holiday_list, "docstatus": 1}):
		return
	hla = frappe.get_doc({"doctype": "Holiday List Assignment", "applicable_for": "Company", "assigned_to": company,
	                      "holiday_list": holiday_list,
	                      "from_date": frappe.db.get_value("Holiday List", holiday_list, "from_date")})
	hla.flags.ignore_permissions = True
	hla.insert()
	hla.submit()


def _liability(company, abbr, label):
	name = f"{label} - {abbr}"
	if frappe.db.exists("Account", name):
		return name
	parent = frappe.db.get_value("Account", {"company": company, "account_name": "Duties and Taxes", "is_group": 1}, "name") \
		or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1, "parent_account": ["is", "set"]}, "name")
	acc = frappe.get_doc({"doctype": "Account", "account_name": label, "parent_account": parent, "company": company,
	                      "root_type": "Liability", "is_group": 0})
	acc.flags.ignore_permissions = True
	acc.insert()
	return acc.name


# ------------------------------------------------------------------ client API

def _company():
	from rpa_integration.books_api import _require, client_company

	company = client_company()
	_require(company, "hr_payroll")
	return company


@frappe.whitelist()
def employees():
	company = _company()
	rows = frappe.get_all("Employee", filters={"company": company, "status": "Active"},
	                      fields=["name", "employee_name", "designation", "date_of_joining", "rpa_pf", "rpa_esi", "rpa_pt"],
	                      order_by="employee_name")
	for r in rows:
		r.gross = flt(frappe.db.get_value("Salary Structure Assignment", {"employee": r.name, "docstatus": 1},
		                                  "base", order_by="from_date desc"))
	return rows


@frappe.whitelist()
def add_employee(full_name, gender, date_of_birth, date_of_joining, monthly_gross, designation=None, mobile=None,
                 pan=None, pf=0, esi=0, pt=1):
	company = _company()
	structure = ensure_company(company)
	first, _sep, last = (full_name or "").strip().partition(" ")
	if not first:
		frappe.throw(_("Please enter the employee's name"))
	if flt(monthly_gross) <= 0:
		frappe.throw(_("Please enter the monthly salary"))
	if designation and not frappe.db.exists("Designation", designation):
		frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert(ignore_permissions=True)
	emp = frappe.get_doc({"doctype": "Employee", "first_name": first, "last_name": last or None, "gender": gender,
	                      "date_of_birth": date_of_birth, "date_of_joining": date_of_joining, "status": "Active",
	                      "company": company, "designation": designation or None, "cell_number": mobile,
	                      "pan_number": (pan or "").upper() or None,
	                      "rpa_pf": cint(pf), "rpa_esi": cint(esi), "rpa_pt": cint(pt)})
	if not emp.meta.has_field("pan_number"):
		emp.pan_number = None
	emp.flags.ignore_permissions = True
	emp.insert()
	from_date = max(getdate(date_of_joining), getdate(get_first_day(nowdate())))
	ssa = frappe.get_doc({"doctype": "Salary Structure Assignment", "employee": emp.name, "salary_structure": structure,
	                      "company": company, "currency": "INR", "from_date": from_date, "base": flt(monthly_gross)})
	ssa.flags.ignore_permissions = True
	ssa.insert()
	ssa.submit()
	return {"name": emp.name, "employee_name": emp.employee_name}


@frappe.whitelist()
def run_salary(month=None):
	"""Make and finalise salary slips for every active employee for a month (YYYY-MM), then post one entry."""
	company = _company()
	ensure_company(company)
	month = month or nowdate()[:7]
	start = getdate(f"{month}-01")
	end = get_last_day(start)
	slips, problems = [], []
	for emp in frappe.get_all("Employee", filters={"company": company, "status": "Active", "date_of_joining": ["<=", end]},
	                          fields=["name", "employee_name"]):
		existing = frappe.db.get_value("Salary Slip", {"employee": emp.name, "start_date": start, "docstatus": ["<", 2]}, "name")
		if existing:
			slips.append(frappe.get_doc("Salary Slip", existing))
			continue
		frappe.db.savepoint("rpa_slip")
		try:
			ss = frappe.get_doc({"doctype": "Salary Slip", "employee": emp.name, "company": company,
			                     "posting_date": end, "start_date": start, "end_date": end, "payroll_frequency": "Monthly"})
			ss.flags.ignore_permissions = True
			ss.insert()
			ss.submit()
			slips.append(ss)
		except Exception as e:
			frappe.db.rollback(save_point="rpa_slip")
			problems.append(f"{emp.employee_name}: {frappe.utils.strip_html(str(e))}")
	rows, totals = [], {"gross": 0, "pf": 0, "esi": 0, "pt": 0, "net": 0, "er_pf": 0, "er_esi": 0}
	for s in slips:
		ded = {d.salary_component: flt(d.amount) for d in s.deductions}
		basic = sum(flt(e.amount) for e in s.earnings if e.salary_component == "Basic")
		r = {"slip": s.name, "employee": s.employee_name, "days": flt(s.payment_days), "gross": flt(s.gross_pay),
		     "pf": ded.get("Provident Fund", 0), "esi": ded.get("ESI", 0), "pt": ded.get("Professional Tax", 0),
		     "net": flt(s.net_pay)}
		r["er_pf"] = round(min(basic, 15000) * 0.12) if r["pf"] else 0
		r["er_esi"] = round(r["gross"] * 0.0325) if r["esi"] else 0
		rows.append(r)
		for k in totals:
			totals[k] += r[k]
	entry = _post(company, month, totals) if rows else None
	return {"month": month, "rows": rows, "totals": totals, "entry": entry, "problems": problems}


def _post(company, month, t):
	"""One journal entry for the month: salary and employer contributions as expense, dues as payables."""
	abbr = _abbr(company)
	remark = f"Salaries for {month}"
	existing = frappe.db.get_value("Journal Entry", {"company": company, "user_remark": remark, "docstatus": 1}, "name")
	if existing:
		return existing
	salary_acc = f"Salary - {abbr}" if frappe.db.exists("Account", f"Salary - {abbr}") else \
		frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0, "account_name": ["like", "%alar%"]}, "name")
	payable = frappe.get_cached_value("Company", company, "default_payroll_payable_account") or _liability(company, abbr, "Payroll Payable")
	cc = frappe.get_cached_value("Company", company, "cost_center")
	lines = [{"account": salary_acc, "debit_in_account_currency": t["gross"] + t["er_pf"] + t["er_esi"], "cost_center": cc},
	         {"account": payable, "credit_in_account_currency": t["net"]}]
	for key, label, extra in (("pf", "PF Payable", "er_pf"), ("esi", "ESI Payable", "er_esi"), ("pt", "Professional Tax Payable", None)):
		amt = t[key] + (t[extra] if extra else 0)
		if amt:
			lines.append({"account": _liability(company, abbr, label), "credit_in_account_currency": amt})
	je = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": company,
	                     "posting_date": get_last_day(getdate(f"{month}-01")), "user_remark": remark, "accounts": lines})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


@frappe.whitelist()
def pay_salaries(month, paid_from="Bank", payment_date=None):
	"""Salaries paid out: clear the payroll payable from bank or cash."""
	company = _company()
	abbr = _abbr(company)
	remark = f"Salaries paid for {month}"
	if frappe.db.exists("Journal Entry", {"company": company, "user_remark": remark, "docstatus": 1}):
		frappe.throw(_("Salaries for {0} are already marked as paid").format(month))
	net = flt(frappe.db.sql("""select sum(net_pay) from `tabSalary Slip` where company=%s and docstatus=1
		and start_date=%s""", (company, getdate(f"{month}-01")))[0][0])
	if net <= 0:
		frappe.throw(_("Run the salaries for {0} first").format(month))
	payable = frappe.get_cached_value("Company", company, "default_payroll_payable_account") or f"Payroll Payable - {abbr}"
	bank = frappe.get_cached_value("Company", company, "default_cash_account" if paid_from == "Cash" else "default_bank_account")
	je = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Bank Entry" if paid_from != "Cash" else "Cash Entry",
	                     "company": company, "posting_date": payment_date or nowdate(), "user_remark": remark,
	                     "cheque_no": f"SAL-{month}", "cheque_date": payment_date or nowdate(),
	                     "accounts": [{"account": payable, "debit_in_account_currency": net},
	                                  {"account": bank, "credit_in_account_currency": net}]})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return {"name": je.name, "amount": net}
