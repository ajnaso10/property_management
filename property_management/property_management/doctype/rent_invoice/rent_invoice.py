import frappe
from frappe import _
from frappe.utils import flt, getdate

from property_management.finance import (
	allow_reversal_transaction_link,
	location_from_allocation,
	post_financial_transaction,
)
from property_management.hierarchy import OwnedDocument, copy_owner_from


class RentInvoice(OwnedDocument):
	def validate(self):
		if not self.bed_allocation:
			frappe.throw(_("Bed Allocation is required."))
		copy_owner_from(self, "Bed Allocation", self.bed_allocation)
		location = location_from_allocation(self.bed_allocation)
		if location.get("tenant") and self.tenant and self.tenant != location.tenant:
			frappe.throw(_("Tenant does not match the bed allocation."))
		if not self.tenant:
			self.tenant = location.get("tenant")
		for fieldname in ("building", "flat", "area", "bed"):
			self.set(fieldname, location.get(fieldname))
		if flt(self.rent_amount) <= 0:
			frappe.throw(_("Rent Amount must be greater than zero."))
		if self.billing_month and len(self.billing_month) != 7:
			frappe.throw(_("Billing Month must look like YYYY-MM."))
		self.billing_date = getdate(self.billing_date) if self.billing_date else None
		self.due_date = getdate(self.due_date) if self.due_date else None
		if self.billing_date and self.due_date and self.due_date < self.billing_date:
			frappe.throw(_("Due Date cannot be before Billing Date."))
		if self.name and not self.invoice_number:
			self.invoice_number = self.name
		if flt(self.amount_paid) < 0:
			frappe.throw(_("Amount Paid cannot be negative."))
		self.outstanding = flt(self.rent_amount) - flt(self.amount_paid)
		if self.outstanding < 0:
			frappe.throw(_("Amount Paid cannot exceed Rent Amount."))
		if self.docstatus == 0 and self.status != "Cancelled":
			self.status = "Draft"
		elif self.docstatus == 1:
			self.set_payment_status()

	def before_submit(self):
		self.amount_paid = flt(self.amount_paid)
		self.outstanding = flt(self.rent_amount) - flt(self.amount_paid)
		self.set_payment_status()
		if not self.invoice_number:
			self.invoice_number = self.name

	def on_submit(self):
		post_financial_transaction(
			transaction_type="Rent Generated",
			amount=self.rent_amount,
			owner_user=self.owner_user,
			posting_date=self.billing_date,
			tenant=self.tenant,
			building=self.building,
			flat=self.flat,
			area=self.area,
			bed=self.bed,
			reference_doctype=self.doctype,
			reference_name=self.name,
			remarks=_("Rent invoice {0}").format(self.name),
		)

	def before_cancel(self):
		if flt(self.amount_paid) > 0:
			frappe.throw(
				_("Cancel the rent payments first, or post a receivable adjustment. Outstanding is not written off.")
			)
		self.outstanding = 0
		self.status = "Cancelled"

	def on_cancel(self):
		allow_reversal_transaction_link(self)
		post_financial_transaction(
			transaction_type="Receivable Adjustment",
			amount=-flt(self.rent_amount),
			owner_user=self.owner_user,
			posting_date=self.billing_date,
			tenant=self.tenant,
			building=self.building,
			flat=self.flat,
			area=self.area,
			bed=self.bed,
			reference_doctype=self.doctype,
			reference_name=self.name,
			remarks=_("Reversal of rent invoice {0}. Not a vacate write-off.").format(self.name),
		)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(_("A submitted rent invoice cannot be deleted."))

	def set_payment_status(self):
		paid = flt(self.amount_paid)
		if self.outstanding == 0 and paid > 0:
			self.status = "Paid"
		elif paid > 0:
			self.status = "Partly Paid"
		else:
			self.status = "Unpaid"
