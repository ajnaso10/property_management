import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from property_management.hierarchy import OwnedDocument, apply_owner

TRANSACTION_TYPES = {
	"Rent Generated",
	"Rent Received",
	"Deposit Received",
	"Deposit Refunded",
	"Deposit Transferred to Revenue",
	"Other Revenue",
	"Expense",
	"Receivable Adjustment",
	"Payment Reversal",
}


class FinancialTransaction(OwnedDocument):
	def validate(self):
		apply_owner(self)
		if self.transaction_type not in TRANSACTION_TYPES:
			frappe.throw(_("Transaction Type is not valid."))
		if flt(self.amount) == 0:
			frappe.throw(_("Amount cannot be zero."))
		if self.posting_date:
			self.posting_date = getdate(self.posting_date)
		if self.name and not self.transaction_number:
			self.transaction_number = self.name
		if self.docstatus == 0:
			self.status = "Draft"
		self._validate_reference_owner()
		self._reject_edits_after_submit()

	def get_invalid_links(self, *args, **kwargs):
		"""Keep every link check, except the cancelled-document ban on the audit reference.

		A reversal is posted from on_cancel, after Frappe has already saved the source
		as cancelled. `reference_name` is the history pointer to that source. Other
		links, including a missing reference, are still rejected.
		"""
		invalid_links, cancelled_links = super().get_invalid_links(*args, **kwargs)
		cancelled_links = [link for link in cancelled_links if link[0] != "reference_name"]
		return invalid_links, cancelled_links

	def _validate_reference_owner(self):
		if not self.reference_doctype or not self.reference_name:
			return
		if not frappe.db.exists(self.reference_doctype, self.reference_name):
			frappe.throw(
				_("Reference {0} {1} was not found.").format(self.reference_doctype, self.reference_name)
			)
		if not frappe.get_meta(self.reference_doctype).has_field("owner_user"):
			return
		referenced_owner = frappe.db.get_value(self.reference_doctype, self.reference_name, "owner_user")
		if referenced_owner and referenced_owner != self.owner_user:
			frappe.throw(
				_("Reference {0} {1} belongs to another user.").format(self.reference_doctype, self.reference_name),
				frappe.PermissionError,
			)

	def before_submit(self):
		self.status = "Submitted"
		if not self.transaction_number:
			self.transaction_number = self.name

	def before_cancel(self):
		frappe.throw(
			_("Submitted financial transactions stay on record. Post a reversal transaction instead.")
		)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(_("A submitted financial transaction cannot be deleted."))

	def _reject_edits_after_submit(self):
		# Submit itself runs validate after docstatus is set to 1 in memory.
		# Block only when the database row is already submitted.
		if self.is_new() or not self.name or self.flags.ignore_validate_update_after_submit:
			return
		previous = frappe.db.get_value(self.doctype, self.name, "docstatus")
		if cint(previous) == 1:
			frappe.throw(_("Submitted financial transactions cannot be edited. Post a reversal instead."))
