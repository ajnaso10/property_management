import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

test_records = []


class TestPropertySettings(IntegrationTestCase):
	def test_billing_day_stays_inside_every_month(self):
		settings = frappe.get_single("Property Settings")
		settings.billing_day = 31
		with self.assertRaises(frappe.ValidationError):
			settings.save()
