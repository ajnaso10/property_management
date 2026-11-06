frappe.query_reports["User-wise Financial Summary"] = {
	filters: (function () {
		const privileged =
			frappe.session.user === "Administrator" ||
			(frappe.user_roles || []).includes("Property Super Admin") ||
			(frappe.user_roles || []).includes("System Manager");
		const filters = [];
		if (privileged) {
			filters.push({
				fieldname: "owner_user",
				label: __("Property User"),
				fieldtype: "Link",
				options: "Property User Profile",
			});
		}
		filters.push(
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
				get_query() {
					const building = frappe.query_report.get_filter_value("building");
					return building ? { filters: { building } } : {};
				},
			},
			{
				fieldname: "area",
				label: __("Area"),
				fieldtype: "Link",
				options: "Area",
				get_query() {
					const filters = {};
					const building = frappe.query_report.get_filter_value("building");
					const flat = frappe.query_report.get_filter_value("flat");
					if (building) filters.building = building;
					if (flat) filters.flat = flat;
					return { filters };
				},
			}
		);
		
		return filters;
	})(),
};
