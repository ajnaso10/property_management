import json

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, flt, get_first_day, get_last_day, getdate, today

from property_management.desk import (
	get_filter_options,
	get_operations,
	get_overview,
	list_property_accounts,
)
from property_management.testing import (
	make_allocation,
	make_bed_stack,
	make_property_user,
	make_super_admin,
	make_tenant,
	unique_digits,
)

test_records = []


class TestDeskPages(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.admin = make_super_admin()
		self.owner_a = make_property_user("Desk Landlord A")
		self.owner_b = make_property_user("Desk Landlord B")
		frappe.set_user(self.owner_a["user"])
		self.building_a, self.flat_a, self.area_a, self.bed_a = make_bed_stack(unique_digits(6))
		self.tenant_a = make_tenant("Desk Tenant A")
		self.allocation_a = make_allocation(self.bed_a.name, self.tenant_a.name, monthly_rent=1800, deposit_amount=0)
		self.cash_a = self.make_cash()
		frappe.set_user(self.owner_b["user"])
		self.building_b, self.flat_b, self.area_b, self.bed_b = make_bed_stack(unique_digits(6))
		self.tenant_b = make_tenant("Desk Tenant B")
		self.allocation_b = make_allocation(self.bed_b.name, self.tenant_b.name, monthly_rent=900, deposit_amount=0)
		self.cash_b = self.make_cash()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def make_cash(self):
		return frappe.get_doc(
			{
				"doctype": "Cash Bank Account",
				"account_name": f"Cash {unique_digits(4)}",
				"account_type": "Cash",
				"status": "Active",
			}
		).insert()

	def make_invoice(self, allocation, tenant, amount, billing_date):
		billing_date = getdate(billing_date)
		invoice = frappe.get_doc(
			{
				"doctype": "Rent Invoice",
				"tenant": tenant,
				"bed_allocation": allocation,
				"billing_month": billing_date.strftime("%Y-%m"),
				"billing_date": billing_date,
				"due_date": billing_date,
				"rent_amount": amount,
			}
		).insert()
		invoice.submit()
		return invoice

	def make_payment(self, tenant, cash, amount, invoice):
		payment = frappe.get_doc(
			{
				"doctype": "Rent Payment",
				"tenant": tenant,
				"posting_date": today(),
				"amount": amount,
				"payment_mode": "Cash",
				"cash_bank_account": cash,
				"allocations": [{"rent_invoice": invoice, "allocated_amount": amount}],
			}
		).insert()
		payment.submit()
		return payment

	def make_expense(self, building, amount, flat=None, area=None):
		expense = frappe.get_doc(
			{
				"doctype": "Property Expense",
				"posting_date": today(),
				"expense_category": "Repairs",
				"amount": amount,
				"building": building,
				"flat": flat,
				"area": area,
			}
		).insert()
		expense.submit()
		return expense

	def test_new_user_overview_is_zero_and_defaults_to_this_month(self):
		frappe.set_user(self.admin)
		fresh = make_property_user("Desk Empty")
		frappe.set_user(fresh["user"])
		result = get_overview()
		self.assertEqual(result["scope"]["from_date"], str(get_first_day(today())))
		self.assertEqual(result["scope"]["to_date"], str(get_last_day(today())))
		self.assertTrue(result["scope"]["period_is_default"])
		self.assertNotIn("users", result)
		for value in result["occupancy"].values():
			self.assertEqual(flt(value), 0)
		for value in result["money"].values():
			self.assertEqual(flt(value), 0)
		operations = get_operations()
		self.assertEqual(operations["hierarchy"], [])
		self.assertEqual(operations["invoices"]["rows"], [])

	def test_profit_uses_transactions_and_does_not_treat_deposits_or_cash_as_revenue(self):
		frappe.set_user(self.owner_a["user"])
		invoice = self.make_invoice(self.allocation_a.name, self.tenant_a.name, 1000, today())
		payment = self.make_payment(self.tenant_a.name, self.cash_a.name, 400, invoice.name)
		deposit = frappe.get_doc(
			{
				"doctype": "Tenant Deposit",
				"tenant": self.tenant_a.name,
				"bed_allocation": self.allocation_a.name,
			}
		).insert()
		receipt = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Receipt",
				"posting_date": today(),
				"amount": 250,
				"payment_mode": "Cash",
				"cash_bank_account": self.cash_a.name,
			}
		).insert()
		receipt.submit()
		expense = self.make_expense(self.building_a.name, 100, flat=self.flat_a.name, area=self.area_a.name)

		result = get_overview()
		money = result["money"]
		self.assertEqual(flt(money["recognized_rental_revenue"]), 1000)
		self.assertEqual(flt(money["rent_collected"]), 400)
		self.assertEqual(flt(money["allocated_receipts"]), 400)
		self.assertEqual(flt(money["advances"]), 0)
		self.assertEqual(flt(money["outstanding_open"]), 600)
		self.assertEqual(flt(money["outstanding_in_period"]), 600)
		self.assertEqual(flt(money["held_deposits"]), 250)
		self.assertEqual(flt(money["deposit_received"]), 250)
		self.assertEqual(flt(money["expenses"]), 100)
		self.assertEqual(flt(money["operating_profit"]), 900)
		self.assertEqual(flt(result["occupancy"]["beds_occupied"]), 1)
		self.assertEqual(flt(result["money"]["monthly_fixed_rent"]), 1800)

		transfer = frappe.get_doc(
			{
				"doctype": "Deposit Transaction",
				"tenant_deposit": deposit.name,
				"transaction_type": "Transfer to Revenue",
				"posting_date": today(),
				"amount": 50,
			}
		).insert()
		transfer.submit()
		result = get_overview()
		self.assertEqual(flt(result["money"]["held_deposits"]), 200)
		self.assertEqual(flt(result["money"]["deposit_transferred_to_revenue"]), 50)
		self.assertEqual(flt(result["money"]["operating_profit"]), 950)
		self.assertEqual(flt(result["money"]["rent_collected"]), 400)

		expense.cancel()
		result = get_overview()
		self.assertEqual(flt(result["money"]["expenses"]), 0)
		self.assertEqual(flt(result["money"]["operating_profit"]), 1050)

		payment.cancel()
		result = get_overview()
		self.assertEqual(flt(result["money"]["rent_collected"]), 0)
		self.assertEqual(flt(result["money"]["allocated_receipts"]), 0)
		self.assertEqual(flt(result["money"]["advances"]), 0)
		self.assertEqual(flt(result["money"]["outstanding_open"]), 1000)
		self.assertEqual(flt(result["money"]["operating_profit"]), 1050)

		invoice.reload()
		invoice.cancel()
		result = get_overview()
		self.assertEqual(flt(result["money"]["recognized_rental_revenue"]), 0)
		self.assertEqual(flt(result["money"]["outstanding_open"]), 0)
		self.assertEqual(flt(result["money"]["operating_profit"]), 50)
		self.assertEqual(flt(result["money"]["held_deposits"]), 200)

	def test_location_and_period_filters(self):
		frappe.set_user(self.owner_a["user"])
		self.make_expense(self.building_a.name, 100)
		self.make_expense(self.building_a.name, 40, flat=self.flat_a.name, area=self.area_a.name)
		by_building = get_overview(building=self.building_a.name)
		by_flat = get_overview(flat=self.flat_a.name)
		by_area = get_overview(area=self.area_a.name)
		self.assertEqual(flt(by_building["money"]["expenses"]), 140)
		self.assertEqual(flt(by_flat["money"]["expenses"]), 40)
		self.assertEqual(flt(by_area["money"]["expenses"]), 40)

		prior = add_days(get_first_day(today()), -1)
		prior_invoice = self.make_invoice(self.allocation_a.name, self.tenant_a.name, 700, prior)
		current = get_overview()
		self.assertEqual(flt(current["money"]["recognized_rental_revenue"]), 0)
		self.assertEqual(flt(current["money"]["outstanding_in_period"]), 0)
		self.assertEqual(flt(current["money"]["outstanding_open"]), 700)
		previous = get_overview(from_date=prior, to_date=prior)
		self.assertEqual(flt(previous["money"]["recognized_rental_revenue"]), 700)
		self.assertFalse(previous["scope"]["period_is_default"])
		self.assertEqual(prior_invoice.docstatus, 1)

		with self.assertRaises(frappe.ValidationError):
			get_overview(from_date=today(), to_date=prior)

	def test_vacating_stops_fixed_rent_after_the_receivable_is_paid(self):
		frappe.set_user(self.owner_a["user"])
		invoice = self.make_invoice(self.allocation_a.name, self.tenant_a.name, 1000, today())
		before = get_overview()
		self.assertEqual(flt(before["money"]["monthly_fixed_rent"]), 1800)
		self.assertEqual(flt(before["occupancy"]["beds_occupied"]), 1)
		with self.assertRaises(frappe.ValidationError):
			self.allocation_a.vacate(vacating_date=today())
		self.allocation_a.reload()
		self.assertEqual(self.allocation_a.allocation_status, "Active")
		self.assertEqual(flt(get_overview()["money"]["outstanding_open"]), 1000)
		self.make_payment(self.tenant_a.name, self.cash_a.name, 1000, invoice.name)
		self.allocation_a.vacate(vacating_date=today())
		after = get_overview()
		self.assertEqual(flt(after["money"]["monthly_fixed_rent"]), 0)
		self.assertEqual(flt(after["occupancy"]["beds_occupied"]), 0)
		self.assertEqual(flt(after["money"]["outstanding_open"]), 0)
		invoice.reload()
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.status, "Paid")
		self.assertEqual(flt(invoice.outstanding), 0)
		operations = get_operations()
		statuses = {row["name"]: row["status"] for row in operations["schedules"]["rows"]}
		schedule = frappe.db.get_value("Monthly Revenue", {"bed_allocation": self.allocation_a.name}, "name")
		self.assertEqual(statuses[schedule], "Stopped")

	def test_callers_cannot_widen_the_scope(self):
		frappe.set_user(self.owner_a["user"])
		self.make_invoice(self.allocation_a.name, self.tenant_a.name, 1000, today())
		frappe.set_user(self.owner_b["user"])
		self.make_invoice(self.allocation_b.name, self.tenant_b.name, 50, today())

		frappe.set_user(self.owner_a["user"])
		own = get_overview(owner_user=self.owner_a["username"])
		self.assertEqual(flt(own["money"]["recognized_rental_revenue"]), 1000)
		self.assertEqual(flt(own["money"]["monthly_fixed_rent"]), 1800)
		self.assertNotIn("users", own)
		operations = get_operations()
		buildings = {row["name"] for row in operations["hierarchy"]}
		self.assertIn(self.building_a.name, buildings)
		self.assertNotIn(self.building_b.name, buildings)
		options = get_filter_options()
		option_names = {row["name"] for row in options["buildings"]}
		self.assertIn(self.building_a.name, option_names)
		self.assertNotIn(self.building_b.name, option_names)

		with self.assertRaises(frappe.PermissionError):
			get_overview(owner_user=self.owner_b["user"])
		with self.assertRaises(frappe.PermissionError):
			get_overview(owner_user="' OR 1=1 --")
		with self.assertRaises(frappe.PermissionError):
			get_overview(building=self.building_b.name)
		with self.assertRaises(frappe.PermissionError):
			get_operations(flat=self.flat_b.name)
		with self.assertRaises(frappe.PermissionError):
			get_filter_options(building=self.building_b.name)
		with self.assertRaises(frappe.PermissionError):
			list_property_accounts()

		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_overview()

		frappe.set_user("Administrator")
		plain = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"plain.{unique_digits(8)}@example.com",
				"first_name": "Plain",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
		frappe.set_user(plain.name)
		with self.assertRaises(frappe.PermissionError):
			get_operations()

		frappe.set_user(self.admin)
		with self.assertRaises(frappe.ValidationError):
			get_overview(owner_user="' OR 1=1 --")
		with self.assertRaises(frappe.ValidationError):
			get_overview(building=self.building_a.name, flat=self.flat_b.name)
		scoped = get_overview(owner_user=self.owner_a["user"])
		self.assertEqual(flt(scoped["money"]["recognized_rental_revenue"]), 1000)
		self.assertEqual(flt(scoped["money"]["monthly_fixed_rent"]), 1800)
		other = get_overview(owner_user=self.owner_b["username"])
		self.assertEqual(flt(other["money"]["recognized_rental_revenue"]), 50)
		rows = {row["user"]: row for row in scoped["users"]}
		self.assertEqual(set(rows), {self.owner_a["user"]})
		admin_options = get_filter_options(owner_user=self.owner_b["user"])
		admin_buildings = {row["name"] for row in admin_options["buildings"]}
		self.assertIn(self.building_b.name, admin_buildings)
		self.assertNotIn(self.building_a.name, admin_buildings)

		accounts = list_property_accounts()
		mobiles = {account["mobile_number"] for account in accounts}
		self.assertIn(self.owner_a["username"], mobiles)
		self.assertIn(self.owner_b["username"], mobiles)
		for account in accounts:
			self.assertNotIn("password", account)
			self.assertNotIn("new_password", account)
			self.assertNotIn("initial-pass-1", json.dumps(account))

	def test_pages_and_workspace_links(self):
		frappe.set_user("Administrator")
		panel = frappe.get_doc("Page", "super-admin-panel")
		self.assertEqual(
			{row.role for row in panel.roles},
			{"Property Super Admin", "System Manager"},
		)
		report = frappe.get_doc("Page", "user-report")
		self.assertEqual(
			{row.role for row in report.roles},
			{"Property User", "Property Super Admin", "System Manager"},
		)
		workspace = frappe.get_doc("Workspace", "Property Management")
		link_targets = {link.link_to for link in workspace.links if link.link_to}
		self.assertIn("super-admin-panel", link_targets)
		self.assertIn("user-report", link_targets)
		self.assertIn("Bed Allocation", link_targets)
		self.assertIn("Property Expense", link_targets)
		content = json.loads(workspace.content)
		card_names = {block["data"]["card_name"] for block in content if block.get("type") == "card"}
		card_labels = {link.label for link in workspace.links if link.type == "Card Break"}
		self.assertEqual(card_names, card_labels)
		sidebar = frappe.get_doc("Sidebar", "Property Management")
		labels = {item.label for item in sidebar.items}
		self.assertIn("Super Admin Panel", labels)
		self.assertIn("User Report", labels)
		self.assertIn("Rent Invoice", labels)
