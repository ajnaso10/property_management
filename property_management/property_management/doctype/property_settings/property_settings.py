import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class PropertySettings(Document):
	def validate(self):
		day = cint(self.billing_day) or 1
		if day < 1 or day > 28:
			frappe.throw(_("Billing Day must be between 1 and 28 so it exists in every month."))
		self.billing_day = day
