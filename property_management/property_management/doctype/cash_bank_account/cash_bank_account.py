import frappe
from frappe.model.document import Document

from property_management.hierarchy import OwnedDocument, apply_owner, assert_unique


class CashBankAccount(OwnedDocument):
	def validate(self):
		if not self.status:
			self.status = "Active"
		if self.account_type not in ("Cash", "Bank"):
			frappe.throw(frappe._("Account Type must be Cash or Bank."))
		apply_owner(self)
		assert_unique(
			"Cash Bank Account",
			"account_name",
			self.account_name,
			{"owner_user": self.owner_user},
			self.name,
		)
