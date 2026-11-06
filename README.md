# Property Management

Standalone [Frappe Framework](https://frappeframework.com) v16 app for a property super admin and the people who run buildings. It does not depend on ERPNext, and it does not post journal entries.

Phase 1 is accounts. Phase 2 is the building hierarchy. Phase 3 is tenant placement and vacating. Phase 4 records rent, deposits, and expenses as transactions. Phase 5 generates monthly rent invoices. Phase 6 is the Super Admin Panel and the User Report. There is no chart of accounts and no ERPNext ledger.

## What you can do

**Property Super Admin**

- Create a property user. The username is the mobile number. The initial password is set with Frappe's password API, not a custom field.
- Move the account expiry date, deactivate the user, or set a new temporary password.
- See every building, flat, area, bed, tenant, and allocation.
- Open **Super Admin Panel** to create logins and read total and user-wise figures.

**Property User**

- Signs in with the mobile number.
- Must replace the temporary password before using the desk.
- Cannot use Forgot Password. A Property Super Admin resets it.
- Creates buildings, then flats, areas, and beds, and names a tenant on a vacant bed.
- Sees only records whose Owner User is themselves. That filter is applied in the database, again when a document is opened, and again by the desk overview even if a request names someone else's building.
- Open **User Report** for that hierarchy, allocations, rent schedules, collections, deposits, and expenses.

Login is refused when Account Expiry is before today. The expiry date itself is still a valid day.

## DocTypes

| DocType | Purpose |
| --- | --- |
| Property Settings | Billing day (1–31, clamped to the month), due days after billing, and partial-month proration. Defaults are day 1, 7 days, and proration on. |
| Property User Profile | One row per property login: mobile, expiry, enabled, must-change-password. |
| Building | Name, code, address, location, status, owner. |
| Flat | Flat number under a building. Area and bed counts are calculated. |
| Area | Bedroom, hall, kitchen, shared area, or other. Bed counts are calculated. |
| Bed | Bed number, occupancy (Vacant / Occupied / Maintenance), current tenant, monthly rent. |
| Tenant | Name, mobile, identification number, address, emergency contact, status, current bed. |
| Bed Allocation | One stay on a bed. Several vacated rows can exist for the same tenant. Only one is Active per bed. |

A property user cannot delete a Bed Allocation. Vacate is the way out, so the row remains.

## Install

The site needs Frappe v16 only. Python 3.14 is required by that framework.

```bash
bench init --frappe-branch version-16 frappe-bench
cd frappe-bench
bench get-app <git-url-of-this-app>
bench new-site property.localhost --install-app property_management
bench --site property.localhost set-config developer_mode 1
bench --site property.localhost migrate
```

Do not install ERPNext on this site.

`bench get-app` clones this repository into `apps/property_management`. The repo root is the app (it contains `pyproject.toml` and the `property_management` package).

Install turns on two System Settings flags so a mobile number can be used at the login form:

- Allow Login Using Mobile Number
- Allow Login Using User Name

It also disables public signup. New desk users come from the super admin, not the sign-up form.

## First Property Super Admin

`Administrator` can open the desk and call the APIs. Create a named super admin before handing the site over:

```bash
bench --site property.localhost add-user super.admin@example.com \
  --first-name Super \
  --password 'choose-a-long-password' \
  --add-role 'Property Super Admin'
```

That account signs in with the email address. It is not a property-user profile, so it does not expire and it is not forced through the mobile-number password flow.

If the role was not added by `add-user`:

```bash
bench --site property.localhost console
```

```python
import frappe
user = frappe.get_doc("User", "super.admin@example.com")
user.add_roles("Property Super Admin")
user.save()
frappe.db.commit()
```

## Create a property user

From the desk, as a Property Super Admin, or from the console:

```python
import frappe
from frappe.utils import add_days, today

frappe.set_user("super.admin@example.com")
result = frappe.call(
    "property_management.api.create_property_user",
    full_name="Amina Hassan",
    mobile_number="971501234567",
    password="temporary-pass-1",
    account_expiry=add_days(today(), 365),
)
frappe.db.commit()
print(result["username"], result["user"])
```

Frappe requires every User primary key to be an email. The app stores `971501234567@users.property.local` as that id. The person signs in with `971501234567`, not with the synthetic address. The mobile number is saved on User as both Username and Mobile No.

The temporary password is written with Frappe `User.new_password` / `update_password`. It is not copied onto Property User Profile.

On the next login the desk redirects to `/property-password`. Until that password is changed, other desk and API calls are rejected. There is no second self-service change: the super admin uses **Reset Password** on the profile, or:

```python
frappe.call(
    "property_management.api.reset_property_user_password",
    user="971501234567",
    new_password="another-temporary-1",
)
```

`set_account_expiry` and `set_user_active` are the other two whitelisted methods. The profile form exposes the same three actions.

## Hierarchy

As the property user:

1. Create a Building.
2. Add one or more Flats.
3. Add one or more Areas in a flat (bedroom, hall, kitchen, shared area, other).
4. Add one or more Beds in an area.
5. Create a Tenant (name, mobile, and identification number).
6. Create a Bed Allocation pointing at that tenant and a vacant bed.

The same user can own many buildings. A flat, area, bed, or allocation takes its Owner User from its parent, so a property user cannot attach their flat to someone else's building.

Allocation rules:

- The bed, area, flat, and building must be Active.
- The bed must be Vacant. Maintenance is not allocatable.
- One active allocation per bed, and one active allocation per tenant. Older vacated rows stay.
- To move a tenant, vacate the current allocation, then create a new one on the other bed.
- **Vacate** asks for a vacating date, marks that allocation Vacated, turns off Generate Rent, sets the bed to Vacant, and clears Current Tenant and Current Allocation. Monthly rent and deposit amount stay on the allocation. Nothing writes off a balance. The tenant becomes Vacated when no active allocation remains, and Active again on the next allocation.
- Building, Flat, Area, Bed, Tenant, and Bed Allocation cannot be deleted once an allocation exists.

Flat and area bed counts are recalculated from Bed rows.

## Tests

```bash
bench --site property.localhost run-tests --app property_management
```

The suite covers:

- Property Super Admin and Property User roles exist and have desk access
- A new property user's username is the mobile number, and the profile does not store a password
- A property user cannot create other users
- An expired profile is rejected by the login check
- Guest and logged-in "forgot password" calls are refused; a logged-in password change is not
- Property user A cannot list or open property user B's building; a Property Super Admin can
- A second active allocation on the same bed is rejected, including after occupancy was forced back to Vacant
- An inactive area or flat cannot receive an allocation
- Vacate requires a date, frees the bed, keeps rent and deposit, and a later allocation can use the bed
- A tenant can move beds; both allocation rows remain, and a vacated row cannot be reopened
- A maintenance bed cannot be allocated
- Building, flat, area, bed, tenant, and allocation rows with history cannot be deleted
- A property user cannot open another user's tenant or bed allocation
- Deposit refunds and transfers cannot exceed the remaining balance, and a receipt is not rent revenue
- A rent payment cannot be allocated above the invoice outstanding or the payment amount
- An expense posts an Expense transaction, and cancelling it posts the opposite amount without editing the first
- Vacating a bed does not change a rent invoice outstanding
- Desk overview totals are zero for a property user with no records, and the default period is the current month
- Recognized rent, collections, expenses, and operating profit follow submitted transactions, including negative reversals
- A deposit receipt is not profit; a transfer to revenue is
- Vacating stops the fixed-rent schedule and leaves the open receivable
- A property user cannot read another user's totals, buildings, or account list, including a forged filter
- A caller who is not a property user or super admin cannot open the overview
- Super Admin Panel excludes the Property User role; User Report includes it
- Financial Position matches the desk overview for the same owner and month
- Flat profit excludes building overhead, and a cancelled expense nets once
- A property user cannot read another user's report or chart, including a forged filter
- Occupancy counts are current, while vacated stays still appear from allocation dates
- An empty portfolio is zero

These tests need a migrated site. They were not executed in the environment that added the app, because that machine has Python 3.12 and Frappe v16 requires Python 3.14.

## Password reset that Frappe still exposes

The app blocks property accounts. It does not remove Frappe's own login page.

- `web_include_js` hides the Forgot Password control on the standard login page.
- `User.validate_reset_password` refuses property accounts, so the guest reset method does not send a mail. Frappe still answers that call with its generic "if this email is registered" message, which is intentional in the framework.
- A direct visit to `/update-password?key=...` does not complete for these accounts.
- Administrator, and a Property Super Admin who has no Property User Profile, still use Frappe's own reset.
- The supported login is the mobile number. The synthetic email is the User id, so Frappe will also accept it at the login form. Prefer the mobile number.

## Phase 3

Tenants need a mobile number and an identification number. Status is Active (can be placed, or currently placed), Vacated (last stay closed), or Inactive (cannot be placed). Owner User isolation uses the same document-load check as buildings.

Bed Allocation is the stay history. Vacate is the button on that form and `Bed Allocation.vacate`. It requires a vacating date and sets Generate Rent to off so a later billing run can skip the row. `allocation_generates_rent` is the hook that run will read. Phase 4–5 must not treat that flag as a write-off of rent or deposit.

## Phase 4

Money is a list of Financial Transaction rows, not debit and credit accounts. Each row belongs to one Owner User, and opening it checks that owner the same way a building does.

- Rent Invoice submit posts Rent Generated. Rent Payment submit posts Rent Received and updates the invoice paid and outstanding amounts. A payment cannot exceed an invoice balance or the payment amount.
- Tenant Deposit receipts post Deposit Received. That is not rent. Refunds and transfers cannot exceed the remaining balance. Only Transfer to Revenue posts Deposit Transferred to Revenue.
- Property Expense submit posts Expense. Cancelling it posts a second Expense transaction for the opposite amount. The first transaction stays.
- Vacate does not change invoice outstanding. `leave_receivables_unchanged` is called from Vacate and does nothing to balances.

Cash/Bank Account is only a name and a type, Cash or Bank.

## Phase 5

Rent is generated per calendar month for an active bed allocation. Property Settings holds the rules:

- Billing Day, default 1. A shorter month uses its last day, so 31 is allowed.
- Due Days After Billing, default 7. The due date is that many days after the later of the billing date and the first occupied day in the month.
- Prorate Partial Months, default on. Occupied days in the month divided by the number of days in that month. When it is off, any overlapping month is billed at the full monthly rent.

An active allocation with Generate Rent on gets one Monthly Revenue schedule. Rent revisions are effective-dated and do not rewrite a submitted invoice. Vacate sets the schedule end date and still allows the final overlapping month. It does not change outstanding amounts.

The daily job is `property_management.billing.generate_due_rent_invoices`. It catches up any missed months. A Property Super Admin, or a Property User for their own schedules, can run the same job by hand:

```bash
bench --site property.localhost execute property_management.billing.generate_due_rent_invoices
```

From the desk or a console session, the whitelisted method is `property_management.billing.generate_rent_invoices` with an optional `as_of` date and an optional `monthly_revenue` name. `property_management.billing.revise_rent` adds a later rate.

Each attempt is a Rent Billing Log row: Success, Skipped, or Failed. A failed period is rolled back to a savepoint and can be run again. The invoice key is the allocation plus `YYYY-MM`, so a repeated run does not create a second invoice.

## Phase checklist

| Phase | In this branch |
| --- | --- |
| 1. Accounts, mobile username, expiry, first-login password change | Yes |
| 2. Building, flat, area, bed, and owner isolation | Yes |
| 3. Tenant, allocation, vacate | Yes |
| 4. Rent, deposits, expenses, and reversals | Yes |
| 5. Monthly rent billing | Yes, parent commit `9dceb5762a683c3a53d5a5f7a563b142468c916b` |
| 6. Super Admin Panel and User Report | Yes |
| 7. Reports and overview charts | Yes |
| 8. Further work | Not started |

## Phase 6

Two standard desk pages, plus the Property Management workspace and sidebar:

- **Super Admin Panel** (`/app/super-admin-panel`) is limited to Property Super Admin and System Manager. It creates a property user, resets the temporary password, moves expiry, and activates or deactivates the account. Those actions call the existing account APIs. The password is not written on the profile and is not returned to the page.
- **User Report** (`/app/user-report`) is for a Property User, and a Property Super Admin can open it too. It lists that owner's buildings, flats, areas, and beds, and links to the real forms for tenants, allocations, vacate, rent schedules, collections, deposit receipt, refund, transfer to revenue, and expenses.

A property user who still has to change the temporary password is kept on `/property-password`. The pages do not call the overview until that flag is clear. An expired or deactivated account cannot sign in.

The overview reads the database. An empty portfolio is zero, not a sample figure. The date filter defaults to the current calendar month. Occupancy, monthly fixed rent, open receivables, and held deposits are current balances. Recognized rent, collections, deposit movements, and expenses use the selected dates.

| Figure | Meaning |
| --- | --- |
| Monthly fixed rent | `monthly_rent` on Active Monthly Revenue schedules. Vacated schedules are stopped and drop out. Submitted invoices stay as they were. |
| Recognized rental revenue | Submitted Rent Generated plus Receivable Adjustment in the date range. Cancelling an invoice posts the negative adjustment on the invoice billing date. |
| Rent collected | Submitted Rent Received plus Payment Reversal in the date range. This is cash, not a second copy of revenue. |
| Allocated receipts | Invoice Allocation rows on submitted payments in the range. Cancelled payments are excluded. |
| Advances | Payment amount minus its allocations. Full allocation is required, so this is zero unless cash is left unapplied. It is not revenue. |
| Outstanding in period | Remaining balance on submitted invoices billed in the range. |
| All open receivables | Remaining balance on every submitted invoice in the filter. Vacate does not clear it. |
| Held deposits | Deposit Received minus Deposit Refunded minus Deposit Transferred to Revenue, ignoring the date range. Held money is not revenue. |
| Operating profit | Recognized rental revenue + deposit transferred to revenue + other revenue − expenses. |

The same words are returned by `property_management.desk.get_overview` in `measures`. A Property User who sends another user's id, or another user's building, flat, or area, is rejected. A Property Super Admin can choose one property user or leave the user blank for every account. The user-wise rows use the same measures.

Manual check, as Administrator or a Property Super Admin:

```bash
bench --site pm.local execute property_management.desk.get_overview
bench --site pm.local execute property_management.desk.list_property_accounts
```

`get_overview` accepts `owner_user`, `building`, `flat`, `area`, `from_date`, and `to_date`.

## Phase 7

Reports use the same measures as the desk overview. A property user is limited to their own rows. A property super admin can leave the user blank for every account, or choose one. Forged user, building, flat, and area filters are rejected. The date range defaults to the current month. Snapshot figures ignore that range and are labelled Snapshot. Period figures use it and are labelled Period.

Operating profit is recognized rental revenue, plus other revenue, plus deposit transferred to revenue, minus expenses. It is not cash profit. Held deposits, rent collected, and advances are separate. A reversal stays as its own negative transaction and is included once. Receivables for a vacated tenant stay in the open balance.

Expenses with no flat are building overhead. Flat Profitability and Area Profitability do not spread that overhead across rows. Building Profitability includes it when no flat is selected, and shows it again in its own column without adding it twice. There is no invented split of a building bill onto flats.

| Requested view | Report or chart |
| --- | --- |
| Total financial position | Financial Position |
| Consolidated position | Financial Position with no property user selected |
| User-wise position | User-wise Financial Summary |
| Flat profitability | Flat Profitability, and the Flat Direct Profit chart |
| Building profitability | Building Profitability |
| Area profitability | Area Profitability |
| Rent invoiced, collected, outstanding | Rent Position |
| Deposit liability and history | Deposit Liability |
| Expenses | Expense Register |
| Occupancy and vacancy | Occupancy, and the Current Occupancy chart |
| Transaction history | Transaction History. This is not a debit and credit ledger |
| Tenant history | Tenant History, including vacated stays and open receivables |
| Monthly invoiced revenue, collections, expenses, and profit | Monthly Property Movement chart |

The monthly chart defaults to the six months ending this month. Each point is that month's movement, not a balance. Current Occupancy is the beds right now. It is not a past occupancy rate. Stays in the Occupancy report come from allocation dates, including a vacated row.

Open them from the Property Management workspace or sidebar, or the Property Overview dashboard.

```bash
bench --site pm.local execute property_management.analytics.run_report --kwargs "{'report': 'financial_position', 'filters': {}}"
```

## Not in this version

Phase 8 is not started. These reports are the views above, not a padded list of duplicate layouts. There is no cash-profit statement, no apportioned overhead, and no historical occupancy rate built from today's bed counts.

## Navigation sync

Frappe reimports a standard Workspace only when the file is newer than the row already on the site. This workspace file does not set `modified`, so a migrate compares the current time with the stored row and reloads the file. A site that already had the older DocType-only workspace picks up the Super Admin Panel and User Report links. A later migrate reloads the same file again; `for_reload` replaces the row without the link check that would block it. The standard Dock is `property_management/dock/property_management/property_management.json` and points at the Property Management sidebar, which is what a new site uses to open the module.

## Verification

Phase 6 and Phase 7 files were syntax-checked here (`py_compile` and `node --check`). This environment has Python 3.12 and no Frappe site, so `bench migrate` and `bench run-tests` were not run here. Nothing was deployed.

On a Frappe 16.53 SQLite site, the Phase 5 suite at `9dceb5762a683c3a53d5a5f7a563b142468c916b` was reported as 32 passed, including the billing tests. A clean production database migration of the unique billing key was not part of that run. This branch does not change that billing key.

On pm.local, after this branch is checked out:

```bash
bench --site pm.local migrate
bench --site pm.local clear-cache
bench --site pm.local run-tests --app property_management
```

Then sign in and open `/app/property-management`, `/app/super-admin-panel`, and `/app/user-report`. A property user's first login still stops at `/property-password` until the temporary password is replaced. The automated tests do not click through the desk.
