import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def leave_receivables_unchanged(bed_allocation):
	"""Vacate must not write off rent invoices or financial transactions.

	TODO Phase 5: billing may stop future rent because Generate Rent is off.
	Outstanding invoices stay until a payment or an explicit receivable adjustment.
	"""
	return bed_allocation


def post_financial_transaction(
	*,
	transaction_type,
	amount,
	owner_user,
	posting_date=None,
	tenant=None,
	building=None,
	flat=None,
	area=None,
	bed=None,
	reference_doctype=None,
	reference_name=None,
	payment_mode=None,
	payment_reference=None,
	cash_bank_account=None,
	remarks=None,
):
	"""Insert an immutable Financial Transaction and submit it.

	Callers own the business rule. This helper does not edit an existing transaction.
	"""
	if not transaction_type:
		frappe.throw(_("Transaction Type is required."))
	if not owner_user:
		frappe.throw(_("Owner User is required."))
	if flt(amount) == 0:
		frappe.throw(_("Amount cannot be zero."))

	doc = frappe.new_doc("Financial Transaction")
	doc.posting_date = getdate(posting_date) if posting_date else today()
	doc.transaction_type = transaction_type
	doc.amount = flt(amount)
	doc.owner_user = owner_user
	doc.tenant = tenant
	doc.building = building
	doc.flat = flat
	doc.area = area
	doc.bed = bed
	doc.reference_doctype = reference_doctype
	doc.reference_name = reference_name
	doc.payment_mode = payment_mode
	doc.payment_reference = payment_reference
	doc.cash_bank_account = cash_bank_account
	doc.remarks = remarks
	doc.status = "Draft"
	doc.insert()
	doc.submit()
	return doc.name


def recompute_deposit_balance(tenant_deposit):
	if not tenant_deposit or not frappe.db.exists("Tenant Deposit", tenant_deposit):
		return
	rows = frappe.get_all(
		"Deposit Transaction",
		filters={"tenant_deposit": tenant_deposit, "docstatus": 1},
		fields=["transaction_type", "amount"],
	)
	received = refunded = transferred = 0.0
	for row in rows:
		amount = flt(row.amount)
		if row.transaction_type == "Receipt":
			received += amount
		elif row.transaction_type == "Refund":
			refunded += amount
		elif row.transaction_type == "Transfer to Revenue":
			transferred += amount
	balance = flt(received - refunded - transferred)
	frappe.db.set_value(
		"Tenant Deposit",
		tenant_deposit,
		{
			"total_received": received,
			"total_refunded": refunded,
			"total_transferred": transferred,
			"balance": balance,
			"status": "Closed" if balance == 0 and received else "Active",
		},
		update_modified=False,
	)


def submitted_deposit_balance(tenant_deposit, exclude_name=None):
	rows = frappe.get_all(
		"Deposit Transaction",
		filters={"tenant_deposit": tenant_deposit, "docstatus": 1},
		fields=["name", "transaction_type", "amount"],
	)
	balance = 0.0
	for row in rows:
		if exclude_name and row.name == exclude_name:
			continue
		amount = flt(row.amount)
		if row.transaction_type == "Receipt":
			balance += amount
		elif row.transaction_type in ("Refund", "Transfer to Revenue"):
			balance -= amount
	return flt(balance)


def apply_invoice_allocation(rent_invoice, allocated_amount):
	"""Move paid and outstanding. Does not create the Financial Transaction."""
	invoice = frappe.get_doc("Rent Invoice", rent_invoice)
	if invoice.docstatus != 1:
		frappe.throw(_("Rent Invoice {0} is not submitted.").format(rent_invoice))
	invoice.amount_paid = flt(invoice.amount_paid) + flt(allocated_amount)
	if flt(invoice.amount_paid) < 0:
		frappe.throw(_("Amount Paid on {0} cannot be negative.").format(rent_invoice))
	if flt(invoice.amount_paid) > flt(invoice.rent_amount):
		frappe.throw(_("Payment exceeds the rent on {0}.").format(rent_invoice))
	invoice.outstanding = flt(invoice.rent_amount) - flt(invoice.amount_paid)
	invoice.set_payment_status()
	invoice.flags.ignore_validate_update_after_submit = True
	invoice.save()
	return invoice


def location_from_allocation(bed_allocation):
	if not bed_allocation:
		return {}
	return frappe.db.get_value(
		"Bed Allocation",
		bed_allocation,
		["tenant", "building", "flat", "area", "bed", "owner_user"],
		as_dict=True,
	) or {}
