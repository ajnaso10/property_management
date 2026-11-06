import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, flt, get_first_day, getdate, today

from property_management.analytics import current_occupancy_chart, flat_profit_chart, monthly_movement, run_report
from property_management.desk import get_overview
from property_management.finance import post_financial_transaction
from property_management.testing import (
	make_allocation,
	make_bed_stack,
	make_property_user,
	make_super_admin,
	make_tenant,
	unique_digits,
)

test_records = []


class TestPropertyReports(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.admin = make_super_admin()
		self.owner_a = make_property_user("Report Landlord A")
		self.owner_b = make_property_user("Report Landlord B")
		frappe.set_user(self.owner_a["user"])
		self.building_a, self.flat_a, self.area_a, self.bed_a = make_bed_stack(unique_digits(6))
		self.tenant_a = make_tenant("Report Tenant A")
		self.allocation_a = make_allocation(self.bed_a.name, self.tenant_a.name, monthly_rent=1800, deposit_amount=0)
		self.cash_a = self.make_cash()
		frappe.set_user(self.owner_b["user"])
		self.building_b, self.flat_b, self.area_b, self.bed_b = make_bed_stack(unique_digits(6))
		self.tenant_b = make_tenant("Report Tenant B")
		self.allocation_b = make_allocation(self.bed_b.name, self.tenant_b.name, monthly_rent=900, deposit_amount=0)

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

	def test_position_matches_overview_and_keeps_overhead_off_the_flat(self):
		frappe.set_user(self.owner_a["user"])
		prior = add_days(get_first_day(today()), -1)
		self.make_invoice(self.allocation_a.name, self.tenant_a.name, 700, prior)
		current = self.make_invoice(self.allocation_a.name, self.tenant_a.name, 1000, today())
		payment = frappe.get_doc(
			{
				"doctype": "Rent Payment",
				"tenant": self.tenant_a.name,
				"posting_date": today(),
				"amount": 400,
				"payment_mode": "Cash",
				"cash_bank_account": self.cash_a.name,
				"allocations": [{"rent_invoice": current.name, "allocated_amount": 400}],
			}
		).insert()
		payment.submit()
		post_financial_transaction(
			transaction_type="Other Revenue",
			amount=30,
			owner_user=self.owner_a["user"],
			posting_date=today(),
			building=self.building_a.name,
			flat=self.flat_a.name,
			area=self.area_a.name,
		)
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
		flat_expense = frappe.get_doc(
			{
				"doctype": "Property Expense",
				"posting_date": today(),
				"expense_category": "Repairs",
				"amount": 40,
				"building": self.building_a.name,
				"flat": self.flat_a.name,
				"area": self.area_a.name,
			}
		).insert()
		flat_expense.submit()
		overhead = frappe.get_doc(
			{
				"doctype": "Property Expense",
				"posting_date": today(),
				"expense_category": "Staff",
				"amount": 100,
				"building": self.building_a.name,
			}
		).insert()
		overhead.submit()

		overview = get_overview()
		_columns, position, _message, _chart = run_report("financial_position", {})
		amounts = {row["label"]: row["amount"] for row in position}
		self.assertEqual(flt(amounts["Recognized rental revenue"]), flt(overview["money"]["recognized_rental_revenue"]))
		self.assertEqual(flt(amounts["Recognized rental revenue"]), 1000)
		self.assertEqual(flt(amounts["Other revenue"]), 30)
		self.assertEqual(flt(amounts["Deposit transferred to revenue"]), 50)
		self.assertEqual(flt(amounts["Expenses"]), 140)
		self.assertEqual(flt(amounts["Operating profit"]), 940)
		self.assertEqual(flt(amounts["Rent collected"]), 400)
		self.assertEqual(flt(amounts["Allocated receipts"]), 400)
		self.assertEqual(flt(amounts["Advances"]), 0)
		self.assertEqual(flt(amounts["Held deposits"]), 200)
		self.assertEqual(flt(amounts["Deposit received"]), 250)
		self.assertEqual(flt(amounts["Outstanding in period"]), 600)
		self.assertEqual(flt(amounts["All open receivables"]), 1300)
		self.assertEqual(next(row["count"] for row in position if row["label"] == "Occupied beds"), 1)
		self.assertEqual(flt(amounts["Operating profit"]), flt(overview["money"]["operating_profit"]))
		_columns, rent_rows, _rent_message, _chart = run_report("rent_position", {})
		rent_amounts = {row["label"]: row["amount"] for row in rent_rows if row["row_type"] == "Summary"}
		self.assertEqual(flt(rent_amounts["Recognized rental revenue"]), 1000)
		self.assertEqual(flt(rent_amounts["Rent collected"]), 400)
		self.assertEqual(flt(rent_amounts["Advances"]), 0)
		self.assertEqual(flt(rent_amounts["All open receivables"]), 1300)
		self.assertTrue(any(row.get("rent_invoice") == current.name for row in rent_rows))
		_columns, deposits, _deposit_message, _chart = run_report("deposit_liability", {})
		deposit_amounts = {row["label"]: row["amount"] for row in deposits if row["row_type"] == "Summary"}
		self.assertEqual(flt(deposit_amounts["Held deposits"]), 200)
		self.assertEqual(flt(deposit_amounts["Deposit received"]), 250)
		self.assertEqual(flt(deposit_amounts["Deposit transferred to revenue"]), 50)

		_columns, flats, flat_message, _chart = run_report("flat_profitability", {})
		flat_row = next(row for row in flats if row["location"] == self.flat_a.name)
		self.assertEqual(flt(flat_row["direct_expenses"]), 40)
		self.assertEqual(flt(flat_row["recognized_rental_revenue"]), 1000)
		self.assertEqual(flt(flat_row["direct_operating_profit"]), 1040)
		self.assertEqual(flt(flat_row["outstanding_open"]), 1300)
		self.assertIn("Unallocated overhead is 100", flat_message)

		_columns, buildings, _message, _chart = run_report("building_profitability", {})
		building_row = next(row for row in buildings if row["location"] == self.building_a.name)
		self.assertEqual(flt(building_row["expenses"]), 140)
		self.assertEqual(flt(building_row["overhead_not_on_a_flat"]), 100)
		self.assertEqual(flt(building_row["operating_profit"]), 940)
		self.assertEqual(
			flt(flat_row["direct_operating_profit"]) - flt(building_row["overhead_not_on_a_flat"]),
			flt(building_row["operating_profit"]),
		)

		_columns, areas, area_message, _chart = run_report("area_profitability", {})
		area_row = next(row for row in areas if row["location"] == self.area_a.name)
		self.assertEqual(flt(area_row["direct_expenses"]), 40)
		self.assertIn("Unallocated overhead is 100", area_message)

		_columns, expenses, expense_message, _chart = run_report("expense_register", {})
		self.assertEqual(sorted(row["amount"] for row in expenses), [40, 100])
		self.assertEqual(
			{row["placement"] for row in expenses},
			{"Area", "Building overhead"},
		)
		self.assertIn("Net expenses are 140", expense_message)

		overhead.cancel()
		_columns, expenses, expense_message, _chart = run_report("expense_register", {})
		self.assertEqual(flt(sum(row["amount"] for row in expenses)), 40)
		self.assertEqual(len(expenses), 3)
		self.assertIn("Net expenses are 40", expense_message)
		self.assertIn("Building overhead with no flat is 0", expense_message)
		_columns, flats, flat_message, _chart = run_report("flat_profitability", {})
		flat_row = next(row for row in flats if row["location"] == self.flat_a.name)
		self.assertEqual(flt(flat_row["direct_expenses"]), 40)
		self.assertIn("Unallocated overhead is 0", flat_message)
		_columns, position, _message, _chart = run_report("financial_position", {})
		amounts = {row["label"]: row["amount"] for row in position}
		self.assertEqual(flt(amounts["Expenses"]), 40)
		self.assertEqual(flt(amounts["Operating profit"]), 1040)
		self.assertEqual(flt(amounts["Rent collected"]), 400)

		self.allocation_a.vacate(vacating_date=today())
		_columns, occupancy_rows, occupancy_message, occupancy_chart = run_report("occupancy", {})
		self.assertEqual(next(row["count"] for row in occupancy_rows if row["label"] == "Occupied beds"), 0)
		stay = next(row for row in occupancy_rows if row.get("allocation") == self.allocation_a.name)
		self.assertEqual(stay["allocation_status"], "Vacated")
		self.assertIn("not a history", occupancy_message)
		self.assertEqual(occupancy_chart["data"]["datasets"][0]["values"][0], 0)
		_columns, position, _message, _chart = run_report("financial_position", {})
		self.assertEqual(
			flt(next(row["amount"] for row in position if row["label"] == "All open receivables")),
			1300,
		)

		_columns, history, history_message, _chart = run_report(
			"tenant_history", {"tenant": self.tenant_a.name}
		)
		self.assertNotIn("debit", {column["fieldname"] for column in _columns})
		self.assertNotIn("credit", {column["fieldname"] for column in _columns})
		snapshot = next(row for row in history if row["row_type"] == "Snapshot")
		self.assertEqual(flt(snapshot["amount"]), 1300)
		self.assertIn("vacating", history_message.lower())
		self.assertTrue(any(row.get("reference_name") == self.allocation_a.name for row in history))
		self.assertIn("not a debit and credit ledger", run_report("transaction_history", {})[2])

	def test_owner_isolation_filters_and_charts(self):
		frappe.set_user(self.owner_a["user"])
		self.make_invoice(self.allocation_a.name, self.tenant_a.name, 1000, today())
		frappe.set_user(self.owner_b["user"])
		self.make_invoice(self.allocation_b.name, self.tenant_b.name, 50, today())

		frappe.set_user(self.owner_a["user"])
		_columns, position, _message, _chart = run_report("financial_position", {})
		self.assertEqual(flt(next(row["amount"] for row in position if row["label"] == "Recognized rental revenue")), 1000)
		with self.assertRaises(frappe.PermissionError):
			run_report("financial_position", {"owner_user": self.owner_b["user"]})
		with self.assertRaises(frappe.PermissionError):
			run_report("flat_profitability", {"building": self.building_b.name})
		with self.assertRaises(frappe.PermissionError):
			run_report("transaction_history", {"owner_user": "' OR 1=1 --"})
		with self.assertRaises(frappe.PermissionError):
			monthly_movement({"flat": self.flat_b.name})
		_columns, users, _message, _chart = run_report("user_wise_financial_summary", {})
		self.assertEqual([row["user"] for row in users], [self.owner_a["user"]])
		self.assertEqual(flt(users[0]["recognized_rental_revenue"]), 1000)

		month = getdate(today()).strftime("%Y-%m")
		own_chart = monthly_movement({})
		self.assertIn(month, own_chart["labels"])
		index = own_chart["labels"].index(month)
		self.assertEqual(flt(own_chart["datasets"][0]["values"][index]), 1000)
		self.assertEqual(
			[dataset["name"] for dataset in own_chart["datasets"]],
			["Recognized rental revenue", "Rent collected", "Expenses", "Operating profit"],
		)
		flat_chart = flat_profit_chart({})
		self.assertEqual(flat_chart["labels"], [self.flat_a.flat_number])
		self.assertEqual(flt(flat_chart["datasets"][0]["values"][0]), 1000)
		occupancy_chart = current_occupancy_chart({})
		self.assertEqual(occupancy_chart["labels"], ["Occupied", "Vacant", "Maintenance"])
		self.assertEqual(occupancy_chart["datasets"][0]["values"], [1, 0, 0])
		self.assertEqual(len(occupancy_chart["labels"]), 3)

		frappe.set_user(self.owner_b["user"])
		other_chart = monthly_movement({})
		other_index = other_chart["labels"].index(month)
		self.assertEqual(flt(other_chart["datasets"][0]["values"][other_index]), 50)

		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			run_report("rent_position", {})

		frappe.set_user(self.admin)
		with self.assertRaises(frappe.ValidationError):
			run_report("financial_position", {"owner_user": "' OR 1=1 --"})
		_columns, users, _message, _chart = run_report("user_wise_financial_summary", {})
		by_user = {row["user"]: row for row in users}
		self.assertEqual(flt(by_user[self.owner_a["user"]]["recognized_rental_revenue"]), 1000)
		self.assertEqual(flt(by_user[self.owner_b["user"]]["recognized_rental_revenue"]), 50)
		admin_chart = monthly_movement({"owner_user": self.owner_b["username"]})
		admin_index = admin_chart["labels"].index(month)
		self.assertEqual(flt(admin_chart["datasets"][0]["values"][admin_index]), 50)

		prior = add_days(get_first_day(today()), -1)
		explicit = monthly_movement({"from_date": prior, "to_date": prior, "owner_user": self.owner_a["user"]})
		self.assertEqual(explicit["labels"], [prior.strftime("%Y-%m")])
		self.assertEqual(flt(explicit["datasets"][0]["values"][0]), 0)

	def test_empty_report_is_zero_and_fixtures_are_restricted(self):
		frappe.set_user(self.admin)
		fresh = make_property_user("Report Empty")
		frappe.set_user(fresh["user"])
		_columns, rows, _message, _chart = run_report("financial_position", {})
		amounts = {row["label"]: row["amount"] for row in rows}
		for label in ("Recognized rental revenue", "Operating profit", "Held deposits", "Expenses", "Advances"):
			self.assertEqual(flt(amounts[label]), 0)
		_columns, flats, message, chart = run_report("flat_profitability", {})
		self.assertEqual(flats, [])
		self.assertIsNone(chart)
		self.assertIn("Unallocated overhead is 0", message)
		occupancy_chart = current_occupancy_chart({})
		self.assertEqual(occupancy_chart["datasets"][0]["values"], [0, 0, 0])

		frappe.set_user("Administrator")
		report = frappe.get_doc("Report", "Financial Position")
		self.assertEqual(
			{row.role for row in report.roles},
			{"Property User", "Property Super Admin", "System Manager"},
		)
		user_report = frappe.get_doc("Report", "User-wise Financial Summary")
		self.assertIn("Property User", {row.role for row in user_report.roles})
		chart = frappe.get_doc("Dashboard Chart", "Current Occupancy")
		self.assertEqual(chart.type, "Donut")
		self.assertIn("Property User", {row.role for row in chart.roles})
		dashboard = frappe.get_doc("Dashboard", "Property Overview")
		self.assertEqual(
			{row.chart for row in dashboard.charts},
			{"Monthly Property Movement", "Flat Direct Profit", "Current Occupancy"},
		)
