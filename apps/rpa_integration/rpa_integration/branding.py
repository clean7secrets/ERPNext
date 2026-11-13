"""White-label the books site: Books by Ronak Patel & Associates everywhere, no ERPNext / Frappe names or logos."""

import frappe

BRAND = "Books by Ronak Patel & Associates"
FIRM = "Ronak Patel & Associates"

# app -> title shown on the apps screen and in the sidebar
APP_TITLES = {
	"erpnext": "Books",
	"india_compliance": "GST",
	"hrms": "Payroll",
	"frappe": "Settings",
}

# English words people see -> our words (stored as Translation records for language "en")
WORDS = {
	"ERPNext": "Books",
	"ERPNext Settings": "Books Settings",
	"ERPNext Integrations": "Integrations",
	"Frappe HR": "Payroll",
	"Frappe": "Books",
	"India Compliance": "GST",
	"India Compliance Account": "GST Account",
}


def logo_url(wordmark=False):
	from rpa_integration.phase1 import LOGO_FILE, WORDMARK_FILE, _logo_url

	return _logo_url(WORDMARK_FILE if wordmark else LOGO_FILE)


def boot_session(bootinfo):
	"""Runs after the other apps' boot hooks: rename and re-logo every app tile."""
	from rpa_integration.phase1 import GST_ICON_FILE, _logo_url

	books_icon, gst_icon = logo_url(), _logo_url(GST_ICON_FILE)
	header = frappe.db.get_single_value("Navbar Settings", "app_logo") or logo_url(wordmark=True)
	for app in bootinfo.get("app_data") or []:
		name = app.get("app_name")
		if name in APP_TITLES:
			app["app_title"] = APP_TITLES[name]
		icon = gst_icon if name == "india_compliance" else books_icon
		if icon:
			app["app_logo_url"] = icon
	if header:
		bootinfo.app_logo_url = header


def ensure():
	from rpa_integration.phase1 import GST_ICON_FILE, _logo_url

	_logo_url(GST_ICON_FILE)
	logo, wordmark = logo_url(), logo_url(wordmark=True)
	website = {
		"app_name": BRAND, "app_logo": wordmark or logo, "favicon": logo, "splash_image": logo,
		"footer_powered": " ", "hide_footer_signup": 1, "disable_signup": 1,
		"copyright": FIRM, "show_footer_on_login": 0, "title_prefix": BRAND,
	}
	meta = frappe.get_meta("Website Settings")
	for field, value in website.items():
		if meta.has_field(field) and value is not None:
			frappe.db.set_single_value("Website Settings", field, value)

	meta = frappe.get_meta("System Settings")
	if meta.has_field("disable_standard_email_footer"):
		frappe.db.set_single_value("System Settings", "disable_standard_email_footer", 1)
	if meta.has_field("email_footer_address"):
		frappe.db.set_single_value("System Settings", "email_footer_address", f"{FIRM} · caronakpatel.com")

	for source, target in WORDS.items():
		existing = frappe.db.get_value("Translation", {"language": "en", "source_text": source}, "name")
		if existing:
			frappe.db.set_value("Translation", existing, "translated_text", target)
		else:
			frappe.get_doc({"doctype": "Translation", "language": "en", "source_text": source,
			                "translated_text": target}).insert(ignore_permissions=True)
