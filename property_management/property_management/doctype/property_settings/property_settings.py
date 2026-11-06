import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class PropertySettings(Document):
	def validate(self):
		if self.billing_day is None or self.billing_day == "":
			day = 1
		else:
			day = cint(self.billing_day)
		if day < 1 or day > 31:
			frappe.throw(_("Billing Day must be between 1 and 31. Shorter months use the last day."))
		self.billing_day = day
		due = cint(self.due_days_after_billing)
		if self.due_days_after_billing is None or self.due_days_after_billing == "":
			due = 7
		if due < 0 or due > 365:
			frappe.throw(_("Due Days After Billing must be between 0 and 365."))
		self.due_days_after_billing = due
