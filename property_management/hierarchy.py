import sys

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from property_management.permissions import is_privileged


class OwnedDocument(Document):
	"""Document whose rows are private to Owner User.

	Frappe v16.53 `get_doc(doctype, name)` loads the row and does not check
	permissions unless the caller passes `check_permission`. List queries still
	hide the name, so the remaining leak is opening a known name. Checking on
	load closes `get_doc`, form load, and the resource API together.

	`frappe.has_permission(doctype, perm, name)` loads the same row through
	`get_lazy_doc` only to evaluate the hook. That fetch must not raise, or the
	permission call itself would error instead of returning False.
	"""

	def load_from_db(self):
		super().load_from_db()
		if self.flags.ignore_permissions or frappe.flags.get("ignore_permissions"):
			return
		if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
			return
		if _called_from_get_lazy_doc():
			return
		self.check_permission("read")


def _called_from_get_lazy_doc():
	frame = sys._getframe()
	while frame is not None:
		if frame.f_code.co_name == "get_lazy_doc":
			return True
		frame = frame.f_back
	return False


def apply_owner(doc):
	"""Property Users are pinned to their own user. Privileged roles must set an owner."""
	user = frappe.session.user
	if is_privileged(user):
		if not doc.owner_user:
			frappe.throw(_("Owner User is required"))
		return

	if user in (None, "", "Guest"):
		frappe.throw(_("You need to be logged in."), frappe.PermissionError)

	if not doc.owner_user:
		doc.owner_user = user
	if doc.owner_user != user:
		frappe.throw(_("You can only work with your own records."), frappe.PermissionError)


def require_readable(doctype, name):
	if not name:
		frappe.throw(_("{0} is required.").format(doctype))
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} was not found.").format(doctype, name))
	if not frappe.has_permission(doctype, "read", name):
		frappe.throw(
			_("{0} {1} is not available.").format(doctype, name),
			frappe.PermissionError,
		)


def copy_owner_from(doc, parent_doctype, parent_name):
	require_readable(parent_doctype, parent_name)
	owner = frappe.db.get_value(parent_doctype, parent_name, "owner_user")
	if not owner:
		frappe.throw(_("{0} {1} has no owner.").format(parent_doctype, parent_name))
	doc.owner_user = owner
	apply_owner(doc)


def assert_status_active(doctype, name):
	if not name:
		return
	status = frappe.db.get_value(doctype, name, "status")
	if status != "Active":
		frappe.throw(_("{0} {1} is not active. Activate it before allocating a bed.").format(doctype, name))


def assert_unique(doctype, fieldname, value, filters, current_name=None):
	if not value:
		return
	filters = dict(filters)
	filters[fieldname] = value
	existing = frappe.db.get_value(doctype, filters, "name")
	if existing and existing != current_name:
		label = frappe.get_meta(doctype).get_label(fieldname) or fieldname
		frappe.throw(_("{0} {1} is already used.").format(label, value))


def assert_non_negative(doc, *fieldnames):
	for fieldname in fieldnames:
		value = doc.get(fieldname)
		if value is None or value == "":
			continue
		if flt(value) < 0:
			frappe.throw(
				_("{0} cannot be negative.").format(doc.meta.get_label(fieldname) or fieldname)
			)


def update_area_counts(area):
	if not area or not frappe.db.exists("Area", area):
		return
	total = cint(frappe.db.count("Bed", {"area": area}))
	occupied = cint(frappe.db.count("Bed", {"area": area, "occupancy_status": "Occupied"}))
	vacant = cint(frappe.db.count("Bed", {"area": area, "occupancy_status": "Vacant"}))
	frappe.db.set_value(
		"Area",
		area,
		{"number_of_beds": total, "occupied_beds": occupied, "vacant_beds": vacant},
		update_modified=False,
	)


def update_flat_counts(flat):
	if not flat or not frappe.db.exists("Flat", flat):
		return
	areas = cint(frappe.db.count("Area", {"flat": flat}))
	total = cint(frappe.db.count("Bed", {"flat": flat}))
	occupied = cint(frappe.db.count("Bed", {"flat": flat, "occupancy_status": "Occupied"}))
	vacant = cint(frappe.db.count("Bed", {"flat": flat, "occupancy_status": "Vacant"}))
	frappe.db.set_value(
		"Flat",
		flat,
		{
			"number_of_areas": areas,
			"total_beds": total,
			"occupied_beds": occupied,
			"vacant_beds": vacant,
		},
		update_modified=False,
	)


def refresh_counts_for_bed(bed):
	if not bed or not frappe.db.exists("Bed", bed):
		return
	area, flat = frappe.db.get_value("Bed", bed, ["area", "flat"])
	update_area_counts(area)
	update_flat_counts(flat)


def sync_bed_occupancy(bed):
	"""Reflect the active allocation, if any. Rent and deposit rows are left in place."""
	if not bed or not frappe.db.exists("Bed", bed):
		return
	active = frappe.db.get_value(
		"Bed Allocation",
		{"bed": bed, "allocation_status": "Active"},
		["tenant", "monthly_rent"],
		as_dict=True,
	)
	if active:
		frappe.db.set_value(
			"Bed",
			bed,
			{
				"occupancy_status": "Occupied",
				"current_tenant": active.tenant,
				"monthly_rent": active.monthly_rent,
			},
			update_modified=False,
		)
	else:
		# Keep monthly_rent. It is the last agreed figure, not a balance to zero out.
		frappe.db.set_value(
			"Bed",
			bed,
			{"occupancy_status": "Vacant", "current_tenant": None},
			update_modified=False,
		)
	refresh_counts_for_bed(bed)


def refresh_tenant_status(tenant):
	if not tenant or not frappe.db.exists("Tenant", tenant):
		return
	current = frappe.db.get_value("Tenant", tenant, "status")
	if current == "Inactive":
		return
	active = frappe.db.exists("Bed Allocation", {"tenant": tenant, "allocation_status": "Active"})
	frappe.db.set_value(
		"Tenant",
		tenant,
		"status",
		"Active" if active else "Vacated",
		update_modified=False,
	)
