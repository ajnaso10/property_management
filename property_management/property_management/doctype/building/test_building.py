import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from property_management.testing import make_property_user, make_super_admin, unique_digits

test_records = []


class TestBuilding(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_property_user_cannot_read_another_users_building(self):
		frappe.set_user("Administrator")
		user_a = make_property_user("User A")
		user_b = make_property_user("User B")
		super_admin = make_super_admin()

		frappe.set_user(user_a["user"])
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{
					"doctype": "Building",
					"building_name": "Not Theirs",
					"building_code": f"X-{unique_digits(6)}",
					"status": "Active",
					"owner_user": user_b["user"],
				}
			).insert()

		building = frappe.get_doc(
			{
				"doctype": "Building",
				"building_name": "Block A",
				"building_code": f"A-{unique_digits(6)}",
				"status": "Active",
			}
		).insert()
		self.assertEqual(building.owner_user, user_a["user"])

		frappe.set_user(user_b["user"])
		visible = frappe.get_list("Building", filters={"name": building.name}, pluck="name")
		self.assertEqual(visible, [])
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Building", building.name)

		frappe.clear_cache(user=super_admin)
		frappe.set_user(super_admin)
		same = frappe.get_doc("Building", building.name)
		self.assertEqual(same.name, building.name)
