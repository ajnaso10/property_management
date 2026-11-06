import frappe
from frappe.model.document import Document

from property_management.auth import normalize_mobile
from property_management.hierarchy import apply_owner, assert_unique


class Tenant(Document):
	def validate(self):
		if not self.status:
			self.status = "Active"
		apply_owner(self)
		self.mobile = normalize_mobile(self.mobile)
		assert_unique(
			"Tenant",
			"mobile",
			self.mobile,
			{"owner_user": self.owner_user},
			self.name,
		)
