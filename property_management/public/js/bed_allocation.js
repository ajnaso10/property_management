frappe.ui.form.on("Bed Allocation", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.allocation_status !== "Active") {
			return;
		}
		frm.add_custom_button(__("Vacate"), () => {
			frappe.prompt(
				[
					{
						fieldname: "vacating_date",
						fieldtype: "Date",
						label: __("Vacating Date"),
						reqd: 1,
						default: frappe.datetime.get_today(),
					},
				],
				(values) => {
					frm.call("vacate", { vacating_date: values.vacating_date }).then(() => {
						frm.reload_doc();
					});
				},
				__("Vacate Bed"),
				__("Vacate")
			);
		});
	},
});
