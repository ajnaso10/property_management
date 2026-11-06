import frappe
from frappe import _
from frappe.utils import flt, getdate

from property_management.finance import (
	post_financial_transaction,
	recompute_deposit_balance,
	submitted_deposit_balance,
)
from property_management.hierarchy import OwnedDocument, copy_owner_from, require_readable

FT_TYPE = {
	"Receipt": "Deposit Received",
	"Refund": "Deposit Refunded",
	"Transfer to Revenue": "Deposit Transferred to Revenue",
}


class DepositTransaction(OwnedDocument):
	def validate(self):
		if self.transaction_type not in FT_TYPE:
			frappe.throw(_("Type must be Receipt, Refund, or Transfer to Revenue."))
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero."))
		copy_owner_from(self, "Tenant Deposit", self.tenant_deposit)
		if self.posting_date:
			self.posting_date = getdate(self.posting_date)
		self._require_cash_account()
		if self.docstatus == 0:
			self._check_balance()

	def before_submit(self):
		self._check_balance()

	def on_submit(self):
		deposit = frappe.db.get_value(
			"Tenant Deposit",
			self.tenant_deposit,
			["tenant", "building", "flat", "area", "bed"],
			as_dict=True,
		)
		# Receipt is not rent. Only a transfer becomes revenue.
		post_financial_transaction(
			transaction_type=FT_TYPE[self.transaction_type],
			amount=self.amount,
			owner_user=self.owner_user,
			posting_date=self.posting_date,
			tenant=deposit.tenant,
			building=deposit.building,
			flat=deposit.flat,
			area=deposit.area,
			bed=deposit.bed,
			reference_doctype=self.doctype,
			reference_name=self.name,
			payment_mode=self.payment_mode,
			payment_reference=self.payment_reference,
			cash_bank_account=self.cash_bank_account,
			remarks=self.remarks or f"{self.transaction_type} on {self.tenant_deposit}",
		)
		recompute_deposit_balance(self.tenant_deposit)

	def before_cancel(self):
		frappe.throw(_("Deposit transactions stay on record. Post a refund or transfer instead."))

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(_("A submitted deposit transaction cannot be deleted."))

	def _check_balance(self):
		if self.transaction_type == "Receipt":
			return
		balance = submitted_deposit_balance(self.tenant_deposit, exclude_name=self.name)
		if flt(self.amount) > balance:
			frappe.throw(
				_("Cannot {0} {1}. Remaining deposit is {2}.").format(
					self.transaction_type.lower(), self.amount, balance
				)
			)

	def _require_cash_account(self):
		if self.transaction_type == "Transfer to Revenue":
			return
		if not self.cash_bank_account:
			frappe.throw(_("Cash/Bank Account is required for a deposit receipt or refund."))
		require_readable("Cash Bank Account", self.cash_bank_account)
		owner = frappe.db.get_value("Cash Bank Account", self.cash_bank_account, "owner_user")
		if owner != self.owner_user:
			frappe.throw(_("That cash or bank account belongs to another user."), frappe.PermissionError)
