from property_management.invoice_migration import backfill_rent_invoice_keys


def execute():
	"""Run before schema sync so unique columns are not added to a populated table."""
	backfill_rent_invoice_keys()
