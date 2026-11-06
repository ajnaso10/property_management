import frappe
from frappe.tests import UnitTestCase
from frappe.utils import flt
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from property_management.invoice_migration import (
	InvoiceKeyConflict,
	plan_invoice_keys,
	sqlite_upgrade_smoke,
)
from property_management.testing import make_allocation, make_bed_stack, make_property_user, make_tenant, unique_digits

test_records = []


class TestRentInvoiceKeyPlan(UnitTestCase):
	def test_sqlite_upgrade_keeps_rows_and_rejects_duplicates(self):
		sqlite_upgrade_smoke()

	def test_blank_keys_are_derived_without_changing_existing_values(self):
		updates = plan_invoice_keys(
			[
				{
					"name": "RINV-00001",
					"invoice_number": None,
					"billing_key": None,
					"bed_allocation": "ALC-00001",
					"billing_month": "2026-11",
					"docstatus": 1,
				},
				{
					"name": "RINV-00002",
					"invoice_number": "KEEP-ME",
					"billing_key": "ALC-00002-2026-10",
					"bed_allocation": "ALC-00002",
					"billing_month": "2026-10",
					"docstatus": 1,
				},
			]
		)
		by_name = {row["name"]: row for row in updates}
		self.assertEqual(by_name["RINV-00001"]["invoice_number"], "RINV-00001")
		self.assertEqual(by_name["RINV-00001"]["billing_key"], "ALC-00001-2026-11")
		self.assertNotIn("RINV-00002", by_name)

	def test_duplicate_and_incomplete_rows_are_listed_and_not_rewritten(self):
		rows = [
			{
				"name": "RINV-00001",
				"invoice_number": "",
				"billing_key": "",
				"bed_allocation": "ALC-00001",
				"billing_month": "2026-11",
				"docstatus": 1,
			},
			{
				"name": "RINV-00002",
				"invoice_number": "RINV-00002",
				"billing_key": "",
				"bed_allocation": "ALC-00001",
				"billing_month": "2026-11",
				"docstatus": 2,
			},
			{
				"name": "RINV-00003",
				"invoice_number": None,
				"billing_key": None,
				"bed_allocation": None,
				"billing_month": "2026-11",
				"docstatus": 0,
			},
		]
		with self.assertRaises(InvoiceKeyConflict) as caught:
			plan_invoice_keys(rows)
		message = str(caught.exception)
		self.assertIn("No invoice was deleted", message)
		self.assertIn("RINV-00001", message)
		self.assertIn("RINV-00002", message)
		self.assertIn("docstatus 2", message)
		self.assertIn("RINV-00003", message)
		self.assertEqual(rows[0]["billing_key"], "")
		self.assertEqual(rows[1]["docstatus"], 2)
		self.assertIsNone(rows[2]["bed_allocation"])


class TestRentInvoiceKeyBackfill(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.owner = make_property_user("Migration Landlord")
		frappe.set_user(self.owner["user"])
		_building, _flat, _area, bed = make_bed_stack(unique_digits(6))
		tenant = make_tenant("Migration Tenant")
		allocation = make_allocation(bed.name, tenant.name, monthly_rent=1000, deposit_amount=0)
		self.invoice = frappe.get_doc(
			{
				"doctype": "Rent Invoice",
				"tenant": tenant.name,
				"bed_allocation": allocation.name,
				"billing_month": "2026-11",
				"billing_date": "2026-11-01",
				"due_date": "2026-11-08",
				"rent_amount": 1000,
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_backfill_restores_blank_keys_and_can_run_again(self):
		from property_management.invoice_migration import backfill_rent_invoice_keys

		frappe.db.sql(
			"UPDATE `tabRent Invoice` SET invoice_number=NULL, billing_key=NULL WHERE name=%s",
			self.invoice.name,
		)
		first = backfill_rent_invoice_keys()
		self.assertIn(self.invoice.name, first["updated"])
		reloaded = frappe.db.get_value(
			"Rent Invoice",
			self.invoice.name,
			["invoice_number", "billing_key", "rent_amount", "docstatus"],
			as_dict=True,
		)
		self.assertEqual(reloaded.invoice_number, self.invoice.name)
		self.assertEqual(reloaded.billing_key, f"{self.invoice.bed_allocation}-2026-11")
		self.assertEqual(flt(reloaded.rent_amount), 1000)
		second = backfill_rent_invoice_keys()
		self.assertEqual(second["updated"], [])
