// Hide the standard forgot-password control. The reset API is also refused for property accounts.
(function () {
	function hidePasswordReset() {
		const nodes = document.querySelectorAll("a, button");
		nodes.forEach((node) => {
			const text = (node.textContent || "").toLowerCase();
			const href = (node.getAttribute("href") || "").toLowerCase();
			if (text.includes("forgot") || href.includes("forgot") || node.classList.contains("forgot-password-message")) {
				node.style.display = "none";
			}
		});
		document.querySelectorAll(".form-forgot, .page-card-body .forgot-password").forEach((node) => {
			node.style.display = "none";
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", hidePasswordReset);
	} else {
		hidePasswordReset();
	}
	document.addEventListener("login_rendered", hidePasswordReset);
})();
