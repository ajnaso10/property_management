"""Upgrade Rent Invoice before Frappe's schema sync adds unique columns.

SQLite rejects ``ALTER TABLE ... ADD COLUMN ... UNIQUE``. MariaDB and Postgres
can add the column, but a unique index still fails if existing rows collide.
This module adds the columns without the unique constraint, fills them, and
stops if a value would be shared or cannot be derived. It does not delete
invoices or change amounts, status, or payments. Frappe's schema sync then
creates the unique indexes.
"""

from __future__ import annotations


class InvoiceKeyConflict(Exception):
	"""Existing invoices cannot take a unique billing key or invoice number."""

	def __init__(self, conflicts: list[str]):
		self.conflicts = conflicts
		super().__init__("\n".join(conflicts))


def plan_invoice_keys(rows: list[dict]) -> list[dict]:
	"""Return updates for blank keys. Raise if any value is duplicated or incomplete.

	A non-blank invoice number or billing key is kept. A blank invoice number
	becomes the invoice name. A blank billing key becomes ``{allocation}-{month}``.
	Nothing is written here.
	"""
	planned = []
	numbers: dict[str, list[str]] = {}
	keys: dict[str, list[str]] = {}
	incomplete = []

	for row in rows:
		name = row.get("name")
		if _blank(name):
			incomplete.append("A Rent Invoice row has no name, so it was left unchanged.")
			continue
		name = str(name)
		number = row.get("invoice_number")
		if _blank(number):
			number = name
		else:
			number = str(number).strip()

		current_key = row.get("billing_key")
		if _blank(current_key):
			allocation = row.get("bed_allocation")
			month = row.get("billing_month")
			if _blank(allocation) or _blank(month):
				incomplete.append(
					f"{name} has no billing key and is missing bed allocation or billing month. "
					"The row was left unchanged."
				)
				continue
			billing_key = f"{str(allocation).strip()}-{str(month).strip()}"
		else:
			billing_key = str(current_key).strip()

		planned.append(
			{
				"name": name,
				"invoice_number": number,
				"billing_key": billing_key,
				"docstatus": row.get("docstatus"),
				"bed_allocation": row.get("bed_allocation"),
				"billing_month": row.get("billing_month"),
				"changed": _blank(row.get("invoice_number")) or _blank(row.get("billing_key")),
			}
		)
		numbers.setdefault(number, []).append(name)
		keys.setdefault(billing_key, []).append(name)

	conflicts = list(incomplete)
	conflicts.extend(_duplicate_lines("invoice number", numbers, planned))
	conflicts.extend(_duplicate_lines("billing key", keys, planned))
	if conflicts:
		raise InvoiceKeyConflict(
			[
				"Rent Invoice migration stopped. No invoice was deleted, and no amount, status, or payment was changed.",
				*conflicts,
				"Fix the invoices listed above, then run bench migrate again.",
			]
		)
	return [row for row in planned if row["changed"]]


def backfill_rent_invoice_keys():
	"""Add plain columns if needed and fill keys. Safe to run again."""
	import frappe
	from frappe.database.schema import get_definition

	if not frappe.db.table_exists("Rent Invoice"):
		return {"created_columns": [], "updated": []}

	column_type = get_definition("Data")
	created = []
	for fieldname in ("invoice_number", "billing_key"):
		if fieldname in set(frappe.db.get_table_columns("Rent Invoice")):
			continue
		# Commit before DDL. MariaDB commits DDL itself; a later error must still
		# leave the plain column so the next migrate can continue the backfill.
		frappe.db.commit()
		_add_plain_column(frappe, fieldname, column_type)
		created.append(fieldname)

	rows = frappe.db.sql(
		"""
		SELECT name, invoice_number, billing_key, bed_allocation, billing_month, docstatus
		FROM `tabRent Invoice`
		""",
		as_dict=True,
	)
	try:
		updates = plan_invoice_keys(rows)
	except InvoiceKeyConflict as exc:
		frappe.throw(str(exc), title="Rent Invoice migration stopped")

	for update in updates:
		frappe.db.sql(
			"""
			UPDATE `tabRent Invoice`
			SET invoice_number=%s, billing_key=%s
			WHERE name=%s
			""",
			(update["invoice_number"], update["billing_key"], update["name"]),
		)
	return {"created_columns": created, "updated": [row["name"] for row in updates]}


