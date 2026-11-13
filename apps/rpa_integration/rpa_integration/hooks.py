app_name = "rpa_integration"
app_title = "RPA Integration"
app_publisher = "Ronak Patel & Associates"
app_description = "Per-client feature gating, provisioning and single sign-on for the client portal"
app_email = "info@caronakpatel.com"
app_license = "Proprietary"
required_apps = ["frappe/erpnext"]

after_install = "rpa_integration.setup.after_install"
after_migrate = "rpa_integration.setup.after_migrate"

# Brand colours (served by rpa_integration.theme.css)
app_include_css = ["/api/method/rpa_integration.theme.css?v=5"]
app_include_js = ["/api/method/rpa_integration.theme.js?v=2"]
web_include_css = ["/api/method/rpa_integration.theme.css?v=5"]

# Per-client numbering: JGE-2627-0001 (see numbering.py)
naming_series_variables = {"FYS": "rpa_integration.numbering.fiscal_year_short"}
doc_events = {
	**{dt: {"before_insert": "rpa_integration.phase2.set_owner_company"}
	   for dt in ("Customer", "Supplier", "Item", "Item Price", "Address", "Contact")},
	**{dt: {"before_insert": "rpa_integration.numbering.set_series"}
	for dt in (
		"Sales Invoice", "Quotation", "Sales Order", "Delivery Note", "Payment Entry", "Purchase Invoice",
		"Purchase Order", "Purchase Receipt", "Journal Entry", "Stock Entry",
	)},
}

# Invoice layouts used by the "Books - ..." print formats
jinja = {"methods": ["rpa_integration.printing.rpa_invoice"]}

# White-label: app tiles, logos and words (see branding.py)
boot_session = ["rpa_integration.branding.boot_session", "rpa_integration.phase2.boot_session"]
