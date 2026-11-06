import frappe
from frappe.model.document import Document

from property_management.hierarchy import (
	assert_unique,
	copy_owner_from,
	update_area_counts,
	update_flat_counts,
)


class Area(Document):
	def validate(self):
		if not self.status:
			self.status = "Active"
		copy_owner_from(self, "Flat", self.flat)
		self.building = frappe.db.get_value("Flat", self.flat, "building")
		assert_unique(
			"Area",
			"area_code",
			self.area_code,
			{"flat": self.flat},
			self.name,
		)

	def on_update(self):
		update_area_counts(self.name)
		update_flat_counts(self.flat)

	def after_delete(self):
		update_flat_counts(self.flat)
