import frappe
from frappe import _

from property_management.hierarchy import (
	OwnedDocument,
	assert_non_negative,
	assert_unique,
	copy_owner_from,
	refresh_counts_for_bed,
)


class Bed(OwnedDocument):
	def validate(self):
		if not self.status:
			self.status = "Active"
		if not self.occupancy_status:
			self.occupancy_status = "Vacant"
		copy_owner_from(self, "Area", self.area)
		parent = frappe.db.get_value("Area", self.area, ["flat", "building"], as_dict=True)
		self.flat = parent.flat
		self.building = parent.building
		assert_unique(
			"Bed",
			"bed_number",
			self.bed_number,
			{"area": self.area},
			self.name,
		)
		assert_non_negative(self, "monthly_rent")
		self._keep_occupancy_consistent()

	def on_update(self):
		refresh_counts_for_bed(self.name)

	def after_delete(self):
		from property_management.hierarchy import update_area_counts, update_flat_counts

		update_area_counts(self.area)
		update_flat_counts(self.flat)

	def _keep_occupancy_consistent(self):
		active = None
		if self.name and not self.is_new():
			active = frappe.db.get_value(
				"Bed Allocation",
				{"bed": self.name, "allocation_status": "Active"},
				["tenant", "monthly_rent"],
				as_dict=True,
			)
		if active:
			self.occupancy_status = "Occupied"
			self.current_tenant = active.tenant
			if active.monthly_rent is not None:
				self.monthly_rent = active.monthly_rent
			return

		if self.occupancy_status == "Occupied":
			frappe.throw(_("Allocate a tenant to mark this bed occupied."))
		if self.occupancy_status not in ("Vacant", "Maintenance"):
			self.occupancy_status = "Vacant"
		self.current_tenant = None
