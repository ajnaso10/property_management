import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from property_management.testing import (
	make_allocation,
	make_bed_stack,
	make_property_user,
	make_tenant,
	unique_digits,
	unique_mobile,
)

test_records = []


class TestTenant(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_identification_number_is_required(self):
		frappe.set_user("Administrator")
		owner = make_property_user("ID Landlord")
		frappe.set_user(owner["user"])
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Tenant",
					"tenant_name": "No Papers",
					"mobile": unique_mobile(),
					"status": "Active",
				}
			).insert()

	def test_active_tenant_cannot_be_marked_inactive(self):
		frappe.set_user("Administrator")
		owner = make_property_user("Status Landlord")
		frappe.set_user(owner["user"])
		_building, _flat, _area, bed = make_bed_stack(unique_digits(6))
		tenant = make_tenant("Still Resident")
		make_allocation(bed.name, tenant.name)
		tenant.reload()
		tenant.status = "Inactive"
		with self.assertRaises(frappe.ValidationError):
			tenant.save()
