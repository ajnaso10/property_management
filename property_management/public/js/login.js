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

	function useServerHomePage() {
		if (!window.login || !login.login_handlers || login.login_handlers.__propertyDesk) {
			return;
		}
		const original = login.login_handlers[200];
		if (typeof original !== "function") {
			return;
		}
		// The stock login script prefers ?redirect-to= over home_page.
		// Put the server home page into that query so sign-in opens the property desk.
		login.login_handlers[200] = function (data) {
			if (data && data.message === "Logged In" && data.home_page) {
				const url = new URL(window.location.href);
				url.searchParams.set("redirect-to", data.home_page);
				window.history.replaceState(null, "", url.pathname + url.search + url.hash);
			}
			return original.apply(this, arguments);
		};
		login.login_handlers.__propertyDesk = true;
	}

	function prepareLoginPage() {
		hidePasswordReset();
		useServerHomePage();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", prepareLoginPage);
	} else {
		prepareLoginPage();
	}
	document.addEventListener("login_rendered", prepareLoginPage);
})();
