# Termux Account Manager

## Requirements
- Termux on Android
- Python 3 and Git (install with `pkg install python git`)

## Install In Termux
1. Clone your Git repo in Termux:
   ```bash
   cd $HOME
   git clone <your-repo-url> Account
   cd Account
   ```
2. Make executable:
   ```bash
   chmod +x account_manager.py
   ```
3. Run it:
   ```bash
   ./account_manager.py
   ```

## Update From Git
When you change the script on your computer and push it to Git, update it on your phone with:
```bash
cd $HOME/Account
git pull
```

Your saved accounts and pricing data stay safe because they are stored outside the repo in:
- `~/.termux_accounts.json`

## Usage
```bash
./account_manager.py
```

Menu options:
- 1: Add account
- 2: List accounts
- 3: View account
- 4: Delete account
- 5: Add market price sample
- 6: Set tag info
- 7: View pricing summary
- 8: Exit

## Tag-Based Info And Pricing
Each tag like `RA`, `RP`, `MX`, and `ON` can now have:
- its own saved info/description
- its own market pricing samples
- its own auto-calculated price

When you add or view an account, the script will show:
- the tag info for that account
- the estimated price for that tag

## Suggested Setup
1. Choose `6) Set tag info`.
2. Save a description for each tag you use.
   - Example: `RA = ready account`
   - Example: `RP = ready profile`
3. Choose `5) Add market price sample`.
4. Pick the tag choice for the listing, then enter the price and quantity.
   - Example: `RA`
   - Example: `54 PHP` for `1` account
   - Example: `RP`
   - Example: `250 PHP` for `5` accounts
5. Add your accounts normally and pick the correct tag from the choices.
6. The script will automatically show the saved tag info and the estimated tag price.

## Pricing Rules
The script calculates price per tag using:
- `sum of prices for that tag / sum of account counts for that tag`

Example for `RA`:
- `54 PHP` for `1` account
- `200 PHP` for `4` accounts

Auto price for `RA`:
- `(54 + 200) / (1 + 4) = 50.80 PHP per RA account`

If a tag has no tag-specific market samples yet, the script can still use global market samples as a fallback.

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
This script stores password hashes (SHA-256) and not plain passwords. If you want to store real passwords, modify it to save `password` directly, or use a secure vault like `pass` or `gpg`.
