import frappe
from frappe import _
from frappe.utils import flt, getdate

from property_management.finance import allow_reversal_transaction_link, post_financial_transaction
from property_management.hierarchy import OwnedDocument, copy_owner_from, require_readable

CATEGORIES = {
	"Maintenance",
	"Electricity",
	"Water",
	"Repairs",
	"Cleaning",
	"Internet",
	"Staff",
	"Other",
}


class PropertyExpense(OwnedDocument):
	def validate(self):
		if self.expense_category not in CATEGORIES:
			frappe.throw(_("Category is not valid."))
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero."))
		copy_owner_from(self, "Building", self.building)
		self._validate_location()
		if self.posting_date:
			self.posting_date = getdate(self.posting_date)
		if self.docstatus == 0 and self.status != "Cancelled":
			self.status = "Draft"

	def before_submit(self):
		self.status = "Submitted"

	def on_submit(self):
		self._post_transaction(self.amount, _("Expense {0}").format(self.name))

	def before_cancel(self):
		self.status = "Cancelled"

	def on_cancel(self):
		# Original Expense transaction stays submitted. This row is the audit reversal.
		# The source is already cancelled when this runs, so the reversal links to that history.
		allow_reversal_transaction_link(self)
		self._post_transaction(-flt(self.amount), _("Reversal of expense {0}").format(self.name))

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(_("A submitted expense cannot be deleted."))

	def _validate_location(self):
		if self.flat:
			require_readable("Flat", self.flat)
			building, owner = frappe.db.get_value("Flat", self.flat, ["building", "owner_user"])
			if building != self.building or owner != self.owner_user:
				frappe.throw(_("Flat {0} is not in this building.").format(self.flat))
		if self.area:
			require_readable("Area", self.area)
			flat, building, owner = frappe.db.get_value("Area", self.area, ["flat", "building", "owner_user"])
			if building != self.building or owner != self.owner_user:
				frappe.throw(_("Area {0} is not in this building.").format(self.area))
			if self.flat and flat != self.flat:
				frappe.throw(_("Area {0} is not in flat {1}.").format(self.area, self.flat))

	def _post_transaction(self, amount, remarks):
		post_financial_transaction(
			transaction_type="Expense",
			amount=amount,
			owner_user=self.owner_user,
			posting_date=self.posting_date,
			building=self.building,
			flat=self.flat,
			area=self.area,
			reference_doctype=self.doctype,
			reference_name=self.name,
			remarks=remarks,
		)
