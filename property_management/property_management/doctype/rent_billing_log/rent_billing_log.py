from property_management.hierarchy import OwnedDocument, apply_owner


class RentBillingLog(OwnedDocument):
	def validate(self):
		apply_owner(self)
		if self.outcome not in ("Success", "Skipped", "Failed"):
			from frappe import _

			frappe.throw(_("Outcome must be Success, Skipped, or Failed."))
