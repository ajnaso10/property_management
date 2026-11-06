from property_management.analytics import run_report


def execute(filters=None):
	return run_report("rent_position", filters)
