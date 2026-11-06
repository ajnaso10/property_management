import frappe

from property_management.analytics import monthly_movement


@frappe.whitelist()
def get(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
):
	filters = frappe.parse_json(filters) or {}
	if from_date and not filters.get("from_date"):
		filters["from_date"] = from_date
	if to_date and not filters.get("to_date"):
		filters["to_date"] = to_date
	return monthly_movement(filters)
