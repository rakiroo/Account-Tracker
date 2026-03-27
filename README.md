# Termux Account Manager

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

Menu options:
- 1: Paste/add account(s)
- 2: List accounts
- 3: View/fetch account
- 4: Delete account
- 5: Add market price sample
- 6: Set stock info
- 7: View pricing summary
- 8: Exit

## Stock Choices
The stock name is now a picked choice instead of a separate free-text stock name plus tag.

Current stock choices:
- `RA`
- `PR`
- `ON`
- `MN`
- `RP`

When adding accounts, you choose one stock name first, then paste the account info for that stock.

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

## Pricing
Pricing is now tied to the picked stock name choices:
- `RA`
- `PR`
- `ON`
- `MN`
- `RP`

You can save stock info and market samples per stock name.

The auto price is calculated like this:
- `sum of prices for that stock / sum of account counts for that stock`

If a stock has no stock-specific market samples yet, the script can still use global market samples as a fallback.

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

## Note
This version stores passwords as plain text so you can view them later in Termux.

Older records created in the previous version may still show a `legacy_password_hash` because hashes cannot be converted back into the original password. Re-save those accounts if you want the real password stored.
