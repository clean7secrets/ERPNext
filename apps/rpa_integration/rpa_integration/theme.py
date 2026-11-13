"""Brand colours for books.caronakpatel.com, matching the client portal.

ICAI Blue #003366 (primary), Karbodh Grey #E3E8EF (page background),
Karbodh Blue #C4DAFB (highlights), ICAI Orange #F37920 and ICAI Green #55B848 (accents).
"""

import frappe
from werkzeug.wrappers import Response

CSS = """
:root, [data-theme="light"] {
	--primary: #003366;
	--primary-color: #003366;
	--btn-primary: #003366;
	--bg-color: #E3E8EF;
	--subtle-accent: #C4DAFB;
	--sidebar-select-color: #C4DAFB;
	--checkbox-color: #003366;
	--rpa-orange: #F37920;
	--rpa-green: #55B848;
}
.btn-primary, .btn-primary:focus { background-color: #003366 !important; border-color: #003366 !important; color: #fff !important; }
.btn-primary:hover, .btn-primary:active { background-color: #002347 !important; border-color: #002347 !important; }
[data-theme="light"] body, [data-theme="light"] .page-container { background-color: #E3E8EF; }
.desk-sidebar .standard-sidebar-item.selected, .sidebar-item-container .selected { background-color: #C4DAFB !important; }
.desk-sidebar .standard-sidebar-item.selected .sidebar-item-label, .sidebar-item-container .selected .item-anchor { color: #003366 !important; }
a.underline, .form-link-title { color: #003366; }
.indicator-pill.green, .indicator.green::before { --indicator-color: #55B848; }
.for-login .page-card, .for-forgot .page-card, .for-signup .page-card { border-top: 4px solid #F37920; }
.for-login .btn-primary { background-color: #003366 !important; }
.page-card-head .app-logo, .page-card-head img.app-logo { height: 76px !important; max-height: 76px !important; width: auto !important; max-width: 100% !important; }
body::after { content: "Powered by ERPNext"; position: fixed; right: 12px; bottom: 8px; z-index: 1030;
  font-size: 11px; line-height: 1; color: #5f6b7a; opacity: .85; pointer-events: none; }
@media print { body::after { content: none; } }
/* Clients: no full ERPNext module menu; My Business is their home */
body.rpa-client .body-sidebar-container { display: none !important; }
"""


@frappe.whitelist(allow_guest=True, methods=["GET"])
def css():
	return Response(CSS, mimetype="text/css", headers={"Cache-Control": "public, max-age=3600"})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def js():
	import os

	path = os.path.join(os.path.dirname(__file__), "public", "js", "books_client.js")
	with open(path) as fh:
		code = fh.read()
	return Response(code, mimetype="application/javascript", headers={"Cache-Control": "public, max-age=3600"})
