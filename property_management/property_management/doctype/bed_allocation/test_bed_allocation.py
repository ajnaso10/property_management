import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import flt

from property_management.testing import make_allocation, make_bed_stack, make_property_user, make_tenant, unique_digits

test_records = []


class TestBedAllocation(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.owner = make_property_user("Landlord")
		frappe.set_user(self.owner["user"])
		self.building, self.flat, self.area, self.bed = make_bed_stack(unique_digits(6))

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_second_active_allocation_is_rejected(self):
		first_tenant = make_tenant("First Tenant")
		make_allocation(self.bed.name, first_tenant.name)
		# Even if occupancy was forced back to Vacant, a second active row is refused.
		frappe.db.set_value("Bed", self.bed.name, "occupancy_status", "Vacant", update_modified=False)

		second_tenant = make_tenant("Second Tenant")
		with self.assertRaises(frappe.ValidationError):
			make_allocation(self.bed.name, second_tenant.name)

		active = frappe.get_all(
			"Bed Allocation",
			filters={"bed": self.bed.name, "allocation_status": "Active"},
			pluck="name",
		)
		self.assertEqual(len(active), 1)

	def test_inactive_area_or_flat_blocks_allocation(self):
		tenant = make_tenant("Waiting Tenant")
		self.area.status = "Inactive"
		self.area.save()
		with self.assertRaises(frappe.ValidationError):
			make_allocation(self.bed.name, tenant.name)

		self.area.status = "Active"
		self.area.save()
		self.flat.status = "Inactive"
		self.flat.save()
		with self.assertRaises(frappe.ValidationError):
			make_allocation(self.bed.name, tenant.name)

	def test_vacate_frees_bed_and_keeps_amounts(self):
		tenant = make_tenant("Leaving Tenant")
		allocation = make_allocation(self.bed.name, tenant.name, monthly_rent=1800, deposit_amount=750)
		self.bed.reload()
		self.assertEqual(self.bed.occupancy_status, "Occupied")
		self.assertEqual(self.bed.current_tenant, tenant.name)

		allocation.vacate()
		allocation.reload()
		self.bed.reload()
		tenant.reload()

		self.assertEqual(allocation.allocation_status, "Vacated")
		self.assertTrue(allocation.vacating_date)
		self.assertEqual(flt(allocation.monthly_rent), 1800)
		self.assertEqual(flt(allocation.deposit_amount), 750)
		self.assertEqual(self.bed.occupancy_status, "Vacant")
		self.assertFalse(self.bed.current_tenant)
		self.assertEqual(tenant.status, "Vacated")

		replacement = make_tenant("Next Tenant")
		again = make_allocation(self.bed.name, replacement.name)
		self.bed.reload()
		self.assertEqual(again.allocation_status, "Active")
		self.assertEqual(self.bed.occupancy_status, "Occupied")
		self.assertEqual(self.bed.current_tenant, replacement.name)
