from property_management.hierarchy import OwnedDocument, assert_unique, copy_owner_from, update_flat_counts


class Flat(OwnedDocument):
	def validate(self):
		if not self.status:
			self.status = "Active"
		copy_owner_from(self, "Building", self.building)
		assert_unique(
			"Flat",
			"flat_number",
			self.flat_number,
			{"building": self.building},
			self.name,
		)

	def on_update(self):
		update_flat_counts(self.name)
