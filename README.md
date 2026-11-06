# Property Management

Standalone [Frappe Framework](https://frappeframework.com) v16 app for a property super admin and the people who run buildings. It does not depend on ERPNext, and it does not post journal entries.

Phase 1 is accounts. Phase 2 is the building hierarchy. Phase 3 is tenant placement and vacating. Phase 4 records rent, deposits, and expenses as transactions. There is still no monthly billing run and no general-ledger accounts.

## What you can do

**Property Super Admin**

- Create a property user. The username is the mobile number. The initial password is set with Frappe's password API, not a custom field.
- Move the account expiry date, deactivate the user, or set a new temporary password.
- See every building, flat, area, bed, tenant, and allocation.

**Property User**

- Signs in with the mobile number.
- Must replace the temporary password before using the desk.
- Cannot use Forgot Password. A Property Super Admin resets it.
- Creates buildings, then flats, areas, and beds, and names a tenant on a vacant bed.
- Sees only records whose Owner User is themselves. That filter is applied in the database and again when a document is opened.

Login is refused when Account Expiry is before today. The expiry date itself is still a valid day.

## DocTypes

| DocType | Purpose |
| --- | --- |
| Property Settings | Billing day (1–28) and a prorate flag. Neither is used to create charges yet. |
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

### Upgrading an existing site

`bench migrate` runs in this order:

1. `pre_model_sync` patch `property_management.patches.v0_1.backfill_rent_invoice_keys`. If `tabRent Invoice` does not exist, the patch returns. That is a clean install: the table is created in the next step with the unique columns already in place.
2. Frappe schema sync. On an upgrade it creates the unique indexes for `invoice_number` and `billing_key`. It does not add those columns as `UNIQUE` in one `ALTER TABLE`, because the patch has already added them as ordinary nullable columns.
3. `post_model_sync`. This app has no patches there.

SQLite rejects `ALTER TABLE ... ADD COLUMN ... UNIQUE` (`Cannot add a UNIQUE column`). That is why the columns are added first without the unique constraint. MariaDB and Postgres still receive a normal unique index from schema sync, so the supported database rule is unchanged. SQLite is only the smoke database.

The patch fills a blank invoice number with the invoice name, and a blank billing key with `{bed allocation}-{billing month}`. A value that is already stored is kept. If two invoices would share a number or a key, or a row has no allocation or billing month to derive a key from, migrate stops and names those invoices, including docstatus. No invoice is deleted, and amounts, status, and payments are not changed. Fix the listed rows and run `bench migrate` again.

The data updates are one transaction. Adding a column is committed first, because MariaDB commits DDL on its own. If the backfill then stops, the plain columns remain and the patch is not recorded, so the next migrate continues from the fill step. After the patch succeeds, a later migrate runs it again only if it was not recorded; the fill then finds nothing blank. Schema sync creates `CREATE UNIQUE INDEX IF NOT EXISTS`, so repeating migrate does not rebuild the invoices.

```bash
python3 -c "from property_management.invoice_migration import sqlite_upgrade_smoke; sqlite_upgrade_smoke()"
bench --site pm.local migrate
bench --site pm.local run-tests --app property_management --case TestRentInvoiceKeyPlan
bench --site pm.local run-tests --app property_management --case TestRentInvoiceKeyBackfill
```

## Not in this version

No desk pages and no financial-position or flat-profitability reports.

## Verification

`sqlite_upgrade_smoke` passed in this environment. It reproduces `Cannot add a UNIQUE column`, then adds plain columns, fills keys, and creates the unique indexes without deleting rows. The Frappe site tests were not run here. On the restored Phase 4 copy, deploy this branch and run:

```bash
bench --site pm.local migrate
bench --site pm.local run-tests --app property_management
```
