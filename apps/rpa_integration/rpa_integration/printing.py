"""Online Books invoice layouts.

One renderer builds every layout from the same data, so all of them carry the mandatory GST invoice
details. A client's choices (layout, colour, logo, bank details, ...) are stored on their Company in
the rpa_inv_* fields and are read when the PDF is made, so one client's style never shows to another.

wkhtmltopdf uses an old WebKit: layouts use tables and inline values only (no flexbox, grid or CSS variables).
"""

import base64
import io
import re
from collections import OrderedDict
from urllib.parse import quote

import frappe
from frappe.utils import cint, flt, fmt_money, formatdate, getdate, strip_html
from markupsafe import Markup

LAYOUTS = OrderedDict([
	("classic", "Classic GST"),
	("modern", "Modern"),
	("minimal", "Minimal"),
	("compact", "Compact"),
	("letterhead", "Letterhead"),
	("bilingual", "Bilingual"),
	("thermal", "Thermal receipt"),
])
LAYOUT_BY_LABEL = {v: k for k, v in LAYOUTS.items()}

DEFAULT_COLOUR = "#003366"
FONTS = {
	"Sans": "'Helvetica Neue', Helvetica, Arial, 'Noto Sans', 'Noto Sans Devanagari', sans-serif",
	"Serif": "Georgia, 'Times New Roman', 'Noto Serif', 'Noto Sans Devanagari', serif",
	"Rounded": "'Trebuchet MS', 'Segoe UI', 'Noto Sans', 'Noto Sans Devanagari', sans-serif",
}

# English label -> (Hindi, Marathi)
SECOND_LANGUAGE = {
	"Tax Invoice": ("टैक्स इनवॉइस", "कर बीजक"),
	"Invoice": ("इनवॉइस", "बीजक"),
	"Bill of Supply": ("बिल ऑफ सप्लाई", "पुरवठा बिल"),
	"Credit Note": ("क्रेडिट नोट", "क्रेडिट नोट"),
	"Debit Note": ("डेबिट नोट", "डेबिट नोट"),
	"Quotation": ("कोटेशन", "दरपत्रक"),
	"Invoice No.": ("इनवॉइस क्र.", "बीजक क्र."),
	"Quote No.": ("कोटेशन क्र.", "दरपत्रक क्र."),
	"Date": ("दिनांक", "दिनांक"),
	"Due Date": ("देय तिथि", "देय दिनांक"),
	"Valid Till": ("मान्य तिथि तक", "वैध दिनांकापर्यंत"),
	"Bill To": ("बिल प्राप्तकर्ता", "खरेदीदार"),
	"Ship To": ("डिलीवरी पता", "पोहोच पत्ता"),
	"Place of Supply": ("आपूर्ति का स्थान", "पुरवठ्याचे ठिकाण"),
	"Item": ("विवरण", "तपशील"),
	"HSN/SAC": ("HSN/SAC", "HSN/SAC"),
	"Qty": ("मात्रा", "नग"),
	"Rate": ("दर", "दर"),
	"Disc.": ("छूट", "सूट"),
	"GST": ("GST", "GST"),
	"Amount": ("राशि", "रक्कम"),
	"Taxable Value": ("कर योग्य मूल्य", "करपात्र मूल्य"),
	"Total": ("कुल", "एकूण"),
	"Round off": ("पूर्णांकन", "पूर्णांक"),
	"Amount in words": ("राशि शब्दों में", "रक्कम अक्षरी"),
	"Bank Details": ("बैंक विवरण", "बँक तपशील"),
	"Terms and Conditions": ("नियम व शर्तें", "अटी व शर्ती"),
	"Authorised Signatory": ("अधिकृत हस्ताक्षरकर्ता", "अधिकृत स्वाक्षरी"),
	"Scan to pay": ("भुगतान हेतु स्कैन करें", "पैसे भरण्यासाठी स्कॅन करा"),
	"Tax is payable on reverse charge": ("कर रिवर्स चार्ज पर देय है", "कर रिव्हर्स चार्जवर देय आहे"),
	"HSN/SAC summary": ("HSN/SAC सारांश", "HSN/SAC सारांश"),
	"Thank you for your business": ("आपके व्यवसाय के लिए धन्यवाद", "आपल्या व्यवसायाबद्दल धन्यवाद"),
}


