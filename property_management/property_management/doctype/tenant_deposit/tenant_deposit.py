import frappe
from frappe import _

from property_management.finance import location_from_allocation
from property_management.hierarchy import OwnedDocument, copy_owner_from


class TenantDeposit(OwnedDocument):
	def validate(self):
		if self.bed_allocation:
			copy_owner_from(self, "Bed Allocation", self.bed_allocation)
			location = location_from_allocation(self.bed_allocation)
			if self.tenant and location.get("tenant") and self.tenant != location.tenant:
				frappe.throw(_("Tenant does not match the bed allocation."))
			self.tenant = location.get("tenant") or self.tenant
			for fieldname in ("building", "flat", "area", "bed"):
				self.set(fieldname, location.get(fieldname))
		else:
			copy_owner_from(self, "Tenant", self.tenant)
		if not self.status:
			self.status = "Active"

	def on_trash(self):
		if frappe.db.exists("Deposit Transaction", {"tenant_deposit": self.name, "docstatus": 1}):
			frappe.throw(_("This deposit has transactions and cannot be deleted."))
