import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, cint, today

from property_management.api import create_property_user
from property_management.auth import assert_login_allowed
from property_management.install import ROLE_PROPERTY_SUPER_ADMIN, ROLE_PROPERTY_USER, ensure_roles
from property_management.testing import future_expiry, make_property_user, unique_mobile

test_records = []


class TestPropertyUserProfile(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_roles_are_created_with_desk_access(self):
		ensure_roles()
		for role_name in (ROLE_PROPERTY_SUPER_ADMIN, ROLE_PROPERTY_USER):
			role = frappe.get_doc("Role", role_name)
			self.assertEqual(cint(role.desk_access), 1)
			self.assertEqual(cint(role.disabled), 0)

	def test_create_property_user_uses_mobile_as_username(self):
		frappe.set_user("Administrator")
		mobile = unique_mobile()
		created = create_property_user("Amina Hassan", mobile, "initial-pass-1", future_expiry())
		user = frappe.get_doc("User", created["user"])
		profile = frappe.get_doc("Property User Profile", created["property_user_profile"])

		self.assertEqual(user.username, mobile)
		self.assertEqual(user.mobile_no, mobile)
		self.assertEqual(profile.mobile_number, mobile)
		self.assertEqual(cint(profile.must_change_password), 1)
		self.assertNotIn("password", profile.as_dict())
		self.assertTrue(ROLE_PROPERTY_USER in {row.role for row in user.roles})
		self.assertFalse(user.new_password)

	def test_property_user_cannot_create_users(self):
		frappe.set_user("Administrator")
		created = make_property_user()
		frappe.set_user(created["user"])
		with self.assertRaises(frappe.PermissionError):
			create_property_user("Other Person", unique_mobile(), "initial-pass-1", future_expiry())

	def test_login_check_allows_active_account_as_guest(self):
		"""before_login still runs as Guest; loading the profile must not PermissionError."""
		frappe.set_user("Administrator")
		created = make_property_user()
		frappe.set_user("Guest")
		assert_login_allowed(created["user"])

	def test_expired_account_is_blocked(self):
		frappe.set_user("Administrator")
		created = make_property_user()
		profile = frappe.get_doc("Property User Profile", created["property_user_profile"])
		profile.account_expiry = add_days(today(), -1)
		profile.save(ignore_permissions=True)

		# Login hooks evaluate the profile before the session is created.
		frappe.set_user("Guest")
		with self.assertRaises(frappe.AuthenticationError):
			assert_login_allowed(created["user"])

	def test_guest_reset_is_refused_for_property_user(self):
		frappe.set_user("Administrator")
		created = make_property_user()
		user = frappe.get_doc("User", created["user"])

		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict()
		with self.assertRaises(frappe.PermissionError):
			user.validate_reset_password()

		frappe.set_user(created["user"])
		frappe.local.form_dict = frappe._dict()
		with self.assertRaises(frappe.PermissionError):
			user.validate_reset_password()

		frappe.local.form_dict = frappe._dict(new_password="a-different-pass-1")
		user.validate_reset_password()
