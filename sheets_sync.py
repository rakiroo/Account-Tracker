#!/usr/bin/env python3
"""Google Sheets backup/sync helpers for MAUS Account Tracker."""

from __future__ import annotations

import os
import re
from datetime import datetime

import account_manager as core

try:
    import gspread
    from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound
except ImportError:  # pragma: no cover - runtime dependency
    gspread = None

    class SpreadsheetNotFound(Exception):
        pass

    class WorksheetNotFound(Exception):
        pass


SERVICE_ACCOUNT_FILE_ENV = 'MAUS_GOOGLE_SERVICE_ACCOUNT_FILE'
SPREADSHEET_TARGET_ENV = 'MAUS_GOOGLE_SHEETS_SPREADSHEET_ID'
SPREADSHEET_URL_PATTERN = re.compile(r'https://docs\.google\.com/spreadsheets/')

WORKSHEET_ACCOUNTS = 'accounts'
WORKSHEET_SOLD_ACCOUNTS = 'sold_accounts'
WORKSHEET_MARKET_SAMPLES = 'market_samples'
WORKSHEET_STOCK_PROFILES = 'stock_profiles'
WORKSHEET_META = 'meta'

ACCOUNT_HEADERS = [
    'code',
    'stock_name',
    'name',
    'link',
    'email',
    'password',
    'legacy_password_hash',
    'fbfs',
    'notes',
]

SOLD_ACCOUNT_HEADERS = ACCOUNT_HEADERS + [
    'sold_price_php',
    'sold_at',
    'sold_note',
    'market_price_php',
    'price_difference_php',
    'price_difference_percent',
    'pricing_source',
]

MARKET_SAMPLE_HEADERS = [
    'scope',
    'stock_name',
    'total_price_php',
    'account_count',
    'note',
    'recorded_at',
]

STOCK_PROFILE_HEADERS = [
    'stock_name',
    'info',
]

META_HEADERS = [
    'key',
    'value',
]


class SheetsSyncError(Exception):
    """Base class for sync failures."""


class SheetsSyncConfigError(SheetsSyncError):
    """Raised when required sync configuration is missing."""


def ensure_dependency_installed():
    if gspread is None:
        raise SheetsSyncConfigError(
            'Google Sheets sync dependency is missing. Install it with: pip install -r requirements-sheets.txt'
        )


def get_sync_config():
    return {
        'service_account_file': os.path.abspath(
            os.path.expanduser(os.environ.get(SERVICE_ACCOUNT_FILE_ENV, '').strip())
        )
        if os.environ.get(SERVICE_ACCOUNT_FILE_ENV, '').strip()
        else '',
        'spreadsheet_target': os.environ.get(SPREADSHEET_TARGET_ENV, '').strip(),
    }


def validate_sync_config(config=None):
    ensure_dependency_installed()
    config = config or get_sync_config()

    if not config['service_account_file']:
        raise SheetsSyncConfigError(
            f'Missing {SERVICE_ACCOUNT_FILE_ENV}. Point it to your downloaded Google service account JSON file.'
        )
    if not os.path.exists(config['service_account_file']):
        raise SheetsSyncConfigError(
            f'Service account file not found: {config["service_account_file"]}'
        )
    if not config['spreadsheet_target']:
        raise SheetsSyncConfigError(
            f'Missing {SPREADSHEET_TARGET_ENV}. Set it to your spreadsheet ID or full Sheets URL.'
        )
    return config


def current_sync_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def open_spreadsheet(config=None):
    config = validate_sync_config(config)
    client = gspread.service_account(filename=config['service_account_file'])
    target = config['spreadsheet_target']

    if SPREADSHEET_URL_PATTERN.search(target):
        spreadsheet = client.open_by_url(target)
    else:
        spreadsheet = client.open_by_key(target)
    return spreadsheet


def ensure_worksheet(spreadsheet, title, headers):
    try:
        worksheet = spreadsheet.worksheet(title)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=max(100, len(headers) + 5), cols=len(headers))
    return worksheet


def write_rows_to_worksheet(spreadsheet, title, headers, rows):
    worksheet = ensure_worksheet(spreadsheet, title, headers)
    worksheet.clear()
    worksheet.update([headers] + rows, 'A1')
    return worksheet


def rows_from_account_records(accounts, include_sale_fields=False):
    rows = []
    headers = SOLD_ACCOUNT_HEADERS if include_sale_fields else ACCOUNT_HEADERS
    for code in sorted(accounts.keys()):
        account = accounts[code]
        row = [
            str(account.get('code', '')),
            str(account.get('stock_name', '')),
            str(account.get('name', '')),
            str(account.get('link', '')),
            str(account.get('email', '')),
            str(account.get('password', '')),
            str(account.get('legacy_password_hash', '')),
            str(account.get('fbfs', 0)),
            str(account.get('notes', '')),
        ]
        if include_sale_fields:
            row.extend(
                [
                    str(account.get('sold_price_php', 0.0)),
                    str(account.get('sold_at', '')),
                    str(account.get('sold_note', '')),
                    str(account.get('market_price_php', 0.0)),
                    str(account.get('price_difference_php', 0.0)),
                    str(account.get('price_difference_percent', 0.0)),
                    str(account.get('pricing_source', '')),
                ]
            )
        if len(row) != len(headers):
            raise SheetsSyncError('Internal row/header mismatch while preparing account sync rows.')
        rows.append(row)
    return rows


