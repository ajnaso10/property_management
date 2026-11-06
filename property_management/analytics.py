"""Script reports and dashboard charts.

Every total comes from the same scope and measure functions as the desk overview.
Period rows use the selected dates. Snapshot rows ignore those dates and say so.
Building expenses with no flat are overhead. They are not spread onto flats or areas.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, formatdate, get_first_day, get_last_day, getdate, today

from property_management.desk import (
	MEASURES,
	_area_filters,
	_building_filters,
	_flat_filters,
	_metrics,
	resolve_scope,
)
from property_management.hierarchy import require_readable

MAX_CHART_MONTHS = 36

REPORT_GUIDE = (
	{
		"report": "Financial Position",
		"request": "Total financial position for a property user, and the consolidated position for a super admin",
		"kind": "Period movement and current snapshots",
	},
	{
		"report": "User-wise Financial Summary",
		"request": "User-wise report for a property super admin",
		"kind": "One row per property user, same measures",
	},
	{
		"report": "Flat Profitability",
		"request": "Flat-wise profitability",
		"kind": "Direct profit only. Overhead is not assigned to a flat",
	},
	{
		"report": "Building Profitability",
		"request": "Building profitability",
		"kind": "Full building result, with overhead shown separately",
	},
	{
		"report": "Area Profitability",
		"request": "Area profitability",
		"kind": "Direct profit only where an area is set",
	},
	{
		"report": "Rent Position",
		"request": "Rent invoiced, collections, and outstanding",
		"kind": "Period revenue and cash, plus open receivables",
	},
	{
		"report": "Deposit Liability",
		"request": "Deposit liability and history",
		"kind": "Held balance is a snapshot. Receipts, refunds, and transfers are the period",
	},
	{
		"report": "Expense Register",
		"request": "Expenses",
		"kind": "Signed expense transactions, including reversals",
	},
	{
		"report": "Occupancy",
		"request": "Occupancy and vacancy",
		"kind": "Current bed counts, plus stays taken from allocation dates",
	},
	{
		"report": "Transaction History",
		"request": "Transaction history",
		"kind": "Financial transactions. Not a debit and credit ledger",
	},
	{
		"report": "Tenant History",
		"request": "Tenant history, including vacated receivables",
		"kind": "Stays plus the transactions for that tenant",
	},
)


def run_report(report, filters=None):
	handlers = {
		"financial_position": financial_position,
		"user_wise_financial_summary": user_wise_financial_summary,
		"flat_profitability": flat_profitability,
		"building_profitability": building_profitability,
		"area_profitability": area_profitability,
		"rent_position": rent_position,
		"deposit_liability": deposit_liability,
		"expense_register": expense_register,
		"occupancy": occupancy,
		"transaction_history": transaction_history,
		"tenant_history": tenant_history,
	}
	return handlers[report](filters)


def financial_position(filters=None):
	scope = scope_from(filters)
	metrics = _metrics(scope)
	money = metrics["money"]
	occupancy_now = metrics["occupancy"]
	rows = [
		_measure_row("Recognized rental revenue", "Period", money["recognized_rental_revenue"], "recognized_rental_revenue"),
		_measure_row("Other revenue", "Period", money["other_revenue"], "other_revenue"),
		_measure_row(
			"Deposit transferred to revenue",
			"Period",
			money["deposit_transferred_to_revenue"],
			"deposit_transferred_to_revenue",
		),
		_measure_row("Expenses", "Period", money["expenses"], "expenses"),
		_measure_row("Operating profit", "Period", money["operating_profit"], "operating_profit"),
		_measure_row("Rent collected", "Period", money["rent_collected"], "rent_collected"),
		_measure_row("Allocated receipts", "Period", money["allocated_receipts"], "allocated_receipts"),
		_measure_row("Advances", "Period", money["advances"], "advances"),
		_measure_row("Deposit received", "Period", money["deposit_received"], "deposit_received"),
		_measure_row("Deposit refunded", "Period", money["deposit_refunded"], "deposit_refunded"),
		_measure_row("Outstanding in period", "Period", money["outstanding_in_period"], "outstanding_in_period"),
		_measure_row("All open receivables", "Snapshot", money["outstanding_open"], "outstanding_open"),
		_measure_row("Held deposits", "Snapshot", money["held_deposits"], "held_deposits"),
		_measure_row("Monthly fixed rent", "Snapshot", money["monthly_fixed_rent"], "monthly_fixed_rent"),
		_count_row("Buildings", occupancy_now["buildings"]),
		_count_row("Flats", occupancy_now["flats"]),
		_count_row("Areas", occupancy_now["areas"]),
		_count_row("Beds", occupancy_now["beds"]),
		_count_row("Occupied beds", occupancy_now["beds_occupied"]),
		_count_row("Vacant beds", occupancy_now["beds_vacant"]),
		_count_row("Maintenance beds", occupancy_now["beds_maintenance"]),
	]
	message = _(
		"Operating profit is recognized rental revenue, plus other revenue, plus deposit transferred to revenue, minus expenses. It is not cash profit. Rent collected, advances, and held deposits are separate. {0} to {1}."
	).format(formatdate(scope.from_date), formatdate(scope.to_date))
	return _measure_columns(), rows, message, None


def user_wise_financial_summary(filters=None):
	scope = scope_from(filters)
	rows = []
	for summary in user_summaries(scope):
		rows.append(
			{
				"user": summary["user"],
				"full_name": summary["full_name"],
				"mobile_number": summary["mobile_number"],
				"recognized_rental_revenue": summary["money"]["recognized_rental_revenue"],
				"other_revenue": summary["money"]["other_revenue"],
				"deposit_transferred_to_revenue": summary["money"]["deposit_transferred_to_revenue"],
				"expenses": summary["money"]["expenses"],
				"operating_profit": summary["money"]["operating_profit"],
				"rent_collected": summary["money"]["rent_collected"],
				"advances": summary["money"]["advances"],
				"outstanding_open": summary["money"]["outstanding_open"],
				"held_deposits": summary["money"]["held_deposits"],
				"monthly_fixed_rent": summary["money"]["monthly_fixed_rent"],
				"beds": summary["occupancy"]["beds"],
				"beds_occupied": summary["occupancy"]["beds_occupied"],
				"beds_vacant": summary["occupancy"]["beds_vacant"],
			}
		)
	message = _(
		"Each row uses the same measures as Financial Position. A property user only receives their own row. Operating profit is not cash profit."
	)
	columns = [
		_link(_("User"), "user", "User", 180),
		_data(_("Name"), "full_name", 160),
		_data(_("Mobile"), "mobile_number", 120),
		_currency(_("Recognized rent"), "recognized_rental_revenue"),
		_currency(_("Other revenue"), "other_revenue"),
		_currency(_("Deposit transferred"), "deposit_transferred_to_revenue"),
		_currency(_("Expenses"), "expenses"),
		_currency(_("Operating profit"), "operating_profit"),
		_currency(_("Rent collected"), "rent_collected"),
		_currency(_("Advances"), "advances"),
		_currency(_("Open receivables"), "outstanding_open"),
		_currency(_("Held deposits"), "held_deposits"),
		_currency(_("Fixed rent"), "monthly_fixed_rent"),
		_int(_("Beds"), "beds"),
		_int(_("Occupied"), "beds_occupied"),
		_int(_("Vacant"), "beds_vacant"),
	]
	return columns, rows, message, None


def flat_profitability(filters=None):
	return _profitability(filters, "flat")


def building_profitability(filters=None):
	return _profitability(filters, "building")


def area_profitability(filters=None):
	return _profitability(filters, "area")


def rent_position(filters=None):
	scope = scope_from(filters)
	money = _metrics(scope)["money"]
	rows = [
		_rent_summary("Recognized rental revenue", "Period", money["recognized_rental_revenue"]),
		_rent_summary("Rent collected", "Period", money["rent_collected"]),
		_rent_summary("Allocated receipts", "Period", money["allocated_receipts"]),
		_rent_summary("Advances", "Period", money["advances"]),
		_rent_summary("Outstanding in period", "Period", money["outstanding_in_period"]),
		_rent_summary("All open receivables", "Snapshot", money["outstanding_open"]),
	]
	for invoice in _invoices(scope, dated=True):
		rows.append(
			{
				"row_type": "Invoice",
				"label": invoice.name,
				"kind": "Period",
				"amount": flt(invoice.rent_amount, 2),
				"rent_invoice": invoice.name,
				"tenant": invoice.tenant,
				"tenant_name": invoice.tenant_name,
				"billing_month": invoice.billing_month,
				"rent_amount": flt(invoice.rent_amount, 2),
				"amount_paid": flt(invoice.amount_paid, 2),
				"outstanding": flt(invoice.outstanding, 2),
				"status": invoice.status,
			}
		)
	message = _(
		"Recognized rent is the invoiced revenue in the period, after receivable reversals. Rent collected is cash. Allocated receipts are the portions applied to invoices. Advances are unapplied payment amounts. Open receivables are what is still unpaid, including a vacated tenant."
	)
	columns = [
		_data(_("Row"), "row_type", 90),
		_data(_("Label"), "label", 180),
		_data(_("Kind"), "kind", 90),
		_currency(_("Amount"), "amount"),
		_link(_("Invoice"), "rent_invoice", "Rent Invoice", 140),
		_data(_("Tenant"), "tenant_name", 160),
		_data(_("Month"), "billing_month", 90),
		_currency(_("Rent"), "rent_amount"),
		_currency(_("Paid"), "amount_paid"),
		_currency(_("Outstanding"), "outstanding"),
		_data(_("Status"), "status", 100),
	]
	return columns, rows, message, None


def deposit_liability(filters=None):
	scope = scope_from(filters)
	money = _metrics(scope)["money"]
	rows = [
		{
			"row_type": "Summary",
			"label": "Held deposits",
			"kind": "Snapshot",
			"amount": money["held_deposits"],
			"posting_date": None,
			"transaction_type": None,
			"reference_name": None,
		},
		{
			"row_type": "Summary",
			"label": "Deposit received",
			"kind": "Period",
			"amount": money["deposit_received"],
			"posting_date": None,
			"transaction_type": None,
			"reference_name": None,
		},
		{
			"row_type": "Summary",
			"label": "Deposit refunded",
			"kind": "Period",
			"amount": money["deposit_refunded"],
			"posting_date": None,
			"transaction_type": None,
			"reference_name": None,
		},
		{
			"row_type": "Summary",
			"label": "Deposit transferred to revenue",
			"kind": "Period",
			"amount": money["deposit_transferred_to_revenue"],
			"posting_date": None,
			"transaction_type": None,
			"reference_name": None,
		},
	]
	for entry in _transactions(
		scope,
		("Deposit Received", "Deposit Refunded", "Deposit Transferred to Revenue"),
		dated=True,
	):
		rows.append(
			{
				"row_type": "Transaction",
				"label": entry.transaction_type,
				"kind": "Period",
				"amount": flt(entry.amount, 2),
				"posting_date": _text_date(entry.posting_date),
				"transaction_type": entry.transaction_type,
				"reference_name": entry.name,
				"tenant": entry.tenant,
				"building": entry.building,
				"flat": entry.flat,
				"area": entry.area,
			}
		)
	message = _(
		"Held deposits are the balance still kept, ignoring the date range. A receipt is not revenue. Only a transfer to revenue is included in operating profit, and only in Financial Position."
	)
	columns = [
		_data(_("Row"), "row_type", 110),
		_data(_("Label"), "label", 220),
		_data(_("Kind"), "kind", 90),
		_currency(_("Amount"), "amount"),
		_date(_("Date"), "posting_date"),
		_data(_("Type"), "transaction_type", 180),
		_link(_("Transaction"), "reference_name", "Financial Transaction", 140),
		_link(_("Tenant"), "tenant", "Tenant", 140),
		_link(_("Building"), "building", "Building", 140),
		_link(_("Flat"), "flat", "Flat", 120),
		_link(_("Area"), "area", "Area", 120),
	]
	return columns, rows, message, None


def expense_register(filters=None):
	scope = scope_from(filters)
	rows = []
	for entry in _transactions(scope, ("Expense",), dated=True):
		rows.append(
			{
				"posting_date": _text_date(entry.posting_date),
				"amount": flt(entry.amount, 2),
				"placement": _expense_placement(entry),
				"building": entry.building,
				"flat": entry.flat,
				"area": entry.area,
				"reference_name": entry.name,
				"remarks": entry.remarks,
			}
		)
	net = flt(sum(row["amount"] for row in rows), 2)
	overhead = _overhead_amount(scope, "flat")
	message = _(
		"Net expenses are {0}. Building overhead with no flat is {1}. A reversal is a negative Expense on the original date, so it nets once. Overhead is not assigned to a flat."
	).format(net, overhead)
	columns = [
		_date(_("Date"), "posting_date"),
		_currency(_("Amount"), "amount"),
		_data(_("Placement"), "placement", 160),
		_link(_("Building"), "building", "Building", 140),
		_link(_("Flat"), "flat", "Flat", 120),
		_link(_("Area"), "area", "Area", 120),
		_link(_("Transaction"), "reference_name", "Financial Transaction", 140),
		_data(_("Remarks"), "remarks", 220),
	]
	return columns, rows, message, None


def occupancy(filters=None):
	scope = scope_from(filters)
	current = _metrics(scope)["occupancy"]
	rows = [
		_count_row("Beds", current["beds"]),
		_count_row("Occupied beds", current["beds_occupied"]),
		_count_row("Vacant beds", current["beds_vacant"]),
		_count_row("Maintenance beds", current["beds_maintenance"]),
	]
	for stay in _overlapping_stays(scope):
		rows.append(
			{
				"label": stay.tenant_name or stay.tenant,
				"kind": "Stay",
				"amount": None,
				"allocation": stay.name,
				"tenant": stay.tenant,
				"tenant_name": stay.tenant_name,
				"bed": stay.bed,
				"building": stay.building,
				"flat": stay.flat,
				"area": stay.area,
				"allocation_status": stay.allocation_status,
				"allocation_date": _text_date(stay.allocation_date),
				"vacating_date": _text_date(stay.vacating_date),
				"monthly_rent": flt(stay.monthly_rent, 2),
			}
		)
	message = _(
		"Bed counts are the occupancy right now. They are not a history. Stays are bed allocations whose dates overlap {0} to {1}, including a vacated tenant. There is no occupancy rate for past months."
	).format(formatdate(scope.from_date), formatdate(scope.to_date))
	columns = _measure_columns() + [
		_link(_("Allocation"), "allocation", "Bed Allocation", 140),
		_link(_("Tenant"), "tenant", "Tenant", 140),
		_link(_("Bed"), "bed", "Bed", 120),
		_link(_("Building"), "building", "Building", 140),
		_link(_("Flat"), "flat", "Flat", 120),
		_link(_("Area"), "area", "Area", 120),
		_data(_("Stay status"), "allocation_status", 110),
		_date(_("Allocation date"), "allocation_date"),
		_date(_("Vacating date"), "vacating_date"),
		_currency(_("Monthly rent"), "monthly_rent"),
	]
	chart = {
		"data": {
			"labels": [_("Occupied"), _("Vacant"), _("Maintenance")],
			"datasets": [
				{
					"name": _("Current beds"),
					"values": [
						current["beds_occupied"],
						current["beds_vacant"],
						current["beds_maintenance"],
					],
				}
			],
		},
		"type": "donut",
	}
	return columns, rows, message, chart


def transaction_history(filters=None):
	scope = scope_from(filters, tenant=True)
	rows = [_history_row(entry) for entry in _transactions(scope, None, dated=True)]
	message = _(
		"Each row is one submitted financial transaction from {0} to {1}. Amounts keep their sign, so a reversal nets once. This is not a debit and credit ledger, and the rows are not one running balance."
	).format(formatdate(scope.from_date), formatdate(scope.to_date))
	return _history_columns(), rows, message, None


def tenant_history(filters=None):
	scope = scope_from(filters, tenant=True)
	rows = []
	stays = _tenant_stays(scope) if scope.tenant else _overlapping_stays(scope)
	for stay in stays:
		rows.append(
			{
				"row_type": "Stay",
				"posting_date": _text_date(stay.allocation_date),
				"transaction_type": stay.allocation_status,
				"amount": flt(stay.monthly_rent, 2),
				"tenant": stay.tenant,
				"tenant_name": stay.tenant_name,
				"building": stay.building,
				"flat": stay.flat,
				"area": stay.area,
				"bed": stay.bed,
				"reference_doctype": "Bed Allocation",
				"reference_name": stay.name,
				"remarks": _text_date(stay.vacating_date),
			}
		)
	for entry in _transactions(scope, None, dated=True):
		row = _history_row(entry)
		row["row_type"] = "Transaction"
		rows.append(row)
	outstanding = _metrics(scope)["money"]["outstanding_open"]
	rows.insert(
		0,
		{
			"row_type": "Snapshot",
			"posting_date": None,
			"transaction_type": "All open receivables",
			"amount": outstanding,
			"tenant": scope.tenant,
			"remarks": "Still unpaid. The date range does not clear a vacated tenant.",
		},
	)
	who = scope.tenant or _("every visible tenant")
	message = _(
		"Stays for {0} remain after vacating. Transactions are the selected period. Open receivables are the current unpaid balance, not a second copy of the transactions."
	).format(who)
	columns = [_data(_("Row"), "row_type", 110)] + _history_columns()
	return columns, rows, message, None


def monthly_movement(filters=None):
	"""Period movement for each month in the range. Defaults to the six months ending this month."""
	filters = _with_chart_range(filters)
	scope = scope_from(filters)
	labels = []
	recognized = []
	collected = []
	expenses = []
	profit = []
	for month in _months(scope.from_date, scope.to_date):
		child = frappe._dict(scope)
		child.from_date = get_first_day(month)
		child.to_date = get_last_day(month)
		money = _metrics(child)["money"]
		labels.append(month.strftime("%Y-%m"))
		recognized.append(money["recognized_rental_revenue"])
		collected.append(money["rent_collected"])
		expenses.append(money["expenses"])
		profit.append(money["operating_profit"])
	return {
		"labels": labels,
		"datasets": [
			{"name": _("Recognized rental revenue"), "values": recognized},
			{"name": _("Rent collected"), "values": collected},
			{"name": _("Expenses"), "values": expenses},
			{"name": _("Operating profit"), "values": profit},
		],
	}


def flat_profit_chart(filters=None):
	scope = scope_from(filters)
	rows, _overhead = _direct_rows(scope, "flat")
	return {
		"labels": [row["label"] for row in rows],
		"datasets": [
			{
				"name": _("Direct operating profit, excluding overhead"),
				"values": [row["direct_operating_profit"] for row in rows],
			}
		],
	}


def current_occupancy_chart(filters=None):
	scope = scope_from(filters)
	current = _metrics(scope)["occupancy"]
	return {
		"labels": [_("Occupied"), _("Vacant"), _("Maintenance")],
		"datasets": [
			{
				"name": _("Current beds"),
				"values": [current["beds_occupied"], current["beds_vacant"], current["beds_maintenance"]],
			}
		],
	}


def scope_from(filters, tenant=False):
	filters = _filters(filters)
	scope = resolve_scope(
		filters.get("owner_user"),
		filters.get("building"),
		filters.get("flat"),
		filters.get("area"),
		filters.get("from_date"),
		filters.get("to_date"),
	)
	scope.tenant = _resolve_tenant(scope, filters.get("tenant")) if tenant else None
	return scope


def user_summaries(scope):
	if scope.privileged and not scope.owner and not scope.location_owner:
		profiles = frappe.get_all(
			"Property User Profile",
			fields=["user", "mobile_number"],
			order_by="mobile_number asc",
		)
	elif scope.privileged and (scope.owner or scope.location_owner):
		owner = scope.owner or scope.location_owner
		profiles = frappe.get_all(
			"Property User Profile",
			filters={"user": owner},
			fields=["user", "mobile_number"],
		)
	else:
		profiles = frappe.get_all(
			"Property User Profile",
			filters={"user": scope.owner},
			fields=["user", "mobile_number"],
		)
		if not profiles and scope.owner:
			profiles = [frappe._dict(user=scope.owner, mobile_number=None)]
	names = {}
	if profiles:
		for row in frappe.get_all(
			"User",
			filters={"name": ["in", [profile.user for profile in profiles]]},
			fields=["name", "full_name"],
		):
			names[row.name] = row.full_name
	summaries = []
	for profile in profiles:
		child = frappe._dict(scope)
		child.owner = profile.user
		metrics = _metrics(child)
		summaries.append(
			{
				"user": profile.user,
				"full_name": names.get(profile.user) or profile.user,
				"mobile_number": profile.mobile_number,
				"money": metrics["money"],
				"occupancy": metrics["occupancy"],
			}
		)
	return summaries


def _profitability(filters, level):
	scope = scope_from(filters)
	rows, overhead = _direct_rows(scope, level)
	if level == "building":
		message = _(
			"With no flat selected, building operating profit includes expenses that have no flat. That overhead is also shown in its own column and is not added a second time. It is not spread onto flats. Operating profit is not cash profit."
		)
		chart_values = [row["operating_profit"] for row in rows]
		chart_name = _("Building operating profit")
	else:
		place = "flat" if level == "flat" else "area"
		message = _(
			"Direct operating profit uses only transactions tagged to a {0}. Unallocated overhead is {1}. It is not spread across these rows. Operating profit is not cash profit."
		).format(place, overhead)
		chart_values = [row["direct_operating_profit"] for row in rows]
		chart_name = _("Direct operating profit")
	chart = None
	if rows:
		chart = {
			"data": {
				"labels": [row["label"] for row in rows],
				"datasets": [{"name": chart_name, "values": chart_values}],
			},
			"type": "bar",
		}
	return _profit_columns(level), rows, message, chart


def _direct_rows(scope, level):
	locations = _locations(scope, level)
	rows = []
	for location in locations:
		child = _child_scope(scope, level, location)
		money = _metrics(child)["money"]
		row = {
			"location": location["name"],
			"label": location["label"],
			"building": location.get("building") or (location["name"] if level == "building" else None),
			"owner_user": location.get("owner_user"),
			"recognized_rental_revenue": money["recognized_rental_revenue"],
			"other_revenue": money["other_revenue"],
			"deposit_transferred_to_revenue": money["deposit_transferred_to_revenue"],
			"outstanding_open": money["outstanding_open"],
			"held_deposits": money["held_deposits"],
		}
		if level == "building":
			row["expenses"] = money["expenses"]
			row["overhead_not_on_a_flat"] = _overhead_amount(child, "flat")
			row["operating_profit"] = money["operating_profit"]
		else:
			row["direct_expenses"] = money["expenses"]
			row["direct_operating_profit"] = money["operating_profit"]
		rows.append(row)
	overhead = 0.0 if level == "building" else _overhead_amount(scope, level)
	return rows, overhead


def _locations(scope, level):
	if level == "building":
		rows = frappe.get_all(
			"Building",
			filters=_building_filters(scope),
			fields=["name", "building_name", "owner_user"],
			order_by="building_name asc",
		)
		return [_location_dict(row.name, row.building_name, row.owner_user, building=row.name) for row in rows]
	if level == "flat":
		rows = frappe.get_all(
			"Flat",
			filters=_flat_filters(scope),
			fields=["name", "flat_number", "building", "owner_user"],
			order_by="flat_number asc",
		)
		return [
			_location_dict(row.name, row.flat_number, row.owner_user, building=row.building) for row in rows
		]
	rows = frappe.get_all(
		"Area",
		filters=_area_filters(scope),
		fields=["name", "area_name", "flat", "building", "owner_user"],
		order_by="area_name asc",
	)
	return [
		_location_dict(row.name, row.area_name, row.owner_user, building=row.building, flat=row.flat)
		for row in rows
	]


def _location_dict(name, label, owner_user, building=None, flat=None):
	return {
		"name": name,
		"label": label,
		"owner_user": owner_user,
		"building": building,
		"flat": flat,
	}


def _child_scope(scope, level, location):
	child = frappe._dict(scope)
	child.owner = location.get("owner_user") or scope.owner
	if level == "building":
		child.building = location["name"]
		child.flat = scope.flat
		child.area = scope.area
	elif level == "flat":
		child.building = location.get("building")
		child.flat = location["name"]
		child.area = scope.area
	else:
		child.building = location.get("building")
		child.flat = location.get("flat")
		child.area = location["name"]
	child.has_location = bool(child.building or child.flat or child.area)
	return child


def _overhead_amount(scope, level):
	"""Net expenses in the parent scope that are not tagged at this level."""
	filters = {
		"docstatus": 1,
		"transaction_type": "Expense",
		"posting_date": ["between", [scope.from_date, scope.to_date]],
	}
	if scope.owner:
		filters["owner_user"] = scope.owner
	building = scope.building
	if not building and scope.flat:
		building = frappe.db.get_value("Flat", scope.flat, "building")
	if not building and scope.area:
		building = frappe.db.get_value("Area", scope.area, "building")
	if building:
		filters["building"] = building
	if level == "flat":
		filters["flat"] = ["is", "not set"]
	elif level == "area":
		filters["area"] = ["is", "not set"]
		if scope.flat and not scope.building:
			filters["building"] = frappe.db.get_value("Flat", scope.flat, "building")
	rows = frappe.get_all("Financial Transaction", filters=filters, fields=["amount"])
	return flt(sum(flt(row.amount) for row in rows), 2)


def _transactions(scope, types, dated):
	filters = {"docstatus": 1}
	if types:
		filters["transaction_type"] = ["in", list(types)]
	if scope.owner:
		filters["owner_user"] = scope.owner
	if scope.building:
		filters["building"] = scope.building
	if scope.flat:
		filters["flat"] = scope.flat
	if scope.area:
		filters["area"] = scope.area
	if getattr(scope, "tenant", None):
		filters["tenant"] = scope.tenant
	if dated:
		filters["posting_date"] = ["between", [scope.from_date, scope.to_date]]
	rows = frappe.get_all(
		"Financial Transaction",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"transaction_type",
			"amount",
			"tenant",
			"building",
			"flat",
			"area",
			"bed",
			"reference_doctype",
			"reference_name",
			"remarks",
			"owner_user",
		],
		order_by="posting_date asc, name asc",
	)
	_attach_names(rows)
	return rows


def _invoices(scope, dated):
	filters = {"docstatus": 1}
	if scope.owner:
		filters["owner_user"] = scope.owner
	if scope.building:
		filters["building"] = scope.building
	if scope.flat:
		filters["flat"] = scope.flat
	if scope.area:
		filters["area"] = scope.area
	if getattr(scope, "tenant", None):
		filters["tenant"] = scope.tenant
	if dated:
		filters["billing_date"] = ["between", [scope.from_date, scope.to_date]]
	rows = frappe.get_all(
		"Rent Invoice",
		filters=filters,
		fields=[
			"name",
			"tenant",
			"billing_month",
			"rent_amount",
			"amount_paid",
			"outstanding",
			"status",
			"billing_date",
		],
		order_by="billing_date asc, name asc",
	)
	_attach_names(rows)
	return rows


def _overlapping_stays(scope):
	filters = {"allocation_date": ["<=", scope.to_date]}
	if scope.owner:
		filters["owner_user"] = scope.owner
	if scope.building:
		filters["building"] = scope.building
	if scope.flat:
		filters["flat"] = scope.flat
	if scope.area:
		filters["area"] = scope.area
	if getattr(scope, "tenant", None):
		filters["tenant"] = scope.tenant
	rows = frappe.get_all(
		"Bed Allocation",
		filters=filters,
		fields=[
			"name",
			"tenant",
			"bed",
			"building",
			"flat",
			"area",
			"allocation_status",
			"allocation_date",
			"vacating_date",
			"monthly_rent",
			"owner_user",
		],
		order_by="allocation_date asc, name asc",
	)
	kept = []
	for row in rows:
		if row.vacating_date and getdate(row.vacating_date) < getdate(scope.from_date):
			continue
		kept.append(row)
	_attach_names(kept)
	return kept


def _tenant_stays(scope):
	filters = {"tenant": scope.tenant}
	if scope.owner:
		filters["owner_user"] = scope.owner
	rows = frappe.get_all(
		"Bed Allocation",
		filters=filters,
		fields=[
			"name",
			"tenant",
			"bed",
			"building",
			"flat",
			"area",
			"allocation_status",
			"allocation_date",
			"vacating_date",
			"monthly_rent",
		],
		order_by="allocation_date asc, name asc",
	)
	_attach_names(rows)
	return rows


def _resolve_tenant(scope, tenant):
	if not tenant:
		return None
	tenant = str(tenant).strip()
	if not tenant:
		return None
	require_readable("Tenant", tenant)
	owner = frappe.db.get_value("Tenant", tenant, "owner_user")
	if scope.owner and owner != scope.owner:
		frappe.throw(_("That tenant belongs to another property user."), frappe.ValidationError)
	return tenant


def _attach_names(rows):
	tenant_ids = [row.tenant for row in rows if row.get("tenant")]
	if not tenant_ids:
		return
	names = {
		row.name: row.tenant_name
		for row in frappe.get_all(
			"Tenant",
			filters={"name": ["in", list(set(tenant_ids))]},
			fields=["name", "tenant_name"],
		)
	}
	for row in rows:
		if row.get("tenant"):
			row.tenant_name = names.get(row.tenant)


def _history_row(entry):
	return {
		"row_type": "Transaction",
		"posting_date": _text_date(entry.posting_date),
		"transaction_type": entry.transaction_type,
		"amount": flt(entry.amount, 2),
		"tenant": entry.tenant,
		"tenant_name": entry.get("tenant_name"),
		"building": entry.building,
		"flat": entry.flat,
		"area": entry.area,
		"bed": entry.bed,
		"reference_doctype": entry.reference_doctype,
		"reference_name": entry.reference_name,
		"remarks": entry.remarks,
	}


def _expense_placement(entry):
	if entry.area:
		return "Area"
	if entry.flat:
		return "Flat, no area"
	if entry.building:
		return "Building overhead"
	return "No building"


def _with_chart_range(filters):
	filters = _filters(filters)
	if not filters.get("from_date") and not filters.get("to_date"):
		filters["from_date"] = get_first_day(add_months(today(), -5))
		filters["to_date"] = get_last_day(today())
	return filters


def _months(start, end):
	months = []
	cursor = getdate(get_first_day(start))
	last = getdate(get_first_day(end))
	while cursor <= last:
		months.append(cursor)
		if len(months) > MAX_CHART_MONTHS:
			frappe.throw(_("Choose a range of {0} months or fewer.").format(MAX_CHART_MONTHS))
		cursor = getdate(add_months(cursor, 1))
	return months


def _filters(filters):
	if not filters:
		return {}
	if isinstance(filters, str):
		return frappe.parse_json(filters) or {}
	return dict(filters)


def _measure_row(label, kind, amount, measure_key):
	return {
		"label": label,
		"kind": kind,
		"amount": flt(amount, 2),
		"detail": MEASURES.get(measure_key, ""),
	}


def _count_row(label, amount):
	return {"label": label, "kind": "Snapshot", "amount": None, "count": amount, "detail": MEASURES["occupancy"]}


def _rent_summary(label, kind, amount):
	return {
		"row_type": "Summary",
		"label": label,
		"kind": kind,
		"amount": flt(amount, 2),
		"rent_invoice": None,
		"tenant_name": None,
		"billing_month": None,
		"rent_amount": None,
		"amount_paid": None,
		"outstanding": None,
		"status": None,
	}


def _measure_columns():
	return [
		_data(_("Label"), "label", 240),
		_data(_("Kind"), "kind", 100),
		_currency(_("Amount"), "amount"),
		_int(_("Count"), "count"),
		_data(_("Detail"), "detail", 420),
	]


def _profit_columns(level):
	columns = [
		_data(_("Name"), "label", 180),
		_link(_("Record"), "location", {"building": "Building", "flat": "Flat", "area": "Area"}[level], 140),
		_link(_("Building"), "building", "Building", 140),
		_link(_("Owner"), "owner_user", "User", 180),
		_currency(_("Recognized rent"), "recognized_rental_revenue"),
		_currency(_("Other revenue"), "other_revenue"),
		_currency(_("Deposit transferred"), "deposit_transferred_to_revenue"),
	]
	if level == "building":
		columns.extend(
			[
				_currency(_("Expenses"), "expenses"),
				_currency(_("Overhead not on a flat"), "overhead_not_on_a_flat"),
				_currency(_("Operating profit"), "operating_profit"),
			]
		)
	else:
		columns.extend(
			[
				_currency(_("Direct expenses"), "direct_expenses"),
				_currency(_("Direct operating profit"), "direct_operating_profit"),
			]
		)
	columns.extend(
		[
			_currency(_("Open receivables"), "outstanding_open"),
			_currency(_("Held deposits"), "held_deposits"),
		]
	)
	return columns


def _history_columns():
	return [
		_date(_("Date"), "posting_date"),
		_data(_("Type"), "transaction_type", 180),
		_currency(_("Amount"), "amount"),
		_data(_("Tenant"), "tenant_name", 160),
		_link(_("Building"), "building", "Building", 140),
		_link(_("Flat"), "flat", "Flat", 120),
		_link(_("Area"), "area", "Area", 120),
		_link(_("Bed"), "bed", "Bed", 110),
		_data(_("Reference type"), "reference_doctype", 140),
		_dynamic(_("Reference"), "reference_name", "reference_doctype", 140),
		_data(_("Remarks"), "remarks", 220),
	]


def _data(label, fieldname, width):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Data", "width": width}


def _currency(label, fieldname):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Currency", "width": 140}


def _int(label, fieldname):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Int", "width": 80}


def _date(label, fieldname):
	return {"label": label, "fieldname": fieldname, "fieldtype": "Date", "width": 110}


def _link(label, fieldname, options, width):
	return {
		"label": label,
		"fieldname": fieldname,
		"fieldtype": "Link",
		"options": options,
		"width": width,
	}


def _dynamic(label, fieldname, options, width):
	return {
		"label": label,
		"fieldname": fieldname,
		"fieldtype": "Dynamic Link",
		"options": options,
		"width": width,
	}


def _text_date(value):
	if not value:
		return None
	return str(getdate(value))
