// Desk redirect. The server gate in before_request is what actually blocks the session.
frappe.ready(() => {
	const gate = frappe.boot && frappe.boot.property_management;
	if (gate && gate.must_change_password && !window.location.pathname.startsWith("/property-password")) {
		window.location.replace("/property-password");
	}
});
