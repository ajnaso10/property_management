import frappe

from property_management.hierarchy import (
	OwnedDocument,
	assert_unique,
	copy_owner_from,
	prevent_delete_with_allocation_history,
	update_area_counts,
	update_flat_counts,
)


class Area(OwnedDocument):
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

	def on_trash(self):
		prevent_delete_with_allocation_history(self)

	def after_delete(self):
		update_flat_counts(self.flat)