def sqlite_upgrade_smoke() -> None:
	"""Reproduce the SQLite failure and the safe sequence. Does not use Frappe."""
	import sqlite3

	connection = sqlite3.connect(":memory:")
	connection.row_factory = sqlite3.Row
	connection.execute(
		"""
		CREATE TABLE `tabRent Invoice` (
			name TEXT PRIMARY KEY,
			bed_allocation TEXT,
			billing_month TEXT,
			docstatus INTEGER,
			rent_amount REAL
		)
		"""
	)
	connection.execute(
		"INSERT INTO `tabRent Invoice` VALUES ('RINV-00001', 'ALC-00001', '2026-11', 1, 1000)"
	)
	connection.execute(
		"INSERT INTO `tabRent Invoice` VALUES ('RINV-00002', 'ALC-00002', '2026-11', 1, 800)"
	)
	try:
		connection.execute("ALTER TABLE `tabRent Invoice` ADD COLUMN billing_key varchar(140) UNIQUE")
	except sqlite3.OperationalError as exc:
		if "unique" not in str(exc).lower():
			raise
	else:
		raise AssertionError("SQLite accepted ALTER TABLE ADD COLUMN UNIQUE")

	for fieldname in ("invoice_number", "billing_key"):
		_sqlite_add_plain_column(connection, fieldname)
		_sqlite_add_plain_column(connection, fieldname)

	_sqlite_apply(connection)
	_sqlite_apply(connection)
	amounts = dict(connection.execute("SELECT name, rent_amount FROM `tabRent Invoice`"))
	if amounts != {"RINV-00001": 1000, "RINV-00002": 800}:
		raise AssertionError(amounts)

	connection.execute(
		"""
		INSERT INTO `tabRent Invoice`
			(name, bed_allocation, billing_month, docstatus, rent_amount)
		VALUES ('RINV-00003', 'ALC-00001', '2026-11', 0, 50)
		"""
	)
	try:
		_sqlite_apply(connection)
	except InvoiceKeyConflict as exc:
		text = str(exc)
		if "RINV-00001" not in text or "RINV-00003" not in text:
			raise
	else:
		raise AssertionError("Duplicate billing key was accepted")

	kept = connection.execute(
		"SELECT rent_amount FROM `tabRent Invoice` WHERE name='RINV-00003'"
	).fetchone()
	if kept[0] != 50:
		raise AssertionError("Conflicting invoice was changed or removed")
	try:
		connection.execute(
			"UPDATE `tabRent Invoice` SET billing_key='ALC-00001-2026-11' WHERE name='RINV-00003'"
		)
	except sqlite3.IntegrityError:
		pass
	else:
		raise AssertionError("Unique index did not reject the duplicate billing key")


def _sqlite_add_plain_column(connection, fieldname: str) -> None:
	existing = {row[1] for row in connection.execute("PRAGMA table_info(`tabRent Invoice`)")}
	if fieldname in existing:
		return
	connection.execute(f"ALTER TABLE `tabRent Invoice` ADD COLUMN `{fieldname}` varchar(140)")


def _sqlite_apply(connection) -> None:
	rows = [
		dict(row)
		for row in connection.execute(
			"""
			SELECT name, invoice_number, billing_key, bed_allocation, billing_month, docstatus
			FROM `tabRent Invoice`
			"""
		)
	]
	for update in plan_invoice_keys(rows):
		connection.execute(
			"""
			UPDATE `tabRent Invoice`
			SET invoice_number=?, billing_key=?
			WHERE name=?
			""",
			(update["invoice_number"], update["billing_key"], update["name"]),
		)
	connection.execute(
		"CREATE UNIQUE INDEX IF NOT EXISTS `billing_key` ON `tabRent Invoice` (`billing_key`)"
	)
	connection.execute(
		"CREATE UNIQUE INDEX IF NOT EXISTS `invoice_number` ON `tabRent Invoice` (`invoice_number`)"
	)


def _add_plain_column(frappe, fieldname: str, column_type: str) -> None:
	table = "`tabRent Invoice`"
	column = f"`{fieldname}`"
	if frappe.db.db_type == "sqlite":
		frappe.db.sql(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
	else:
		frappe.db.sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {column_type}")


def _duplicate_lines(label: str, groups: dict[str, list[str]], planned: list[dict]) -> list[str]:
	details = {row["name"]: row for row in planned}
	lines = []
	for value, names in sorted(groups.items()):
		if len(names) < 2:
			continue
		described = ", ".join(_describe(name, details.get(name)) for name in names)
		lines.append(f"Duplicate {label} {value!r} is shared by {described}.")
	return lines


def _describe(name: str, row: dict | None) -> str:
	if not row:
		return name
	return (
		f"{name} (docstatus {row.get('docstatus')}, "
		f"allocation {row.get('bed_allocation')}, month {row.get('billing_month')})"
	)


def _blank(value) -> bool:
	return value is None or str(value).strip() == ""
