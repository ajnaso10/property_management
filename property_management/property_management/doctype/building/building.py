from property_management.hierarchy import (
	OwnedDocument,
	apply_owner,
	assert_unique,
	prevent_delete_with_allocation_history,
)


class Building(OwnedDocument):
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

	def on_trash(self):
		prevent_delete_with_allocation_history(self)