# ------------------------------------------------------------------ entry point (jinja method)

def rpa_invoice(doc, layout=None):
	"""Render a Sales Invoice or Quotation. layout=None uses the company's chosen layout."""
	try:
		ctx = _context(doc, layout)
		html = frappe.render_template("rpa_integration/templates/print/books_invoice.html", ctx)
		return Markup(html)
	except Exception:
		frappe.log_error(title="Online Books invoice layout failed", reference_doctype=doc.doctype,
		                 reference_name=doc.name)
		raise


# ------------------------------------------------------------------ data

def _context(doc, layout):
	style = company_style(doc.company)
	layout = layout or style.layout
	if layout not in LAYOUTS:
		layout = "classic"
	lang = style.second_language if layout == "bilingual" else None
	company = frappe.get_cached_doc("Company", doc.company)

	kind = _document_kind(doc, company)
	items, hsn_rows, has_disc = _items(doc)
	return {
		"doc": doc,
		"layout": layout,
		"colour": style.colour,
		"tint": _tint(style.colour, 0.92),
		"font": FONTS.get(style.font, FONTS["Sans"]),
		"L": _labeller(lang),
		"show_hsn": style.show_hsn,
		"show_discount": style.show_discount and has_disc,
		"show_uom": style.show_uom,
		"title": kind["title"],
		"number_label": kind["number_label"],
		"is_quote": doc.doctype == "Quotation",
		"seller": _seller(doc, company, style),
		"buyer": _buyer(doc),
		"dates": _dates(doc),
		"items": items,
		"hsn_rows": hsn_rows,
		"show_hsn_summary": style.show_hsn and bool(doc.get("company_gstin")) and len(hsn_rows) > 0,
		"totals": _totals(doc),
		"in_words": doc.get("base_in_words") or doc.get("in_words") or "",
		"reverse_charge": bool(cint(doc.get("is_reverse_charge"))),
		"irn": doc.get("irn"),
		"einvoice_qr": _qr_data_uri(doc.get("signed_qr_code"), 3) if doc.get("signed_qr_code") else None,
		"upi_qr": _upi_qr(doc, company, style),
		"bank": style.bank_details,
		"terms": _terms(doc, style),
		"header_note": style.header_note,
		"footer_note": style.footer_note,
		"logo": style.logo,
		"signature": style.signature,
		"letterhead_header": style.letterhead_header if layout == "letterhead" else None,
		"letterhead_footer": style.letterhead_footer if layout == "letterhead" else None,
		"money": lambda v: _num(v),
		"rupees": lambda v: fmt_money(flt(v), precision=2, currency="INR"),
	}


def company_style(company):
	c = frappe.get_cached_doc("Company", company)
	g = lambda f, default=None: c.get(f) if c.get(f) not in (None, "") else default
	return frappe._dict(
		layout=LAYOUT_BY_LABEL.get(g("rpa_inv_layout", "Classic GST"), "classic"),
		colour=_safe_colour(g("rpa_inv_colour", DEFAULT_COLOUR)),
		font=g("rpa_inv_font", "Sans"),
		second_language={"Hindi": 0, "Marathi": 1}.get(g("rpa_inv_second_language", "Hindi"), 0),
		show_hsn=bool(cint(g("rpa_inv_show_hsn", 1))),
		show_discount=bool(cint(g("rpa_inv_show_discount", 1))),
		show_uom=bool(cint(g("rpa_inv_show_uom", 1))),
		logo=_image_data_uri(g("rpa_inv_logo") or g("company_logo")),
		signature=_image_data_uri(g("rpa_inv_signature")),
		letterhead_header=_image_data_uri(g("rpa_inv_letterhead_header")),
		letterhead_footer=_image_data_uri(g("rpa_inv_letterhead_footer")),
		header_note=g("rpa_inv_header_note"),
		footer_note=g("rpa_inv_footer_note"),
		terms=g("rpa_inv_terms"),
		bank_details=g("rpa_inv_bank_details"),
		upi_id=(g("rpa_inv_upi_id") or "").strip(),
	)


