import frappe
from frappe.model.document import Document

from property_management.hierarchy import apply_owner, assert_unique


class Building(Document):
	def validate(self):
		if not self.status:
			self.status = "Active"
		apply_owner(self)
		assert_unique(
			"Building",
			"building_code",
			self.building_code,
			{"owner_user": self.owner_user},
			self.name,
		)
