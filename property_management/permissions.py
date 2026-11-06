import frappe

from property_management.install import ROLE_PROPERTY_SUPER_ADMIN, ROLE_PROPERTY_USER

PRIVILEGED_ROLES = ("System Manager", ROLE_PROPERTY_SUPER_ADMIN)
PROFILE_DOCTYPE = "Property User Profile"


def is_privileged(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	return bool(roles.intersection(PRIVILEGED_ROLES))


def is_property_user(user=None):
	user = user or frappe.session.user
	return ROLE_PROPERTY_USER in set(frappe.get_roles(user))


def owner_field(doctype):
	if doctype == PROFILE_DOCTYPE:
		return "user"
	return "owner_user"


def permission_query_conditions(user, doctype):
	"""Restrict list/report queries. Privileged roles see every row."""
	user = user or frappe.session.user
	if is_privileged(user):
		return None
	if not is_property_user(user):
		return "1=0"
	column = owner_field(doctype)
	return f"`tab{doctype}`.`{column}` = {frappe.db.escape(user)}"


def has_permission(doc, ptype=None, user=None, debug=False):
	"""Deny document access when the row belongs to someone else.

	Frappe v16 treats a falsy hook result as a deny, so this returns True when
	the user is allowed. It never grants a permission the role does not already have.
	"""
	user = user or frappe.session.user
	if is_privileged(user):
		return True
	if not is_property_user(user):
		return False

	owner = doc.get(owner_field(doc.doctype))
	if not owner:
		# Unsaved documents get their owner in validate, which runs after the create check.
		return bool(doc.get("__islocal") or (hasattr(doc, "is_new") and doc.is_new()))
	return owner == user


def has_app_permission():
	user = frappe.session.user
	if user == "Guest":
		return False
	return is_privileged(user) or is_property_user(user)


def query_property_user_profile(user=None):
	return permission_query_conditions(user, "Property User Profile")


def query_building(user=None):
	return permission_query_conditions(user, "Building")


def query_flat(user=None):
	return permission_query_conditions(user, "Flat")


def query_area(user=None):
	return permission_query_conditions(user, "Area")


def query_bed(user=None):
	return permission_query_conditions(user, "Bed")


def query_tenant(user=None):
	return permission_query_conditions(user, "Tenant")


def query_bed_allocation(user=None):
	return permission_query_conditions(user, "Bed Allocation")
