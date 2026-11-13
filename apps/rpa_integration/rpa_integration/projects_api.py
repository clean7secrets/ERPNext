"""Simple projects for Online Books clients (feature "projects"): log time, bill the hours."""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, nowdate


def _company():
	from rpa_integration.books_api import _require, client_company

	company = client_company()
	_require(company, "projects")
	return company


def _own_project(project, company):
	if frappe.db.get_value("Project", project, "company") != company:
		frappe.throw(_("Please pick one of your projects"), frappe.PermissionError)


@frappe.whitelist()
def projects():
	company = _company()
	rows = frappe.get_all("Project", filters={"company": company, "status": ["!=", "Cancelled"]},
	                      fields=["name", "project_name", "customer", "status"], order_by="creation desc", limit_page_length=50)
	for r in rows:
		r.unbilled_hours, r.unbilled_amount = frappe.db.sql("""select coalesce(sum(d.billing_hours),0), coalesce(sum(d.billing_amount),0)
			from `tabTimesheet Detail` d join `tabTimesheet` t on t.name=d.parent
			where d.project=%s and t.docstatus=1 and d.is_billable=1 and coalesce(d.sales_invoice,'')=''""", r.name)[0]
	return rows


@frappe.whitelist()
def create_project(project_name, customer=None, hourly_rate=0):
	company = _company()
	project_name = (project_name or "").strip()
	if len(project_name) < 2:
		frappe.throw(_("Please enter the project name"))
	if customer and frappe.db.get_value("Customer", customer, "rpa_company") != company:
		frappe.throw(_("Please pick one of your customers"), frappe.PermissionError)
	p = frappe.get_doc({"doctype": "Project", "project_name": project_name, "company": company, "customer": customer or None,
	                    "status": "Open", "rpa_hourly_rate": flt(hourly_rate)} if frappe.get_meta("Project").has_field("rpa_hourly_rate")
	                   else {"doctype": "Project", "project_name": project_name, "company": company, "customer": customer or None,
	                         "status": "Open"})
	p.flags.ignore_permissions = True
	p.insert()
	return {"name": p.name, "project_name": p.project_name}


@frappe.whitelist()
def log_time(project, hours, work_date=None, activity=None, note=None, billable=1, rate=None):
	company = _company()
	_own_project(project, company)
	hours = flt(hours)
	if hours <= 0 or hours > 24:
		frappe.throw(_("Hours must be between 0 and 24"))
	activity = activity if activity and frappe.db.exists("Activity Type", activity) else "Execution"
	rate = flt(rate) or flt(frappe.db.get_value("Project", project, "rpa_hourly_rate")
	                        if frappe.get_meta("Project").has_field("rpa_hourly_rate") else 0)
	start = get_datetime(f"{work_date or nowdate()} 10:00:00")
	ts = frappe.get_doc({"doctype": "Timesheet", "company": company,
	                     "customer": frappe.db.get_value("Project", project, "customer"),
	                     "note": note, "time_logs": [{
		                     "activity_type": activity, "from_time": start, "to_time": add_to_date(start, hours=hours),
		                     "hours": hours, "project": project, "is_billable": cint(billable),
		                     "billing_hours": hours if cint(billable) else 0, "billing_rate": rate,
		                     "billing_amount": hours * rate if cint(billable) else 0, "description": note}]})
	ts.flags.ignore_permissions = True
	ts.insert()
	ts.submit()
	return {"name": ts.name, "hours": hours, "amount": hours * rate if cint(billable) else 0}


@frappe.whitelist()
def bill_hours(project, item_code=None):
	"""Turn a project's unbilled hours into one GST invoice."""
	from rpa_integration.books_api import _service_item

	company = _company()
	_own_project(project, company)
	customer = frappe.db.get_value("Project", project, "customer")
	if not customer:
		frappe.throw(_("Set the customer on this project first"))
	logs = frappe.db.sql("""select d.name, d.parent, d.billing_hours, d.billing_amount from `tabTimesheet Detail` d
		join `tabTimesheet` t on t.name=d.parent where d.project=%s and t.docstatus=1 and d.is_billable=1
		and coalesce(d.sales_invoice,'')='' and d.billing_hours > 0""", project, as_dict=True)
	if not logs:
		frappe.throw(_("No unbilled hours on this project"))
	hours = sum(flt(l.billing_hours) for l in logs)
	amount = sum(flt(l.billing_amount) for l in logs)
	item_code = item_code or _service_item(company)
	si = frappe.get_doc({"doctype": "Sales Invoice", "company": company, "customer": customer, "project": project,
	                     "posting_date": nowdate(), "items": [{"item_code": item_code, "qty": hours,
	                                                           "rate": amount / hours if hours else 0, "project": project}],
	                     "timesheets": [{"time_sheet": l.parent, "timesheet_detail": l.name, "billing_hours": l.billing_hours,
	                                     "billing_amount": l.billing_amount, "project_name": project} for l in logs]})
	si.set_missing_values()
	si.flags.ignore_permissions = True
	si.insert()
	si.submit()
	return {"name": si.name, "grand_total": si.grand_total, "hours": hours}