def _document_kind(doc, company):
	if doc.doctype == "Quotation":
		return {"title": "Quotation", "number_label": "Quote No."}
	if cint(doc.get("is_return")):
		return {"title": "Credit Note", "number_label": "Invoice No."}
	if cint(doc.get("is_debit_note")):
		return {"title": "Debit Note", "number_label": "Invoice No."}
	if not doc.get("company_gstin"):
		return {"title": "Invoice", "number_label": "Invoice No."}
	if company.get("gst_category") == "Composition" or doc.get("gst_category") == "Composition":
		return {"title": "Bill of Supply", "number_label": "Invoice No."}
	return {"title": "Tax Invoice", "number_label": "Invoice No."}


def _seller(doc, company, style):
	address = doc.get("company_address")
	if not address:
		rows = frappe.db.sql("""select a.name from `tabAddress` a join `tabDynamic Link` l on l.parent = a.name
			where l.link_doctype = 'Company' and l.link_name = %s and a.is_your_company_address = 1
			order by a.is_primary_address desc limit 1""", doc.company)
		address = rows[0][0] if rows else None
	return frappe._dict(
		name=company.company_name,
		gstin=doc.get("company_gstin") or company.get("gstin"),
		address=_address_lines(address, doc.get("company_address_display")),
		phone=company.get("phone_no"),
		email=company.get("email"),
		pan=company.get("pan"),
	)


def _buyer(doc):
	return frappe._dict(
		name=doc.get("customer_name") or doc.get("party_name") or doc.get("customer"),
		gstin=doc.get("billing_address_gstin"),
		address=_address_lines(doc.get("customer_address"), doc.get("address_display")),
		shipping=_address_lines(doc.get("shipping_address_name"), doc.get("shipping_address"))
		if doc.get("shipping_address_name") and doc.get("shipping_address_name") != doc.get("customer_address") else None,
		place_of_supply=doc.get("place_of_supply"),
		phone=doc.get("contact_mobile") or doc.get("contact_phone"),
	)


def _dates(doc):
	if doc.doctype == "Quotation":
		return frappe._dict(date=formatdate(doc.transaction_date), second_label="Valid Till",
		                    second=formatdate(doc.valid_till) if doc.get("valid_till") else None)
	due = doc.get("due_date")
	return frappe._dict(date=formatdate(doc.posting_date), second_label="Due Date",
	                    second=formatdate(due) if due and getdate(due) != getdate(doc.posting_date) else None)


def _items(doc):
	rows, hsn = [], OrderedDict()
	has_disc = False
	for i, it in enumerate(doc.get("items") or [], start=1):
		taxable = flt(it.get("taxable_value")) or flt(it.get("base_net_amount")) or flt(it.get("net_amount"))
		gst_rate = flt(it.get("igst_rate")) or (flt(it.get("cgst_rate")) + flt(it.get("sgst_rate")))
		tax = sum(flt(it.get(f)) for f in ("igst_amount", "cgst_amount", "sgst_amount", "cess_amount"))
		disc = flt(it.get("discount_percentage"))
		has_disc = has_disc or disc > 0 or flt(it.get("discount_amount")) > 0
		desc = it.item_name or it.item_code
		extra = strip_html(it.get("description") or "").strip()
		if extra and extra.lower() != (desc or "").lower():
			desc = f"{desc} — {extra[:160]}"
		rows.append(frappe._dict(
			idx=i, name=desc, hsn=it.get("gst_hsn_code") or "", qty=_qty(it.qty), uom=it.get("uom") or "",
			rate=flt(it.rate), discount=(f"{flt(disc, 2):g}%" if disc else (_num(it.get("discount_amount")) if flt(it.get("discount_amount")) else "")),
			taxable=taxable, gst_rate=gst_rate, amount=flt(it.amount),
		))
		key = (it.get("gst_hsn_code") or "-", gst_rate)
		h = hsn.setdefault(key, frappe._dict(hsn=key[0], rate=gst_rate, taxable=0, cgst=0, sgst=0, igst=0, cess=0))
		h.taxable += taxable
		h.cgst += flt(it.get("cgst_amount"))
		h.sgst += flt(it.get("sgst_amount"))
		h.igst += flt(it.get("igst_amount"))
		h.cess += flt(it.get("cess_amount"))
	return rows, list(hsn.values()), has_disc


