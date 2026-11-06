from property_management.analytics import run_report


def execute(filters=None):
	return run_report("transaction_history", filters)
