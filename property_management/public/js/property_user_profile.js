frappe.ui.form.on("Property User Profile", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		const roles = frappe.user_roles || [];
		const allowed =
			frappe.session.user === "Administrator" ||
			roles.includes("Property Super Admin") ||
			roles.includes("System Manager");
		if (!allowed) {
			return;
		}

		frm.add_custom_button(__("Reset Password"), () => {
			frappe.prompt(
				[
					{
						fieldname: "new_password",
						fieldtype: "Password",
						label: __("New Password"),
						reqd: 1,
						description: __("The user must change this password the next time they sign in."),
					},
				],
				(values) => {
					frm.call("reset_password", { new_password: values.new_password }).then(() => {
						frm.reload_doc();
					});
				},
				__("Reset Password"),
				__("Set Password")
			);
		});

		frm.add_custom_button(__("Set Expiry"), () => {
			frappe.prompt(
				[
					{
						fieldname: "account_expiry",
						fieldtype: "Date",
						label: __("Account Expiry"),
						reqd: 1,
						default: frm.doc.account_expiry,
					},
				],
				(values) => {
					frm.call("set_expiry", { account_expiry: values.account_expiry }).then(() => {
						frm.reload_doc();
					});
				},
				__("Account Expiry"),
				__("Update")
			);
		});

		frm.add_custom_button(frm.doc.enabled ? __("Deactivate") : __("Activate"), () => {
			frm.call("set_active", { active: frm.doc.enabled ? 0 : 1 }).then(() => {
				frm.reload_doc();
			});
		});
	},
});
