import frappe
from frappe.utils import add_days, today

from property_management.api import create_property_user


def unique_digits(length=8):
	raw = frappe.generate_hash(length=length)
	return "".join(str(int(char, 16) % 10) for char in raw)


def unique_mobile():
	return "9715" + unique_digits(8)


def future_expiry(days=30):
	return add_days(today(), days)


def make_property_user(full_name=None):
	mobile = unique_mobile()
	return create_property_user(
		full_name or f"Property {mobile[-4:]}",
		mobile,
		"initial-pass-1",
		future_expiry(),
	)


def make_super_admin():
	email = f"super.{unique_digits(10)}@example.com"
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Super",
			"last_name": "Admin",
			"send_welcome_email": 0,
			"user_type": "System User",
			"roles": [{"role": "Property Super Admin"}],
		}
	)
	user.new_password = "initial-pass-1"
	user.flags.ignore_password_policy = True
	user.insert(ignore_permissions=True)
	return user.name


def make_bed_stack(code):
	"""Create a building, flat, area, and vacant bed as the current user."""
	building = frappe.get_doc(
		{
			"doctype": "Building",
			"building_name": f"Harbour {code}",
			"building_code": code,
			"status": "Active",
			"location": "Dubai",
			"address": "1 Harbour Road",
		}
	).insert()
	flat = frappe.get_doc(
		{
			"doctype": "Flat",
			"flat_number": f"F-{code}",
			"building": building.name,
			"status": "Active",
		}
	).insert()
	area = frappe.get_doc(
		{
			"doctype": "Area",
			"area_name": "Bedroom 1",
			"area_code": f"A-{code}",
			"area_type": "Bedroom",
			"flat": flat.name,
			"floor_number": 2,
			"capacity": 2,
			"status": "Active",
		}
	).insert()
	bed = frappe.get_doc(
		{
			"doctype": "Bed",
			"bed_number": "1",
			"area": area.name,
			"status": "Active",
			"occupancy_status": "Vacant",
			"monthly_rent": 1500,
		}
	).insert()
	return building, flat, area, bed


def make_tenant(name, mobile=None):
	return frappe.get_doc(
		{
			"doctype": "Tenant",
			"tenant_name": name,
			"mobile": mobile or unique_mobile(),
			"identification_number": f"ID-{unique_digits(6)}",
			"address": "Tenant address",
			"emergency_contact": "971500000000",
			"status": "Active",
		}
	).insert()


def make_allocation(bed, tenant, monthly_rent=1800, deposit_amount=500):
	return frappe.get_doc(
		{
			"doctype": "Bed Allocation",
			"tenant": tenant,
			"bed": bed,
			"allocation_status": "Active",
			"monthly_rent": monthly_rent,
			"deposit_amount": deposit_amount,
			"billing_start_date": today(),
			"remarks": "Agreed at move-in",
		}
	).insert()
