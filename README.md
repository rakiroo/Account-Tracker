# MAUS Account Tracker

## Requirements
- Termux on Android
- Python 3 and Git (install with `pkg install python git`)

## Install In Termux
1. Clone your Git repo in Termux:
   ```bash
   cd $HOME
   git clone https://github.com/rakiroo/Account-Tracker.git Account
   cd Account
   ```
2. Run it:
   ```bash
   python account_manager.py
   ```

## Update From Git
When you change the script on your computer and push it to Git, update it on your phone with:
```bash
cd $HOME/Account
git pull
python account_manager.py
```

Your saved accounts and pricing data stay safe because they are stored outside the repo in:
- `~/.termux_accounts.json`

## Usage
```bash
python account_manager.py
```

The app now uses a cleaner MAUS-themed terminal UI with:
- a dashboard-style home screen
- colored panels on supported terminals like Termux
- cleaner action screens for add, fetch, pricing, and delete flows

Menu options:
- 1: Paste/add account(s)
- 2: List accounts
- 3: View/fetch account
- 4: Edit account
- 5: Mark account as sold
- 6: View sold history
- 7: Add market price sample
- 8: Set stock info
- 9: View market state
- 10: View pricing summary
- 11: Export backup
- 12: Import backup
- 13: Delete account
- 14: Exit

## Stock Choices
The stock name is now a picked choice instead of a separate free-text stock name plus tag.

Current stock choices:
- `RA`
- `PR`
- `ON`
- `MN`
- `RP`

When adding accounts, you choose one stock name first, then paste the account info for that stock.

If you open a stock/category picker by mistake, use:
- `0` to go back
- `G` for global fallback on market-sample screens

## Account Fields
Each account stores:
- code
- stock name
- name
- link
- email
- password
- fbfs
- notes

Every account also gets an auto code like:
- `ACC-0001`
- `ACC-0002`

## Bulk Add
Choose `1) Paste/add account(s)`, then pick the stock name first.

After that, you can paste accounts in either format.

### Format 1: One Line Per Account
```text
name | link | email | password | fbfs | notes
```

Example:
```text
John Doe | https://example.com/john | john@example.com | pass123 | 120 | main stock
Jane Doe |  | jane@example.com | pass456 | 80 |
```

### Format 2: One Field Per Line
Each account uses 6 lines in this order:
1. `name`
2. `link`
3. `email`
4. `password`
5. `fbfs`
6. `notes`

Example:
```text
John Doe
https://example.com/john
john@example.com
pass123
120
main stock

Jane Doe
-
jane@example.com
pass456
80
-
```

Notes:
- Use `-` for blank `link` or blank `notes` in multiline mode.
- Type `DONE` on its own line when finished.

## Fetching Stock
You can fetch or delete an account by:
- account code
- stock name
- saved account name

Fetching an account shows:
- code
- stock name
- name
- link
- email
- password
- fbfs
- notes
- estimated price

## Edit Active Accounts
Choose `4) Edit account` to update an active stock account without deleting and re-adding it.

You can update:
- stock/category
- name
- link
- email
- password
- fbfs
- notes

Editing tips:
- press `Enter` to keep the current value
- use `-` to clear `link` or `notes`
- use `0` while choosing a new stock/category to cancel the edit

## Sold Tracking
Choose `5) Mark account as sold` to move an active account out of inventory and into sold history.

When you mark an account as sold, the app saves:
- sold price
- sold date/time
- optional sale note
- market price at the time of sale
- difference between sold price and market price

Choose `6) View sold history` to see:
- what sold
- when it sold
- how much it sold for
- whether it sold above or below market

## Pricing
Pricing is now tied to the picked stock name choices:
- `RA`
- `PR`
- `ON`
- `MN`
- `RP`

You can save stock info and market samples per stock name.

Every market sample can also store:
- observed date/time
- note/source

The auto price is calculated like this:
- `sum of prices for that stock / sum of account counts for that stock`

If a stock has no stock-specific market samples yet, the script can still use global market samples as a fallback.

Choose `9) View market state` to see:
- latest observed market price per stock
- price movement versus the previous sample
- weighted market average
- price range from saved samples

## Price Input Formats
The price prompt accepts inputs like:
- `54`
- `54php`
- `PHP 54`
- `1,250`

## Data Is Stored In
- `~/.termux_accounts.json`

This is useful for Git + Termux because:
- you can `git pull` the latest script without losing your account data
- your stock list is not mixed into your repo files

## Move Data Between Phones
Use these menu options for manual transfer:
- `11) Export backup`
- `12) Import backup`

Default backup file:
- `~/maus-account-backup.json`

Import safety backup:
- `~/.termux_accounts.pre_import_backup.json`

Simple phone-to-phone flow:
1. On phone A, choose `11) Export backup`.
2. Move the backup file to phone B.
3. On phone B, choose `12) Import backup`.

If you want to export into shared storage on Android, you can usually use a path like:
- `~/storage/downloads/maus-account-backup.json`

That may require running:
```bash
termux-setup-storage
```

## Note
This version stores passwords as plain text so you can view them later in Termux.

Older records created in the previous version may still show a `legacy_password_hash` because hashes cannot be converted back into the original password. Re-save those accounts if you want the real password stored.