def _totals(doc):
	lines = [("Taxable Value", flt(doc.net_total))]
	if flt(doc.get("discount_amount")) and doc.get("apply_discount_on") == "Grand Total":
		lines.append(("Disc.", -flt(doc.discount_amount)))
	for t in doc.get("taxes") or []:
		amount = flt(t.get("tax_amount_after_discount_amount") or t.get("tax_amount"))
		if not amount:
			continue
		kind = (t.get("gst_tax_type") or "").upper()
		label = f"{kind} @ {flt(t.rate):g}%" if kind and flt(t.rate) else (t.description or t.account_head)
		lines.append((label, amount))
	total = flt(doc.rounded_total) if flt(doc.get("rounded_total")) and not cint(doc.get("disable_rounded_total")) else flt(doc.grand_total)
	if flt(doc.get("rounding_adjustment")) and total == flt(doc.get("rounded_total")):
		lines.append(("Round off", flt(doc.rounding_adjustment)))
	return frappe._dict(lines=lines, total=total)


def _terms(doc, style):
	text = doc.get("terms") or style.terms or ""
	return strip_html(text).strip() if "<" in text else text.strip()


# ------------------------------------------------------------------ QR codes and images

def _upi_qr(doc, company, style):
	if doc.doctype != "Sales Invoice" or not style.upi_id or cint(doc.get("is_return")):
		return None
	if not re.match(r"^[\w.\-]{2,256}@[a-zA-Z][\w]{1,64}$", style.upi_id):
		return None
	amount = flt(doc.get("outstanding_amount")) if doc.docstatus == 1 else flt(doc.rounded_total or doc.grand_total)
	if amount <= 0:
		return None
	uri = (f"upi://pay?pa={quote(style.upi_id)}&pn={quote(company.company_name[:40])}"
	       f"&am={amount:.2f}&cu=INR&tn={quote('Invoice ' + doc.name)}")
	return frappe._dict(img=_qr_data_uri(uri, 3), upi_id=style.upi_id, amount=amount)


def _qr_data_uri(text, scale):
	import pyqrcode

	buf = io.BytesIO()
	pyqrcode.create(text, error="M").png(buf, scale=scale, quiet_zone=2)
	return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _image_data_uri(file_url):
	"""Embed an attached image so the PDF never has to fetch it over the network."""
	if not file_url:
		return None
	try:
		name = frappe.db.get_value("File", {"file_url": file_url}, "name")
		if not name:
			return None
		f = frappe.get_doc("File", name)
		content = f.get_content()
		if isinstance(content, str):
			content = content.encode()
		ext = (file_url.rsplit(".", 1)[-1] or "png").lower()
		mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "svg": "svg+xml", "webp": "webp"}.get(ext, "png")
		return f"data:image/{mime};base64," + base64.b64encode(content).decode()
	except Exception:
		frappe.log_error(title="Online Books invoice image failed")
		return None


# ------------------------------------------------------------------ helpers

def _labeller(lang):
	def L(text):
		if lang is None or text not in SECOND_LANGUAGE:
			return text
		return Markup(f"{frappe.utils.escape_html(text)} <span class='l2'>/ {SECOND_LANGUAGE[text][lang]}</span>")
	return L


def _num(v):
	return fmt_money(flt(v), precision=2)


def _qty(q):
	q = flt(q)
	return f"{q:g}" if q == int(q) else f"{q:.3f}".rstrip("0").rstrip(".")


def _address_lines(name, fallback_html=None):
	"""Street, city + PIN, state: GSTIN, phone and email are printed separately."""
	if name and frappe.db.exists("Address", name):
		a = frappe.get_cached_doc("Address", name)
		lines = [a.address_line1, a.address_line2, " ".join(x for x in (a.city, a.pincode) if x)]
		if a.state:
			lines.append(a.state if (a.country or "India") == "India" else f"{a.state}, {a.country}")
		return "\n".join(x.strip() for x in lines if x and x.strip())
	text = _clean_address(fallback_html)
	keep = [ln for ln in text.splitlines()
	        if not re.match(r"^(gstin|phone|email|e-mail|india$)", ln.strip(), re.I)]
	return "\n".join(keep)


def _clean_address(html):
	if not html:
		return ""
	text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
	text = strip_html(text)
	lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
	return "\n".join(lines)


def _tint(hex_colour, amount):
	"""Mix a colour with white: amount 0.92 = 92% white."""
	r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
	mix = lambda v: round(v + (255 - v) * amount)
	return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


def _safe_colour(value):
	value = (value or "").strip()
	return value if re.match(r"^#[0-9a-fA-F]{6}$", value) else DEFAULT_COLOUR
