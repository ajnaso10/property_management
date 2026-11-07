import frappe
from frappe import _
from frappe.utils import cint, getdate
from frappe.utils.password import check_password, update_password

from property_management.auth import (
	get_profile,
	must_change_password,
	normalize_mobile,
	resolve_user,
	synthetic_email,
)
from property_management.install import ROLE_PROPERTY_USER, ensure_roles
from property_management.permissions import is_privileged


def _require_super_admin():
	if not is_privileged():
		frappe.throw(
			_("Only a Property Super Admin can manage property users."),
			frappe.PermissionError,
		)


def _require_profile(user):
	profile = get_profile(user)
	if not profile:
		frappe.throw(_("{0} is not a property user.").format(user))
	return profile


def _enforce_password_strength(new_password):
	from frappe.core.doctype.user.user import handle_password_test_fail, test_password_strength

	result = test_password_strength(new_password) or {}
	feedback = result.get("feedback")
	if feedback and not feedback.get("password_policy_validation_passed", False):
		handle_password_test_fail(feedback)


def _reject_reused_password(user, new_password):
	try:
		check_password(user, new_password, delete_tracker_cache=False)
	except frappe.AuthenticationError:
		return
	frappe.throw(_("The new password must be different from the current password."))


@frappe.whitelist(methods=["POST"])
def create_property_user(full_name, mobile_number, password, account_expiry, enabled=1):
	"""Create a Property User. The mobile number is the username. The password is not stored in a custom field."""
	_require_super_admin()
	ensure_roles()

	full_name = (full_name or "").strip()
	if not full_name:
		frappe.throw(_("Full Name is required"))

	mobile = normalize_mobile(mobile_number)
	if not password or len(password) < 8:
		frappe.throw(_("The initial password must be at least 8 characters."))

	expiry = getdate(account_expiry)
	email = synthetic_email(mobile)
	enabled_flag = 1 if cint(enabled) else 0

	existing_user = (
		frappe.db.get_value("User", email, "name")
		or frappe.db.get_value("User", {"username": mobile}, "name")
		or frappe.db.get_value("User", {"mobile_no": mobile}, "name")
	)
	if existing_user and frappe.db.exists("Property User Profile", {"user": existing_user}):
		frappe.throw(_("Mobile number {0} is already a username.").format(mobile))

	parts = full_name.split()
	if existing_user:
		user = frappe.get_doc("User", existing_user)
		user.first_name = parts[0]
		user.last_name = " ".join(parts[1:])
		user.username = mobile
		user.mobile_no = mobile
		user.enabled = enabled_flag
		user.user_type = "System User"
		if ROLE_PROPERTY_USER not in {row.role for row in user.roles}:
			user.append("roles", {"role": ROLE_PROPERTY_USER})
		user.new_password = password
		user.flags.ignore_password_policy = True
		user.save(ignore_permissions=True)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": parts[0],
				"last_name": " ".join(parts[1:]),
				"username": mobile,
				"mobile_no": mobile,
				"enabled": enabled_flag,
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": ROLE_PROPERTY_USER}],
			}
		)
		user.new_password = password
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)

	profile = frappe.get_doc(
		{
			"doctype": "Property User Profile",
			"user": user.name,
			"mobile_number": mobile,
			"account_expiry": expiry,
			"must_change_password": 1,
			"enabled": user.enabled,
		}
	).insert(ignore_permissions=True)

	return {
		"user": user.name,
		"username": mobile,
		"property_user_profile": profile.name,
		"account_expiry": str(expiry),
		"must_change_password": 1,
		"enabled": cint(user.enabled),
	}


@frappe.whitelist(methods=["POST"])
def reset_property_user_password(user, new_password):
	"""Set a new temporary password and force a change on the next login."""
	_require_super_admin()
	user = resolve_user(user)
	profile = _require_profile(user)
	if not new_password or len(new_password) < 8:
		frappe.throw(_("The new password must be at least 8 characters."))

	_reject_reused_password(user, new_password)
	update_password(user, new_password, logout_all_sessions=True)
	profile.must_change_password = 1
	profile.save(ignore_permissions=True)
	return {"user": user, "must_change_password": 1}


@frappe.whitelist(methods=["POST"])
def set_account_expiry(user, account_expiry):
	_require_super_admin()
	user = resolve_user(user)
	profile = _require_profile(user)
	if not account_expiry:
		frappe.throw(_("Account Expiry is required"))
	profile.account_expiry = getdate(account_expiry)
	profile.save(ignore_permissions=True)
	return {"user": user, "account_expiry": str(profile.account_expiry)}


@frappe.whitelist(methods=["POST"])
def set_user_active(user, active):
	_require_super_admin()
	user = resolve_user(user)
	profile = _require_profile(user)
	profile.enabled = 1 if cint(active) else 0
	profile.save(ignore_permissions=True)
	return {"user": user, "enabled": cint(profile.enabled)}


@frappe.whitelist(methods=["POST"])
def change_own_password(old_password, new_password):
	"""Replace the temporary password. Later changes go through the super admin."""
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		frappe.throw(_("Sign in with the property user account first."), frappe.PermissionError)

	profile = _require_profile(user)
	if not must_change_password(user):
		frappe.throw(
			_("This account cannot change its own password. Ask a Property Super Admin to reset it."),
			frappe.PermissionError,
		)
	if not old_password or not new_password:
		frappe.throw(_("Enter the current password and a new password."))

	try:
		check_password(user, old_password, delete_tracker_cache=False)
	except frappe.AuthenticationError:
		frappe.throw(_("The current password is incorrect."))
	if old_password == new_password:
		frappe.throw(_("The new password must be different from the current password."))
	_enforce_password_strength(new_password)
	update_password(user, new_password, logout_all_sessions=False)
	profile.must_change_password = 0
	profile.save(ignore_permissions=True)
	return {"user": user, "must_change_password": 0}