def rows_from_market_samples(data):
    rows = []
    for sample in data['pricing']['samples']:
        rows.append(
            [
                'global',
                '',
                str(sample.get('total_price_php', 0.0)),
                str(sample.get('account_count', 0)),
                str(sample.get('note', '')),
                str(sample.get('recorded_at', '')),
            ]
        )

    for stock_name in core.STOCK_CHOICES:
        for sample in data['stock_profiles'][stock_name]['samples']:
            rows.append(
                [
                    'stock',
                    stock_name,
                    str(sample.get('total_price_php', 0.0)),
                    str(sample.get('account_count', 0)),
                    str(sample.get('note', '')),
                    str(sample.get('recorded_at', '')),
                ]
            )

    return rows


def rows_from_stock_profiles(data):
    rows = []
    for stock_name in core.STOCK_CHOICES:
        rows.append([stock_name, str(data['stock_profiles'][stock_name].get('info', ''))])
    return rows


def rows_from_meta(data):
    return [
        ['schema_version', '1'],
        ['pushed_at', current_sync_timestamp()],
        ['active_account_count', str(len(data['accounts']))],
        ['sold_account_count', str(len(data.get('sold_accounts', {})))],
        ['global_market_sample_count', str(len(data['pricing']['samples']))],
    ]


def push_data_to_sheets(data):
    spreadsheet = open_spreadsheet()

    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_ACCOUNTS,
        ACCOUNT_HEADERS,
        rows_from_account_records(data['accounts']),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_SOLD_ACCOUNTS,
        SOLD_ACCOUNT_HEADERS,
        rows_from_account_records(data.get('sold_accounts', {}), include_sale_fields=True),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_MARKET_SAMPLES,
        MARKET_SAMPLE_HEADERS,
        rows_from_market_samples(data),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_STOCK_PROFILES,
        STOCK_PROFILE_HEADERS,
        rows_from_stock_profiles(data),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_META,
        META_HEADERS,
        rows_from_meta(data),
    )

    return {
        'spreadsheet_title': spreadsheet.title,
        'active_account_count': len(data['accounts']),
        'sold_account_count': len(data.get('sold_accounts', {})),
        'market_sample_count': len(rows_from_market_samples(data)),
        'stock_profile_count': len(core.STOCK_CHOICES),
    }


def get_worksheet_values(spreadsheet, title):
    try:
        worksheet = spreadsheet.worksheet(title)
    except WorksheetNotFound:
        return []
    return worksheet.get_all_values()


def worksheet_values_to_rows(values):
    if not values:
        return []
    headers = values[0]
    if not headers:
        return []
    rows = []
    for raw_row in values[1:]:
        padded = list(raw_row) + [''] * (len(headers) - len(raw_row))
        rows.append({headers[index]: padded[index] for index in range(len(headers))})
    return rows


def pull_data_from_sheets():
    spreadsheet = open_spreadsheet()

    accounts_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_ACCOUNTS))
    sold_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_SOLD_ACCOUNTS))
    market_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_MARKET_SAMPLES))
    profile_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_STOCK_PROFILES))

    raw_data = core.default_database()

    for row in accounts_rows:
        code = str(row.get('code', '')).strip().upper()
        if not code:
            continue
        raw_data['accounts'][code] = {
            'code': code,
            'stock_name': row.get('stock_name', ''),
            'name': row.get('name', ''),
            'link': row.get('link', ''),
            'email': row.get('email', ''),
            'password': row.get('password', ''),
            'legacy_password_hash': row.get('legacy_password_hash', ''),
            'fbfs': row.get('fbfs', '0'),
            'notes': row.get('notes', ''),
        }

    for row in sold_rows:
        code = str(row.get('code', '')).strip().upper()
        if not code:
            continue
        raw_data['sold_accounts'][code] = {
            'code': code,
            'stock_name': row.get('stock_name', ''),
            'name': row.get('name', ''),
            'link': row.get('link', ''),
            'email': row.get('email', ''),
            'password': row.get('password', ''),
            'legacy_password_hash': row.get('legacy_password_hash', ''),
            'fbfs': row.get('fbfs', '0'),
            'notes': row.get('notes', ''),
            'sold_price_php': row.get('sold_price_php', '0'),
            'sold_at': row.get('sold_at', ''),
            'sold_note': row.get('sold_note', ''),
            'market_price_php': row.get('market_price_php', '0'),
            'price_difference_php': row.get('price_difference_php', '0'),
            'price_difference_percent': row.get('price_difference_percent', '0'),
            'pricing_source': row.get('pricing_source', ''),
        }

    for row in profile_rows:
        stock_name = str(row.get('stock_name', '')).strip().upper()
        if stock_name not in core.STOCK_CHOICES:
            continue
        raw_data['stock_profiles'][stock_name]['info'] = str(row.get('info', '')).strip()

    for row in market_rows:
        try:
            sample = {
                'total_price_php': row.get('total_price_php', '0'),
                'account_count': row.get('account_count', '0'),
                'note': row.get('note', ''),
                'recorded_at': row.get('recorded_at', ''),
            }
            scope = str(row.get('scope', '')).strip().lower()
            stock_name = str(row.get('stock_name', '')).strip().upper()
            if scope == 'global' or not stock_name:
                raw_data['pricing']['samples'].append(sample)
            elif stock_name in core.STOCK_CHOICES:
                raw_data['stock_profiles'][stock_name]['samples'].append(sample)
        except KeyError:
            continue

    normalized = core.normalize_data(raw_data)
    return normalized, {
        'spreadsheet_title': spreadsheet.title,
        'active_account_count': len(normalized['accounts']),
        'sold_account_count': len(normalized.get('sold_accounts', {})),
        'market_sample_count': len(market_rows),
        'stock_profile_count': len(profile_rows),
    }
