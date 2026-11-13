"""API the client portal calls. Every call except sso_login needs the RPA Provisioner role."""

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import re
import time

import frappe
from frappe import _

from rpa_integration.features import (
	ALL_FEATURE_ROLES, FEATURES, PROVISIONER_ROLE, READ_ONLY_ROLE, TEAM_ROLES,
	modules_for, roles_for, validate_features,
)

PROTECTED_ROLES = {"System Manager", "Administrator", PROVISIONER_ROLE}


def _only_portal():
	frappe.only_for(PROVISIONER_ROLE)


@contextmanager
def _portal_session():
	"""Check the caller is the portal, then run as Administrator.

	Creating a company runs ERPNext/India Compliance setup hooks that need full rights;
	the portal user itself only holds the RPA Provisioner role.
	"""
	_only_portal()
	caller = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(caller)


def _json_list(value):
	if value is None:
		return []
	if isinstance(value, str):
		value = json.loads(value) if value.strip().startswith("[") else [v.strip() for v in value.split(",") if v.strip()]
	return list(value)


# ---------------------------------------------------------------- catalogue

@frappe.whitelist()
def get_catalogue():
	with _portal_session():
		return {k: {"label": v["label"], "free": v.get("free", False)} for k, v in FEATURES.items()}


# ---------------------------------------------------------------- clients

@frappe.whitelist()
def provision_client(company_name, email, full_name, features=None, gstin=None, state=None, abbr=None,
                     address_line1=None, city=None, pincode=None, phone=None):
	"""Create (or reuse) the client's company and user, then switch on the given features."""
	from rpa_integration import phase1

	with _portal_session():
		features = validate_features(_json_list(features))
		email = email.strip().lower()
		company_name = company_name.strip()
		if frappe.db.exists("Company", company_name):
			owner = frappe.db.get_value("Company", company_name, "rpa_portal_user")
			if owner != email:
				frappe.throw(_("Company name already in use"), frappe.DuplicateEntryError)
		company = _ensure_company(company_name, gstin, state, abbr)
		phase1.company_defaults(company)
		phase1.ensure_company_address(company, address_line1, city, state, pincode,
		                              gstin=(gstin or "").strip().upper() or None, phone=phone, email=email)
		_ensure_user(email, full_name)
		_ensure_company_permission(email, company, is_default=1)
		frappe.db.set_value("Company", company, "rpa_portal_user", email)
		result = _apply_features(email, company, features, status="Active")
		frappe.db.commit()
		return result


@frappe.whitelist()
def set_features(email, company, features, read_only_features=None):
	"""Switch features on/off for a client: exactly the list given ends up enabled.

	read_only_features: features whose plan lapsed; their records stay visible read-only.
	"""
	with _portal_session():
		features = validate_features(_json_list(features))
		lapsed = [f for f in validate_features(_json_list(read_only_features)) if f not in features]
		email = email.strip().lower()
		_check_client(email, company)
		result = _apply_features(email, company, features, status="Active", lapsed=lapsed)
		frappe.db.commit()
		return result


@frappe.whitelist()
def set_read_only(email, company):
	"""Plan lapsed: keep the books visible and printable, but nothing can be changed."""
	with _portal_session():
		email = email.strip().lower()
		_check_client(email, company)
		user = frappe.get_doc("User", email)
		user.remove_roles(*[r for r in ALL_FEATURE_ROLES if r != READ_ONLY_ROLE])
		user.add_roles(READ_ONLY_ROLE)
		_block_modules(user, modules_for(["invoicing", "accounting", "purchase", "inventory", "hr_payroll", "projects"]))
		frappe.db.set_value("Company", company, {"rpa_status": "Read only", "rpa_enabled_features": "[]"})
		frappe.db.commit()
		return get_status(email)


@frappe.whitelist()
def get_status(email):
	with _portal_session():
		email = email.strip().lower()
		companies = frappe.get_all("User Permission", filters={"user": email, "allow": "Company"}, pluck="for_value")
		out = []
		for c in companies:
			row = frappe.db.get_value("Company", c, ["name", "rpa_status", "rpa_enabled_features"], as_dict=True)
			if row:
				row["rpa_enabled_features"] = json.loads(row.rpa_enabled_features or "[]")
				out.append(row)
		roles = frappe.get_roles(email) if frappe.db.exists("User", email) else []
		return {"email": email, "companies": out, "roles": sorted(r for r in roles if r not in ("All", "Guest"))}


# ---------------------------------------------------------------- team

@frappe.whitelist()
def grant_team_access(email, full_name, company):
	"""Give a firm team member reviewer access to one client company."""
	with _portal_session():
		email = email.strip().lower()
		_ensure_user(email, full_name)
		frappe.get_doc("User", email).add_roles(*[r for r in TEAM_ROLES if frappe.db.exists("Role", r)])
		_ensure_company_permission(email, company, is_default=0)
		frappe.db.commit()
		return get_status(email)


@frappe.whitelist()
def revoke_team_access(email, company):
	with _portal_session():
		frappe.db.delete("User Permission", {"user": email.strip().lower(), "allow": "Company", "for_value": company})
		frappe.db.commit()
		return get_status(email)


