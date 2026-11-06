import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

test_records = []


class TestPropertySettings(IntegrationTestCase):
	def test_billing_day_can_be_clamped_to_the_end_of_a_short_month(self):
		settings = frappe.get_single("Property Settings")
		settings.billing_day = 31
		settings.due_days_after_billing = 7
		settings.save()
		self.assertEqual(settings.billing_day, 31)
		settings.billing_day = 32
		with self.assertRaises(frappe.ValidationError):
			settings.save()
