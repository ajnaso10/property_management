import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import flt, today

from property_management.testing import (
	make_allocation,
	make_bed_stack,
	make_property_user,
	make_tenant,
	unique_digits,
)

test_records = []


class TestFinancialTransaction(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.owner = make_property_user("Finance Landlord")
		frappe.set_user(self.owner["user"])
		self.building, self.flat, self.area, self.bed = make_bed_stack(unique_digits(6))
		self.tenant = make_tenant("Paying Tenant")
		self.allocation = make_allocation(self.bed.name, self.tenant.name, monthly_rent=1000, deposit_amount=0)
		self.cash = frappe.get_doc(
			{
				"doctype": "Cash Bank Account",
				"account_name": f"Cash {unique_digits(4)}",
				"account_type": "Cash",
				"status": "Active",
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def make_invoice(self, rent=1000, month="2026-11"):
		invoice = frappe.get_doc(
			{
				"doctype": "Rent Invoice",
				"tenant": self.tenant.name,
				"bed_allocation": self.allocation.name,
				"billing_month": month,
				"billing_date": "2026-11-01",
				"due_date": "2026-11-10",
				"rent_amount": rent,
			}
		).insert()
		invoice.submit()
		return invoice

	def make_payment(self, amount, allocations):
		return frappe.get_doc(
			{
				"doctype": "Rent Payment",
				"tenant": self.tenant.name,
				"posting_date": "2026-11-06",
				"amount": amount,
				"payment_mode": "Cash",
				"cash_bank_account": self.cash.name,
				"allocations": [
					{"rent_invoice": invoice, "allocated_amount": allocated}
					for invoice, allocated in allocations
				],
			}
		)

	def test_invoice_and_payment_post_transactions_without_over_allocation(self):
		invoice = self.make_invoice(1000)
		generated = frappe.get_all(
			"Financial Transaction",
			filters={"reference_name": invoice.name, "transaction_type": "Rent Generated", "docstatus": 1},
			fields=["amount"],
		)
		self.assertEqual(len(generated), 1)
		self.assertEqual(flt(generated[0].amount), 1000)

		partial = self.make_payment(400, [(invoice.name, 400)])
		partial.insert()
		partial.submit()
		invoice.reload()
		self.assertEqual(flt(invoice.amount_paid), 400)
		self.assertEqual(flt(invoice.outstanding), 600)
		self.assertEqual(invoice.status, "Partly Paid")
		received = frappe.get_all(
			"Financial Transaction",
			filters={"reference_name": partial.name, "transaction_type": "Rent Received", "docstatus": 1},
		)
		self.assertEqual(len(received), 1)

		over_invoice = self.make_payment(700, [(invoice.name, 700)])
		with self.assertRaises(frappe.ValidationError):
			over_invoice.insert()

		short = self.make_payment(600, [(invoice.name, 500)])
		with self.assertRaises(frappe.ValidationError):
			short.insert()

		rest = self.make_payment(600, [(invoice.name, 600)])
		rest.insert()
		rest.submit()
		invoice.reload()
		self.assertEqual(flt(invoice.outstanding), 0)
		self.assertEqual(invoice.status, "Paid")

		extra = self.make_payment(1, [(invoice.name, 1)])
		with self.assertRaises(frappe.ValidationError):
			extra.insert()

	def _stay_state(self):
		self.allocation.reload()
		self.bed.reload()
		schedule = frappe.db.get_value(
			"Monthly Revenue",
			{"bed_allocation": self.allocation.name},
			["status", "end_date"],
			as_dict=True,
		)
		return {
			"allocation_status": self.allocation.allocation_status,
			"vacating_date": str(self.allocation.vacating_date or ""),
			"generate_rent": int(self.allocation.generate_rent or 0),
			"bed": self.bed.occupancy_status,
			"current_tenant": self.bed.current_tenant,
			"schedule_status": schedule.status if schedule else None,
			"schedule_end": str(schedule.end_date or "") if schedule else "",
		}

	def test_unpaid_rent_on_this_stay_blocks_vacate_without_side_effects(self):
		invoice = self.make_invoice(1000)
		earlier = self.make_invoice(250, month="2026-10")
		before = self._stay_state()
		self.assertEqual(before["allocation_status"], "Active")
		self.assertEqual(before["bed"], "Occupied")
		self.assertEqual(before["schedule_status"], "Active")

		for attempt in (
			lambda: self.allocation.vacate(vacating_date=today()),
			lambda: self._save_as_vacated(),
		):
			with self.assertRaises(frappe.ValidationError) as refused:
				attempt()
			self.assertIn(invoice.name, str(refused.exception))
			self.assertIn(earlier.name, str(refused.exception))
			self.assertEqual(self._stay_state(), before)
			invoice.reload()
			earlier.reload()
			self.assertEqual(flt(invoice.outstanding), 1000)
			self.assertEqual(flt(earlier.outstanding), 250)
			self.assertEqual(invoice.docstatus, 1)
			self.assertEqual(earlier.docstatus, 1)

		other_bed = frappe.get_doc(
			{
				"doctype": "Bed",
				"bed_number": "Other Stay",
				"area": self.area.name,
				"status": "Active",
				"occupancy_status": "Vacant",
			}
		).insert()
		other_stay = make_allocation(
			other_bed.name, make_tenant("Separate Stay").name, monthly_rent=700, deposit_amount=0
		)
		other_stay.vacate(vacating_date=today())
		other_stay.reload()
		self.assertEqual(other_stay.allocation_status, "Vacated")
		self.assertEqual(self._stay_state(), before)
		invoice.reload()
		self.assertEqual(flt(invoice.outstanding), 1000)

		partial = self.make_payment(400, [(invoice.name, 400)])
		partial.insert()
		partial.submit()
		with self.assertRaises(frappe.ValidationError):
			self.allocation.vacate(vacating_date=today())
		self.assertEqual(self._stay_state(), before)
		invoice.reload()
		self.assertEqual(flt(invoice.outstanding), 600)
		self.assertEqual(invoice.status, "Partly Paid")

		deposit = frappe.get_doc(
			{
				"doctype": "Tenant Deposit",
				"tenant": self.tenant.name,
				"bed_allocation": self.allocation.name,
			}
		).insert()
		receipt = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Receipt",
				"posting_date": "2026-11-06",
				"amount": 1000,
				"payment_mode": "Cash",
				"cash_bank_account": self.cash.name,
			}
		).insert()
		receipt.submit()
		with self.assertRaises(frappe.ValidationError):
			self.allocation.vacate(vacating_date=today())
		deposit.reload()
		self.assertEqual(flt(deposit.balance), 1000)
		self.assertEqual(self._stay_state(), before)

	def _save_as_vacated(self):
		self.allocation.reload()
		self.allocation.allocation_status = "Vacated"
		self.allocation.vacating_date = today()
		self.allocation.save()

	def test_settled_rent_allows_vacate_and_keeps_the_audit(self):
		fresh_bed = frappe.get_doc(
			{
				"doctype": "Bed",
				"bed_number": "No Invoice",
				"area": self.area.name,
				"status": "Active",
				"occupancy_status": "Vacant",
			}
		).insert()
		fresh = make_allocation(
			fresh_bed.name, make_tenant("Zero Rent Tenant").name, monthly_rent=1000, deposit_amount=0
		)
		fresh.vacate(vacating_date=today())
		fresh.reload()
		fresh_bed.reload()
		self.assertEqual(fresh.allocation_status, "Vacated")
		self.assertEqual(fresh_bed.occupancy_status, "Vacant")

		invoice = self.make_invoice(1000)
		rest = self.make_payment(1000, [(invoice.name, 1000)])
		rest.insert()
		rest.submit()
		invoice.reload()
		self.assertEqual(flt(invoice.outstanding), 0)
		self.allocation.vacate(vacating_date=today())
		self.allocation.reload()
		invoice.reload()
		self.bed.reload()
		self.assertEqual(self.allocation.allocation_status, "Vacated")
		self.assertEqual(self.bed.occupancy_status, "Vacant")
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.status, "Paid")
		self.assertEqual(flt(invoice.outstanding), 0)
		self.assertEqual(
			frappe.db.get_value(
				"Monthly Revenue", {"bed_allocation": self.allocation.name}, "status"
			),
			"Stopped",
		)
		self.assertTrue(
			frappe.db.exists(
				"Financial Transaction",
				{"reference_name": invoice.name, "transaction_type": "Rent Generated", "docstatus": 1},
			)
		)

	def test_reversal_and_cancellation_change_whether_vacate_is_allowed(self):
		invoice = self.make_invoice(1000)
		payment = self.make_payment(1000, [(invoice.name, 1000)])
		payment.insert()
		payment.submit()
		payment.cancel()
		invoice.reload()
		self.assertEqual(flt(invoice.outstanding), 1000)
		self.assertEqual(invoice.status, "Unpaid")
		before = self._stay_state()
		with self.assertRaises(frappe.ValidationError):
			self.allocation.vacate(vacating_date=today())
		self.assertEqual(self._stay_state(), before)

		invoice.cancel()
		invoice.reload()
		self.assertEqual(invoice.docstatus, 2)
		self.assertEqual(flt(invoice.outstanding), 0)
		self.allocation.vacate(vacating_date=today())
		self.allocation.reload()
		invoice.reload()
		self.assertEqual(self.allocation.allocation_status, "Vacated")
		self.assertEqual(invoice.docstatus, 2)
		self.assertTrue(
			frappe.db.exists(
				"Financial Transaction",
				{
					"reference_name": invoice.name,
					"transaction_type": "Receivable Adjustment",
					"docstatus": 1,
				},
			)
		)

	def test_draft_does_not_block_vacate_and_another_stay_is_separate(self):
		draft = frappe.get_doc(
			{
				"doctype": "Rent Invoice",
				"tenant": self.tenant.name,
				"bed_allocation": self.allocation.name,
				"billing_month": "2026-11",
				"billing_date": "2026-11-01",
				"due_date": "2026-11-10",
				"rent_amount": 1000,
			}
		).insert()
		self.assertEqual(draft.docstatus, 0)
		self.allocation.vacate(vacating_date=today())
		draft.reload()
		self.allocation.reload()
		self.assertEqual(draft.docstatus, 0)
		self.assertEqual(flt(draft.outstanding), 1000)
		self.assertEqual(self.allocation.allocation_status, "Vacated")

		other_bed = frappe.get_doc(
			{
				"doctype": "Bed",
				"bed_number": "Vacate Scope",
				"area": self.area.name,
				"status": "Active",
				"occupancy_status": "Vacant",
			}
		).insert()
		other_tenant = make_tenant("Other Stay Tenant")
		other_stay = make_allocation(other_bed.name, other_tenant.name, monthly_rent=800, deposit_amount=0)
		other_stay.vacate(vacating_date=today())
		other_stay.reload()
		draft.reload()
		self.assertEqual(other_stay.allocation_status, "Vacated")
		self.assertEqual(draft.docstatus, 0)
		self.assertEqual(flt(draft.outstanding), 1000)

	def test_another_owners_unpaid_rent_does_not_affect_this_vacate(self):
		invoice = self.make_invoice(1000)
		frappe.set_user("Administrator")
		other = make_property_user("Other Finance Landlord")
		frappe.set_user(other["user"])
		_building, _flat, _area, bed = make_bed_stack(unique_digits(6))
		tenant = make_tenant("Other Finance Tenant")
		allocation = make_allocation(bed.name, tenant.name, monthly_rent=500, deposit_amount=0)
		allocation.vacate(vacating_date=today())
		allocation.reload()
		self.assertEqual(allocation.allocation_status, "Vacated")
		frappe.set_user(self.owner["user"])
		invoice.reload()
		self.allocation.reload()
		self.assertEqual(flt(invoice.outstanding), 1000)
		self.assertEqual(self.allocation.allocation_status, "Active")

	def test_deposit_balance_rules(self):
		deposit = frappe.get_doc(
			{
				"doctype": "Tenant Deposit",
				"tenant": self.tenant.name,
				"bed_allocation": self.allocation.name,
			}
		).insert()
		receipt = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Receipt",
				"posting_date": "2026-11-01",
				"amount": 1000,
				"payment_mode": "Cash",
				"cash_bank_account": self.cash.name,
			}
		).insert()
		receipt.submit()
		deposit.reload()
		self.assertEqual(flt(deposit.balance), 1000)
		receipt_types = frappe.get_all(
			"Financial Transaction",
			filters={"reference_name": receipt.name, "docstatus": 1},
			pluck="transaction_type",
		)
		self.assertEqual(receipt_types, ["Deposit Received"])

		too_much = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Refund",
				"posting_date": "2026-11-02",
				"amount": 1001,
				"payment_mode": "Cash",
				"cash_bank_account": self.cash.name,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			too_much.insert()

		refund = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Refund",
				"posting_date": "2026-11-02",
				"amount": 400,
				"payment_mode": "Cash",
				"cash_bank_account": self.cash.name,
			}
		).insert()
		refund.submit()
		deposit.reload()
		self.assertEqual(flt(deposit.balance), 600)

		over_transfer = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Transfer to Revenue",
				"posting_date": "2026-11-03",
				"amount": 700,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			over_transfer.insert()

		transfer = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Transfer to Revenue",
				"posting_date": "2026-11-03",
				"amount": 600,
			}
		).insert()
		transfer.submit()
		deposit.reload()
		self.assertEqual(flt(deposit.balance), 0)
		self.assertEqual(deposit.status, "Closed")
		self.assertEqual(
			frappe.db.get_value(
				"Financial Transaction",
				{"reference_name": transfer.name, "docstatus": 1},
				"transaction_type",
			),
			"Deposit Transferred to Revenue",
		)

	def test_expense_posts_and_reverses_without_editing_the_original(self):
		expense = frappe.get_doc(
			{
				"doctype": "Property Expense",
				"posting_date": "2026-11-04",
				"expense_category": "Repairs",
				"amount": 250,
				"building": self.building.name,
				"flat": self.flat.name,
				"remarks": "Door lock",
			}
		).insert()
		expense.submit()
		original = frappe.db.get_value(
			"Financial Transaction",
			{"reference_name": expense.name, "transaction_type": "Expense", "docstatus": 1},
			["name", "amount"],
			as_dict=True,
		)
		expense.cancel()
		rows = frappe.get_all(
			"Financial Transaction",
			filters={"reference_name": expense.name, "reference_doctype": "Property Expense", "docstatus": 1},
			fields=["name", "amount", "transaction_type", "reference_name"],
			order_by="amount desc",
		)
		self.assertEqual(len(rows), 2)
		self.assertEqual({row.transaction_type for row in rows}, {"Expense"})
		self.assertEqual(flt(rows[0].amount), 250)
		self.assertEqual(rows[0].name, original.name)
		self.assertEqual(flt(rows[1].amount), -250)
		self.assertTrue(all(row.reference_name == expense.name for row in rows))
		expense.reload()
		self.assertEqual(expense.docstatus, 2)
		self.assertEqual(expense.status, "Cancelled")

	def test_invoice_and_payment_cancel_keep_reversal_links(self):
		invoice = self.make_invoice(1000)
		generated = frappe.db.get_value(
			"Financial Transaction",
			{"reference_name": invoice.name, "transaction_type": "Rent Generated", "docstatus": 1},
			"name",
		)
		payment = self.make_payment(400, [(invoice.name, 400)])
		payment.insert()
		payment.submit()
		received = frappe.db.get_value(
			"Financial Transaction",
			{"reference_name": payment.name, "transaction_type": "Rent Received", "docstatus": 1},
			"name",
		)
		payment.cancel()
		invoice.reload()
		self.assertEqual(flt(invoice.outstanding), 1000)
		self.assertEqual(invoice.status, "Unpaid")
		self.assertEqual(payment.docstatus, 2)
		self.assertEqual(
			frappe.db.get_value("Financial Transaction", received, "docstatus"),
			1,
		)
		reversal = frappe.db.get_value(
			"Financial Transaction",
			{"reference_name": payment.name, "transaction_type": "Payment Reversal", "docstatus": 1},
			["name", "amount"],
			as_dict=True,
		)
		self.assertEqual(flt(reversal.amount), -400)

		invoice.cancel()
		self.assertEqual(
			frappe.db.get_value("Financial Transaction", generated, "docstatus"),
			1,
		)
		adjustment = frappe.db.get_value(
			"Financial Transaction",
			{"reference_name": invoice.name, "transaction_type": "Receivable Adjustment", "docstatus": 1},
			["amount", "reference_doctype"],
			as_dict=True,
		)
		self.assertEqual(adjustment.reference_doctype, "Rent Invoice")
		self.assertEqual(flt(adjustment.amount), -1000)
		invoice.reload()
		self.assertEqual(invoice.docstatus, 2)
		self.assertEqual(flt(invoice.outstanding), 0)

	def test_reversal_cannot_reference_another_users_expense(self):
		expense = frappe.get_doc(
			{
				"doctype": "Property Expense",
				"posting_date": "2026-11-04",
				"expense_category": "Cleaning",
				"amount": 80,
				"building": self.building.name,
			}
		).insert()
		expense.submit()
		expense.cancel()
		frappe.set_user("Administrator")
		other = make_property_user("Other Expense User")
		frappe.set_user(other["user"])
		foreign = frappe.new_doc("Financial Transaction")
		foreign.transaction_type = "Expense"
		foreign.amount = -80
		foreign.reference_doctype = "Property Expense"
		foreign.reference_name = expense.name
		foreign.posting_date = "2026-11-04"
		with self.assertRaises(frappe.PermissionError):
			foreign.insert()

	def test_missing_reference_is_still_rejected(self):
		doc = frappe.new_doc("Financial Transaction")
		doc.transaction_type = "Expense"
		doc.amount = 10
		doc.reference_doctype = "Property Expense"
		doc.reference_name = "EXP-DOES-NOT-EXIST"
		doc.posting_date = "2026-11-04"
		with self.assertRaises(frappe.LinkValidationError):
			doc.insert()

	def test_property_user_cannot_open_another_users_invoice(self):
		invoice = self.make_invoice(800, month="2026-12")
		generated = frappe.get_all(
			"Financial Transaction",
			filters={"reference_name": invoice.name, "docstatus": 1},
			pluck="name",
		)
		self.assertEqual(len(generated), 1)
		frappe.set_user("Administrator")
		other = make_property_user("Other Finance User")
		frappe.set_user(other["user"])
		self.assertEqual(frappe.get_list("Rent Invoice", filters={"name": invoice.name}, pluck="name"), [])
		self.assertFalse(frappe.has_permission("Rent Invoice", "read", invoice.name))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Rent Invoice", invoice.name)
		self.assertFalse(frappe.has_permission("Financial Transaction", "read", generated[0]))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Financial Transaction", generated[0])
