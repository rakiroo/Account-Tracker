# MAUS Account Tracker

## Run
Termux:
```bash
cd ~/Account
python3 account_manager.py
```

Windows:
```powershell
cd C:\Users\User\Account
python account_manager.py
```

## Update
```bash
cd ~/Account
git pull
python3 account_manager.py
```

## Menu
- `1` Add account
- `2` List accounts
- `3` Get stock
- `4` Manage account
- `9` Push to Google Sheets
- `10` Pull from Google Sheets

## Sheets Sync
Set:
- `MAUS_GOOGLE_SERVICE_ACCOUNT_FILE`
- `MAUS_GOOGLE_SHEETS_SPREADSHEET_ID`
