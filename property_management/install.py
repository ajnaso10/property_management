import frappe
from frappe.utils import cint


ROLE_PROPERTY_SUPER_ADMIN = "Property Super Admin"
ROLE_PROPERTY_USER = "Property User"
APP_ROLES = (ROLE_PROPERTY_SUPER_ADMIN, ROLE_PROPERTY_USER)


def before_install():
	"""Roles have to exist before DocType permissions and the workspace are imported."""
	ensure_roles()


def after_install():
	ensure_roles()
	enable_login_identifiers()
	ensure_property_settings()
	disable_public_signup()


def ensure_roles():
	"""Create the app roles. Idempotent so install and tests can call it safely."""
	for role_name in APP_ROLES:
		if frappe.db.exists("Role", role_name):
			role = frappe.get_doc("Role", role_name)
			changed = False
			if cint(role.disabled):
				role.disabled = 0
				changed = True
			if not cint(role.desk_access):
				role.desk_access = 1
				changed = True
			if changed:
				role.save(ignore_permissions=True)
			continue

		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"disabled": 0,
				"is_custom": 0,
			}
		).insert(ignore_permissions=True)


def enable_login_identifiers():
	"""Property users sign in with the mobile number stored as username and mobile_no.

	Frappe only matches those columns when the corresponding System Settings flags are on.
	This site is intended to run Frappe plus this app, so the flags are enabled at install.
	"""
	frappe.db.set_single_value("System Settings", "allow_login_using_mobile_number", 1)
	frappe.db.set_single_value("System Settings", "allow_login_using_user_name", 1)


def ensure_property_settings():
	if frappe.db.exists("DocType", "Property Settings") and not frappe.db.exists(
		"Property Settings", "Property Settings"
	):
		doc = frappe.new_doc("Property Settings")
		doc.billing_day = 1
		doc.prorate_partial_months = 1
		doc.due_days_after_billing = 7
		doc.insert(ignore_permissions=True)


def disable_public_signup():
	"""Keep account creation in the super-admin API. Frappe already defaults this on."""
	if frappe.db.exists("DocType", "Website Settings"):
		frappe.db.set_single_value("Website Settings", "disable_signup", 1)
