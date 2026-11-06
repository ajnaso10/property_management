import frappe
from frappe import _
from frappe.utils import flt, getdate

from property_management.finance import location_from_allocation
from property_management.hierarchy import OwnedDocument, copy_owner_from


class MonthlyRevenue(OwnedDocument):
	def validate(self):
		if self.frequency != "Monthly":
			frappe.throw(_("Frequency must be Monthly."))
		copy_owner_from(self, "Bed Allocation", self.bed_allocation)
		location = location_from_allocation(self.bed_allocation)
		for fieldname in ("tenant", "building", "flat", "area", "bed"):
			self.set(fieldname, location.get(fieldname))
		if not self.revisions:
			frappe.throw(_("Add at least one rent revision."))
		seen = set()
		latest = None
		for row in self.revisions:
			if flt(row.monthly_rent) < 0:
				frappe.throw(_("Monthly rent cannot be negative."))
			effective = getdate(row.effective_from)
			if effective in seen:
				frappe.throw(_("Only one rent revision can start on {0}.").format(effective))
			seen.add(effective)
			if latest is None or effective >= latest[0]:
				latest = (effective, flt(row.monthly_rent))
		self.monthly_rent = latest[1] if latest else 0
		if self.start_date:
			self.start_date = getdate(self.start_date)
		if self.end_date:
			self.end_date = getdate(self.end_date)
			if self.start_date and self.end_date < self.start_date:
				frappe.throw(_("End Date cannot be before Start Date."))
		if self.status not in ("Active", "Stopped"):
			frappe.throw(_("Status must be Active or Stopped."))

	def on_trash(self):
		if frappe.db.exists("Rent Invoice", {"bed_allocation": self.bed_allocation, "docstatus": ["!=", 2]}):
			frappe.throw(_("Rent invoices already exist for this schedule and cannot be removed by deleting it."))
