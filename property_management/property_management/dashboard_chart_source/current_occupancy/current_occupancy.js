frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Current Occupancy"] = {
	method: "property_management.property_management.dashboard_chart_source.current_occupancy.current_occupancy.get",
	filters: [
		{
			fieldname: "owner_user",
			label: __("Property User"),
			fieldtype: "Link",
			options: "Property User Profile",
		},

		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "building",
			label: __("Building"),
			fieldtype: "Link",
			options: "Building",
		},
		{
			fieldname: "flat",
			label: __("Flat"),
			fieldtype: "Link",
			options: "Flat",
		},
		{
			fieldname: "area",
			label: __("Area"),
			fieldtype: "Link",
			options: "Area",
		}
	],
};