# ---------------------------------------------------------------- single sign-on

def make_sso_token(email, ttl=120):
	"""Same format the portal produces (for tests): base64url(payload).hex(hmac_sha256)."""
	payload = base64.urlsafe_b64encode(json.dumps(
		{"email": email, "exp": int(time.time()) + ttl, "nonce": frappe.generate_hash(length=16)}
	).encode()).decode().rstrip("=")
	return payload + "." + _sign(payload)


def _sign(payload):
	secret = frappe.conf.get("rpa_sso_secret")
	if not secret:
		frappe.throw(_("Single sign-on is not configured"), frappe.PermissionError)
	return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def sso_login(token):
	"""Portal 'Open my books' link: verify the short-lived signed token, log the client in, go to the desk."""
	try:
		payload, sig = token.rsplit(".", 1)
		if not hmac.compare_digest(_sign(payload), sig):
			raise ValueError("bad signature")
		data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
		if int(data["exp"]) < time.time() or int(data["exp"]) > time.time() + 300:
			raise ValueError("expired")
		nonce_key = f"rpa_sso_nonce:{data['nonce']}"
		if frappe.cache().get_value(nonce_key):
			raise ValueError("reused")
		frappe.cache().set_value(nonce_key, 1, expires_in_sec=600)
		email = data["email"].strip().lower()
		if not frappe.db.get_value("User", email, "enabled"):
			raise ValueError("no user")
		if PROTECTED_ROLES & set(frappe.get_roles(email)):
			raise ValueError("protected user")
	except Exception:
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = "/login?rpa_sso=failed"
		return
	frappe.local.login_manager.login_as(email)
	frappe.local.response["type"] = "redirect"
	is_client = frappe.db.exists("Company", {"rpa_portal_user": email})
	frappe.local.response["location"] = "/app/my-business" if is_client else "/app"


# ---------------------------------------------------------------- helpers

def _ensure_company(company_name, gstin=None, state=None, abbr=None):
	if frappe.db.exists("Company", company_name):
		return company_name
	doc = frappe.get_doc({
		"doctype": "Company",
		"company_name": company_name,
		"abbr": abbr or _unique_abbr(company_name),
		"country": "India",
		"default_currency": "INR",
		"chart_of_accounts": "Standard",
		"create_chart_of_accounts_based_on": "Standard Template",
	})
	if gstin and doc.meta.has_field("gstin"):
		doc.gstin = gstin.strip().upper()
		if doc.meta.has_field("gst_category"):
			doc.gst_category = "Registered Regular"
	elif doc.meta.has_field("gst_category"):
		doc.gst_category = "Unregistered"
	if state and doc.meta.has_field("state"):
		doc.state = state
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def _unique_abbr(name):
	base = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", name)).upper()[:4] or "CL"
	abbr, n = base, 1
	while frappe.db.exists("Company", {"abbr": abbr}):
		n += 1
		abbr = f"{base}{n}"
	return abbr


def _ensure_user(email, full_name):
	if frappe.db.exists("User", email):
		if PROTECTED_ROLES & set(frappe.get_roles(email)):
			frappe.throw(_("This user is an administrator and cannot be managed from the portal"))
		return
	first, _sep, last = (full_name or email.split("@")[0]).strip().partition(" ")
	frappe.get_doc({
		"doctype": "User", "email": email, "first_name": first, "last_name": last,
		"user_type": "System User", "send_welcome_email": 0, "enabled": 1,
	}).insert(ignore_permissions=True)


def _ensure_company_permission(email, company, is_default=0):
	if not frappe.db.exists("User Permission", {"user": email, "allow": "Company", "for_value": company}):
		frappe.get_doc({
			"doctype": "User Permission", "user": email, "allow": "Company", "for_value": company,
			"apply_to_all_doctypes": 1, "is_default": is_default,
		}).insert(ignore_permissions=True)


def _check_client(email, company):
	if not frappe.db.exists("User Permission", {"user": email, "allow": "Company", "for_value": company}):
		frappe.throw(_("{0} is not linked to {1}").format(email, company), frappe.DoesNotExistError)


def _apply_features(email, company, features, status, lapsed=None):
	lapsed = lapsed or []
	user = frappe.get_doc("User", email)
	wanted = set(roles_for(features)) | ({READ_ONLY_ROLE} if lapsed else set())
	existing = [r for r in wanted if frappe.db.exists("Role", r)]
	to_remove = [r for r in ALL_FEATURE_ROLES if r not in wanted]
	user.remove_roles(*to_remove)
	if existing:
		user.add_roles(*existing)
	_block_modules(user, modules_for(list(features) + list(lapsed)))
	frappe.db.set_value("Company", company, {"rpa_status": status, "rpa_enabled_features": json.dumps(features)})
	return {"email": email, "company": company, "features": features, "read_only": lapsed, "roles": existing}


def _block_modules(user, allowed):
	all_modules = frappe.get_all("Module Def", pluck="name")
	user.reload()
	user.set("block_modules", [{"module": m} for m in all_modules if m not in allowed])
	user.flags.ignore_permissions = True
	user.save()
