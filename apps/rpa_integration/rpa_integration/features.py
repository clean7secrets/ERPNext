"""Feature catalogue: what a client gets in ERPNext when a feature is switched on.

Each feature lists the standard ERPNext/HRMS roles it grants and the desk modules it
shows. Anything not switched on is hidden (blocked modules) and not permitted (no role).
Prices live in the portal, not here, so they can change without touching ERPNext.
"""

FEATURES = {
	"invoicing": {
		"label": "Invoicing and quotations",
		"roles": ["RPA Invoicing", "Sales User"],
		"modules": ["Selling", "CRM"],
		"free": True,
	},
	"accounting": {
		"label": "Accounting, banking and GST",
		"roles": ["Accounts User"],
		"modules": ["Accounts", "Assets", "GST India", "Income Tax India", "Regional"],
	},
	"purchase": {
		"label": "Purchases and suppliers",
		"roles": ["Purchase User"],
		"modules": ["Buying", "Subcontracting"],
	},
	"inventory": {
		"label": "Inventory and warehouses",
		"roles": ["Stock User", "Item Manager"],
		"modules": ["Stock"],
	},
	"hr_payroll": {
		"label": "HR and payroll",
		"roles": ["HR User"],
		"modules": ["HR", "Payroll"],
	},
	"projects": {
		"label": "Projects and timesheets",
		"roles": ["Projects User"],
		"modules": ["Projects"],
	},
	"manufacturing": {
		"label": "Manufacturing",
		"roles": ["Manufacturing User"],
		"modules": ["Manufacturing", "Quality Management"],
	},
}

# Modules every client can always see (basic setup, contacts, printing).
ALWAYS_VISIBLE_MODULES = {"Setup", "Contacts", "Desk", "Printing", "Utilities", "Communication", "Portal", "Core", "Email", "Automation"}

# Roles a lapsed client keeps: read, print and export only, never edit.
READ_ONLY_ROLE = "RPA Read Only"

# Role the portal's API user holds; only it may call the provisioning API.
PROVISIONER_ROLE = "RPA Provisioner"

# Roles for the firm's team on the companies they are allocated.
TEAM_ROLES = [
	"Accounts Manager", "Accounts User", "Sales Manager", "Sales User", "Purchase Manager",
	"Purchase User", "Stock Manager", "Stock User", "Item Manager", "HR Manager", "HR User",
	"Projects Manager", "Projects User", "Manufacturing User",
]

# Every role that features can grant, so switching a feature off can remove it cleanly.
ALL_FEATURE_ROLES = sorted({r for f in FEATURES.values() for r in f["roles"]} | {READ_ONLY_ROLE})


def validate_features(features):
	unknown = [f for f in features if f not in FEATURES]
	if unknown:
		raise ValueError(f"Unknown feature(s): {', '.join(unknown)}")
	return sorted(set(features))


def roles_for(features):
	return sorted({r for f in features for r in FEATURES[f]["roles"]})


def modules_for(features):
	return set(ALWAYS_VISIBLE_MODULES) | {m for f in features for m in FEATURES[f]["modules"]}
