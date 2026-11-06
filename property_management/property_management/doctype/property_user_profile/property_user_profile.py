import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

from property_management.auth import normalize_mobile


class PropertyUserProfile(Document):
	def validate(self):
		if not self.user:
			frappe.throw(_("User is required"))
		self.mobile_number = normalize_mobile(self.mobile_number)
		if not self.account_expiry:
			frappe.throw(_("Account Expiry is required"))
		self.account_expiry = getdate(self.account_expiry)
		self.enabled = 1 if cint(self.enabled) else 0

		existing = frappe.db.get_value(
			"Property User Profile", {"mobile_number": self.mobile_number, "name": ["!=", self.name]}, "name"
		)
		if existing:
			frappe.throw(_("Mobile number {0} is already used.").format(self.mobile_number))
		taken = frappe.db.get_value(
			"User", {"username": self.mobile_number, "name": ["!=", self.user]}, "name"
		)
		if taken:
			frappe.throw(_("Mobile number {0} is already a username.").format(self.mobile_number))

	def on_update(self):
		if not self.user or not frappe.db.exists("User", self.user):
			return
		enabled = 1 if cint(self.enabled) else 0
		was_enabled = cint(frappe.db.get_value("User", self.user, "enabled"))
		frappe.db.set_value(
			"User",
			self.user,
			{"username": self.mobile_number, "mobile_no": self.mobile_number, "enabled": enabled},
			update_modified=False,
		)
		if was_enabled and not enabled and not frappe.in_test:
			from frappe.sessions import clear_sessions

			clear_sessions(self.user, force=True)

	@frappe.whitelist(methods=["POST"])
	def reset_password(self, new_password):
		from property_management.api import reset_property_user_password

		return reset_property_user_password(self.user, new_password)

	@frappe.whitelist(methods=["POST"])
	def set_expiry(self, account_expiry):
		from property_management.api import set_account_expiry

		return set_account_expiry(self.user, account_expiry)

	@frappe.whitelist(methods=["POST"])
	def set_active(self, active):
		from property_management.api import set_user_active

		return set_user_active(self.user, active)
