#!/usr/bin/env python3
"""Google Sheets backup/sync helpers for MAUS Account Tracker."""

from __future__ import annotations

import copy
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
WORKSHEET_DELETED_ACCOUNTS = 'deleted_accounts'
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
    'fbfs',
    'notes',
    'updated_at',
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

DELETED_ACCOUNT_HEADERS = [
    'code',
    'stock_name',
    'name',
    'link',
    'email',
    'password',
    'deleted_at',
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

TIMESTAMP_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
    '%Y-%m-%d',
)


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


def parse_timestamp(value):
    text = str(value or '').strip()
    if not text:
        return None

    for timestamp_format in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, timestamp_format)
        except ValueError:
            continue
    return None


def latest_timestamp_text(*values):
    candidates = []
    for value in values:
        text = str(value or '').strip()
        parsed = parse_timestamp(text)
        if text:
            candidates.append((parsed, text))

    if not candidates:
        return ''

    dated_candidates = [candidate for candidate in candidates if candidate[0] is not None]
    if dated_candidates:
        return max(dated_candidates, key=lambda candidate: candidate[0])[1]
    return candidates[0][1]


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


def meta_rows_to_dict(rows):
    meta = {}
    for row in rows:
        key = str(row.get('key', '')).strip()
        if key:
            meta[key] = str(row.get('value', '')).strip()
    return meta


def rows_from_account_records(accounts, include_sale_fields=False):
    rows = []
    headers = SOLD_ACCOUNT_HEADERS if include_sale_fields else ACCOUNT_HEADERS
    for code in sorted(accounts.keys()):
        account = accounts[code]
        row = [
            str(account.get('code', '')),
            str(core.get_stock_sheet_name(account.get('stock_name', ''))),
            str(account.get('name', '')),
            str(account.get('link', '')),
            str(account.get('email', '')),
            str(account.get('password', '')),
            str(account.get('fbfs', 0)),
            str(account.get('notes', '')),
            str(account.get('updated_at', '')),
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


def sample_signature(scope, stock_name, sample):
    return (
        str(scope).strip().lower(),
        str(stock_name or '').strip().upper(),
        f'{core.normalize_non_negative_float(sample.get("total_price_php")):.2f}',
        str(core.normalize_non_negative_int(sample.get('account_count', 0))),
        str(sample.get('note', '')).strip(),
        str(sample.get('recorded_at', '')).strip(),
    )


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
                    core.get_stock_sheet_name(stock_name),
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
        rows.append([core.get_stock_sheet_name(stock_name), str(data['stock_profiles'][stock_name].get('info', ''))])
    return rows


def rows_from_deleted_accounts(data):
    rows = []
    for entry in data.get('deleted_accounts', []):
        rows.append(
            [
                str(entry.get('code', '')),
                str(core.get_stock_sheet_name(entry.get('stock_name', ''))),
                str(entry.get('name', '')),
                str(entry.get('link', '')),
                str(entry.get('email', '')),
                str(entry.get('password', '')),
                str(entry.get('deleted_at', '')),
            ]
        )
    return rows


def rows_from_meta(data, merge_summary=None):
    merge_summary = merge_summary or {}
    rows = [
        ['schema_version', '2'],
        ['pushed_at', current_sync_timestamp()],
        ['active_account_count', str(len(data['accounts']))],
        ['sold_account_count', str(len(data.get('sold_accounts', {})))],
        ['deleted_account_count', str(len(data.get('deleted_accounts', [])))],
        ['global_market_sample_count', str(len(data['pricing']['samples']))],
        ['duplicates_merged', str(merge_summary.get('duplicates_merged', 0))],
        ['code_collisions_resolved', str(merge_summary.get('code_collisions_resolved', 0))],
        ['ambiguous_duplicates', str(merge_summary.get('ambiguous_duplicates', 0))],
        ['deletions_applied', str(merge_summary.get('deletions_applied', 0))],
    ]
    return rows


def read_spreadsheet_snapshot(spreadsheet):
    accounts_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_ACCOUNTS))
    sold_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_SOLD_ACCOUNTS))
    deleted_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_DELETED_ACCOUNTS))
    market_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_MARKET_SAMPLES))
    profile_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_STOCK_PROFILES))
    meta_rows = worksheet_values_to_rows(get_worksheet_values(spreadsheet, WORKSHEET_META))

    raw_data = core.default_database()

    for row in accounts_rows:
        code = str(row.get('code', '')).strip().upper()
        if not code:
            continue
        raw_data['accounts'][code] = {
            'code': code,
            'stock_name': core.normalize_stock_name(row.get('stock_name', '')),
            'name': row.get('name', ''),
            'link': row.get('link', ''),
            'email': row.get('email', ''),
            'password': row.get('password', ''),
            'fbfs': row.get('fbfs', '0'),
            'notes': row.get('notes', ''),
            'updated_at': row.get('updated_at', ''),
        }

    for row in sold_rows:
        code = str(row.get('code', '')).strip().upper()
        if not code:
            continue
        raw_data['sold_accounts'][code] = {
            'code': code,
            'stock_name': core.normalize_stock_name(row.get('stock_name', '')),
            'name': row.get('name', ''),
            'link': row.get('link', ''),
            'email': row.get('email', ''),
            'password': row.get('password', ''),
            'fbfs': row.get('fbfs', '0'),
            'notes': row.get('notes', ''),
            'updated_at': row.get('updated_at', row.get('sold_at', '')),
            'sold_price_php': row.get('sold_price_php', '0'),
            'sold_at': row.get('sold_at', ''),
            'sold_note': row.get('sold_note', ''),
            'market_price_php': row.get('market_price_php', '0'),
            'price_difference_php': row.get('price_difference_php', '0'),
            'price_difference_percent': row.get('price_difference_percent', '0'),
            'pricing_source': row.get('pricing_source', ''),
        }

    raw_data['deleted_accounts'] = [
        {
            'code': str(row.get('code', '')).strip().upper(),
            'stock_name': core.normalize_stock_name(row.get('stock_name', '')),
            'name': row.get('name', ''),
            'link': row.get('link', ''),
            'email': row.get('email', ''),
            'password': row.get('password', ''),
            'deleted_at': row.get('deleted_at', ''),
        }
        for row in deleted_rows
    ]

    for row in profile_rows:
        stock_name = core.normalize_stock_name(row.get('stock_name', ''))
        if stock_name not in core.STOCK_CHOICES:
            continue
        raw_data['stock_profiles'][stock_name]['info'] = str(row.get('info', '')).strip()

    for row in market_rows:
        sample = {
            'total_price_php': row.get('total_price_php', '0'),
            'account_count': row.get('account_count', '0'),
            'note': row.get('note', ''),
            'recorded_at': row.get('recorded_at', ''),
        }
        scope = str(row.get('scope', '')).strip().lower()
        stock_name = core.normalize_stock_name(row.get('stock_name', ''))
        if scope == 'global' or not stock_name:
            raw_data['pricing']['samples'].append(sample)
        elif stock_name in core.STOCK_CHOICES:
            raw_data['stock_profiles'][stock_name]['samples'].append(sample)

    normalized = core.normalize_data(raw_data)
    return normalized, {
        'spreadsheet_title': spreadsheet.title,
        'meta': meta_rows_to_dict(meta_rows),
        'deleted_account_count': len(normalized.get('deleted_accounts', [])),
        'market_sample_count': len(market_rows),
        'stock_profile_count': len(profile_rows),
    }


def clone_database(data):
    return copy.deepcopy(core.normalize_data(data))


def build_merge_summary():
    return {
        'duplicates_merged': 0,
        'duplicate_details': [],
        'ambiguous_duplicates': 0,
        'ambiguous_details': [],
        'code_collisions_resolved': 0,
        'code_collision_details': [],
        'same_code_updates': 0,
        'sold_promotions': 0,
        'deletions_applied': 0,
        'market_sample_duplicates_skipped': 0,
    }


def normalized_email_key(account):
    value = str(account.get('email', '')).strip().lower()
    return value or ''


def normalized_link_key(account):
    value = str(account.get('link', '')).strip().lower()
    if not value:
        return ''
    return re.sub(r'/+$', '', value)


def weak_identity_signature(account):
    stock_name = str(account.get('stock_name', '')).strip().upper()
    name = str(account.get('name', '')).strip().lower()
    password = str(account.get('password', '')).strip()
    if stock_name and name and password:
        return (stock_name, name, password)
    return ()


def duplicate_reason_tokens(existing_record, incoming_record):
    reasons = []
    existing_email = normalized_email_key(existing_record)
    incoming_email = normalized_email_key(incoming_record)
    if existing_email and existing_email == incoming_email:
        reasons.append('same email')

    existing_link = normalized_link_key(existing_record)
    incoming_link = normalized_link_key(incoming_record)
    if existing_link and existing_link == incoming_link:
        reasons.append('same link')

    if not reasons:
        existing_signature = weak_identity_signature(existing_record)
        incoming_signature = weak_identity_signature(incoming_record)
        if existing_signature and existing_signature == incoming_signature:
            reasons.append('same stock, name, and password')
    return reasons


def records_refer_to_same_account(existing_record, incoming_record):
    return bool(duplicate_reason_tokens(existing_record, incoming_record))


def tombstone_matches_record(tombstone, record):
    tombstone_code = str(tombstone.get('code', '')).strip().upper()
    record_code = str(record.get('code', '')).strip().upper()
    if tombstone_code and record_code and tombstone_code == record_code:
        return True
    return bool(duplicate_reason_tokens(tombstone, record))


def account_record_timestamp(record):
    return (
        parse_timestamp(record.get('updated_at'))
        or parse_timestamp(record.get('sold_at'))
    )


def account_record_completeness(record, final_section='accounts'):
    score = 0
    for field_name in ('stock_name', 'name', 'link', 'email', 'password', 'notes', 'updated_at'):
        if str(record.get(field_name, '')).strip():
            score += 1

    if core.normalize_non_negative_int(record.get('fbfs', 0)) > 0:
        score += 1

    if final_section == 'sold_accounts':
        for field_name in ('sold_at', 'sold_note', 'pricing_source'):
            if str(record.get(field_name, '')).strip():
                score += 1
        for field_name in (
            'sold_price_php',
            'market_price_php',
            'price_difference_php',
            'price_difference_percent',
        ):
            if abs(core.normalize_float(record.get(field_name, 0.0))) > 0:
                score += 1

    return score


def choose_preferred_record(existing_record, incoming_record, incoming_preferred=False, final_section='accounts'):
    if final_section == 'sold_accounts':
        existing_has_sale = bool(str(existing_record.get('sold_at', '')).strip()) or (
            core.normalize_non_negative_float(existing_record.get('sold_price_php', 0.0)) > 0
        )
        incoming_has_sale = bool(str(incoming_record.get('sold_at', '')).strip()) or (
            core.normalize_non_negative_float(incoming_record.get('sold_price_php', 0.0)) > 0
        )
        if existing_has_sale != incoming_has_sale:
            return (incoming_record, existing_record) if incoming_has_sale else (existing_record, incoming_record)

    existing_timestamp = account_record_timestamp(existing_record)
    incoming_timestamp = account_record_timestamp(incoming_record)
    if existing_timestamp and incoming_timestamp and existing_timestamp != incoming_timestamp:
        return (incoming_record, existing_record) if incoming_timestamp > existing_timestamp else (existing_record, incoming_record)
    if incoming_timestamp and not existing_timestamp:
        return incoming_record, existing_record
    if existing_timestamp and not incoming_timestamp:
        return existing_record, incoming_record

    existing_score = account_record_completeness(existing_record, final_section=final_section)
    incoming_score = account_record_completeness(incoming_record, final_section=final_section)
    if existing_score != incoming_score:
        return (incoming_record, existing_record) if incoming_score > existing_score else (existing_record, incoming_record)

    return (incoming_record, existing_record) if incoming_preferred else (existing_record, incoming_record)


def merge_text_field(preferred_record, secondary_record, field_name):
    preferred_value = str(preferred_record.get(field_name, '')).strip()
    if preferred_value:
        return preferred_record.get(field_name, '')
    return secondary_record.get(field_name, '')


def merge_account_records(existing_record, incoming_record, incoming_preferred=False, final_section='accounts', keep_code=''):
    preferred_record, secondary_record = choose_preferred_record(
        existing_record,
        incoming_record,
        incoming_preferred=incoming_preferred,
        final_section=final_section,
    )

    merged = {
        'code': keep_code or str(existing_record.get('code') or incoming_record.get('code') or '').strip().upper(),
        'stock_name': merge_text_field(preferred_record, secondary_record, 'stock_name') or 'UNKNOWN',
        'name': merge_text_field(preferred_record, secondary_record, 'name'),
        'link': core.normalize_optional_text(merge_text_field(preferred_record, secondary_record, 'link')),
        'email': merge_text_field(preferred_record, secondary_record, 'email'),
        'password': merge_text_field(preferred_record, secondary_record, 'password'),
        'fbfs': core.normalize_non_negative_int(preferred_record.get('fbfs', secondary_record.get('fbfs', 0))),
        'notes': core.normalize_optional_text(merge_text_field(preferred_record, secondary_record, 'notes')),
        'updated_at': latest_timestamp_text(
            existing_record.get('updated_at', ''),
            incoming_record.get('updated_at', ''),
            existing_record.get('sold_at', ''),
            incoming_record.get('sold_at', ''),
        ),
    }

    if final_section == 'sold_accounts':
        sale_preferred, sale_secondary = choose_preferred_record(
            existing_record,
            incoming_record,
            incoming_preferred=incoming_preferred,
            final_section='sold_accounts',
        )
        merged.update(
            {
                'sold_price_php': round(
                    core.normalize_non_negative_float(
                        sale_preferred.get('sold_price_php', sale_secondary.get('sold_price_php', 0.0))
                    ),
                    2,
                ),
                'sold_at': merge_text_field(sale_preferred, sale_secondary, 'sold_at'),
                'sold_note': core.normalize_optional_text(merge_text_field(sale_preferred, sale_secondary, 'sold_note')),
                'market_price_php': round(
                    core.normalize_non_negative_float(
                        sale_preferred.get('market_price_php', sale_secondary.get('market_price_php', 0.0))
                    ),
                    2,
                ),
                'price_difference_php': round(
                    core.normalize_float(
                        sale_preferred.get('price_difference_php', sale_secondary.get('price_difference_php', 0.0))
                    ),
                    2,
                ),
                'price_difference_percent': round(
                    core.normalize_float(
                        sale_preferred.get(
                            'price_difference_percent',
                            sale_secondary.get('price_difference_percent', 0.0),
                        )
                    ),
                    2,
                ),
                'pricing_source': merge_text_field(sale_preferred, sale_secondary, 'pricing_source'),
            }
        )
        merged['updated_at'] = latest_timestamp_text(
            merged.get('updated_at', ''),
            merged.get('sold_at', ''),
        )

    return merged


def all_used_codes(data):
    return set(data['accounts'].keys()) | set(data.get('sold_accounts', {}).keys())


def merge_deleted_accounts(base_deleted_accounts, incoming_deleted_accounts):
    merged = list(base_deleted_accounts) + list(incoming_deleted_accounts)
    return core.normalize_deleted_accounts(merged)


def tombstone_is_newer_than_record(tombstone, record):
    deleted_at = parse_timestamp(tombstone.get('deleted_at'))
    record_timestamp = account_record_timestamp(record)
    if deleted_at and record_timestamp:
        return deleted_at >= record_timestamp
    if deleted_at and not record_timestamp:
        return True
    return True


def apply_deleted_accounts(data, deleted_accounts, summary):
    removed_codes = set()
    for tombstone in deleted_accounts:
        for section in ('accounts', 'sold_accounts'):
            for code, record in list(data.get(section, {}).items()):
                if code in removed_codes:
                    continue
                if not tombstone_matches_record(tombstone, record):
                    continue
                if not tombstone_is_newer_than_record(tombstone, record):
                    continue
                del data[section][code]
                removed_codes.add(code)

    summary['deletions_applied'] += len(removed_codes)


def store_record(data, section, record):
    code = str(record.get('code', '')).strip().upper()
    if not code:
        raise SheetsSyncError('Cannot store a record without an account code.')

    cloned = dict(record)
    cloned['code'] = code

    if section == 'sold_accounts':
        data.setdefault('sold_accounts', {})[code] = cloned
        data.setdefault('accounts', {}).pop(code, None)
    else:
        if code in data.get('sold_accounts', {}):
            return
        data.setdefault('accounts', {})[code] = cloned


def reassign_record_code(data, record):
    reassigned = dict(record)
    new_code = core.generate_unique_account_code(all_used_codes(data))
    reassigned['code'] = new_code
    return reassigned, new_code


def find_duplicate_candidates(data, incoming_record):
    candidates = []
    seen = set()

    for section in ('accounts', 'sold_accounts'):
        for code, existing_record in data.get(section, {}).items():
            if code == incoming_record.get('code'):
                continue

            reasons = duplicate_reason_tokens(existing_record, incoming_record)
            if not reasons:
                continue

            candidate_key = (section, code)
            if candidate_key in seen:
                continue

            candidates.append(
                {
                    'section': section,
                    'code': code,
                    'reasons': reasons,
                }
            )
            seen.add(candidate_key)

    return candidates


def merge_records_into_data(data, incoming_records, incoming_section, incoming_preferred, summary, source_label):
    for incoming_code in sorted(incoming_records.keys()):
        record = dict(incoming_records[incoming_code])
        record['code'] = str(record.get('code') or incoming_code).strip().upper()
        if not record['code']:
            record, new_code = reassign_record_code(data, record)
            summary['code_collisions_resolved'] += 1
            summary['code_collision_details'].append(
                {
                    'source': source_label,
                    'old_code': '',
                    'new_code': new_code,
                    'reason': 'missing code',
                }
            )

        while True:
            same_code_section = ''
            same_code_record = None
            if record['code'] in data.get('sold_accounts', {}):
                same_code_section = 'sold_accounts'
                same_code_record = data['sold_accounts'][record['code']]
            elif record['code'] in data.get('accounts', {}):
                same_code_section = 'accounts'
                same_code_record = data['accounts'][record['code']]

            if same_code_record is not None:
                if records_refer_to_same_account(same_code_record, record):
                    final_section = (
                        'sold_accounts'
                        if incoming_section == 'sold_accounts' or same_code_section == 'sold_accounts'
                        else 'accounts'
                    )
                    merged_record = merge_account_records(
                        same_code_record,
                        record,
                        incoming_preferred=incoming_preferred,
                        final_section=final_section,
                        keep_code=record['code'],
                    )
                    store_record(data, final_section, merged_record)
                    summary['same_code_updates'] += 1
                    if final_section == 'sold_accounts' and same_code_section == 'accounts':
                        summary['sold_promotions'] += 1
                    break

                old_code = record['code']
                record, new_code = reassign_record_code(data, record)
                summary['code_collisions_resolved'] += 1
                summary['code_collision_details'].append(
                    {
                        'source': source_label,
                        'old_code': old_code,
                        'new_code': new_code,
                        'reason': 'same code used by a different account',
                    }
                )
                continue

            duplicate_candidates = find_duplicate_candidates(data, record)
            if len(duplicate_candidates) == 1:
                duplicate_match = duplicate_candidates[0]
                existing_record = data[duplicate_match['section']][duplicate_match['code']]
                final_section = (
                    'sold_accounts'
                    if incoming_section == 'sold_accounts' or duplicate_match['section'] == 'sold_accounts'
                    else 'accounts'
                )
                merged_record = merge_account_records(
                    existing_record,
                    record,
                    incoming_preferred=incoming_preferred,
                    final_section=final_section,
                    keep_code=duplicate_match['code'],
                )
                store_record(data, final_section, merged_record)
                summary['duplicates_merged'] += 1
                if final_section == 'sold_accounts' and duplicate_match['section'] == 'accounts':
                    summary['sold_promotions'] += 1
                summary['duplicate_details'].append(
                    {
                        'source': source_label,
                        'kept_code': duplicate_match['code'],
                        'merged_code': record['code'],
                        'reasons': duplicate_match['reasons'],
                    }
                )
                break

            if len(duplicate_candidates) > 1:
                summary['ambiguous_duplicates'] += 1
                summary['ambiguous_details'].append(
                    {
                        'source': source_label,
                        'code': record['code'],
                        'candidate_codes': [candidate['code'] for candidate in duplicate_candidates],
                        'reasons': sorted({reason for candidate in duplicate_candidates for reason in candidate['reasons']}),
                    }
                )

            store_record(data, incoming_section, record)
            break


def merge_sample_lists(base_samples, incoming_samples, summary):
    merged = []
    seen = set()

    for scope, stock_name, sample in base_samples + incoming_samples:
        signature = sample_signature(scope, stock_name, sample)
        if signature in seen:
            summary['market_sample_duplicates_skipped'] += 1
            continue
        seen.add(signature)
        merged.append((scope, stock_name, dict(sample)))

    return merged


def merge_stock_profiles(base_profiles, incoming_profiles, incoming_preferred):
    profiles = core.default_stock_profiles()

    for stock_name in core.STOCK_CHOICES:
        base_info = str(base_profiles.get(stock_name, {}).get('info', '')).strip()
        incoming_info = str(incoming_profiles.get(stock_name, {}).get('info', '')).strip()

        if incoming_preferred:
            merged_info = incoming_info or base_info
        else:
            merged_info = base_info or incoming_info

        profiles[stock_name]['info'] = merged_info

    return profiles


def merge_databases(base_data, incoming_data, incoming_label='incoming', incoming_preferred=True):
    merged = clone_database(base_data)
    summary = build_merge_summary()
    merged['deleted_accounts'] = merge_deleted_accounts(
        merged.get('deleted_accounts', []),
        incoming_data.get('deleted_accounts', []),
    )
    apply_deleted_accounts(merged, merged.get('deleted_accounts', []), summary)

    merge_records_into_data(
        merged,
        incoming_data.get('accounts', {}),
        'accounts',
        incoming_preferred=incoming_preferred,
        summary=summary,
        source_label=incoming_label,
    )
    merge_records_into_data(
        merged,
        incoming_data.get('sold_accounts', {}),
        'sold_accounts',
        incoming_preferred=incoming_preferred,
        summary=summary,
        source_label=incoming_label,
    )
    apply_deleted_accounts(merged, merged.get('deleted_accounts', []), summary)

    all_samples = []
    for sample in merged['pricing']['samples']:
        all_samples.append(('global', '', sample))
    for sample in incoming_data.get('pricing', {}).get('samples', []):
        all_samples.append(('global', '', sample))

    for stock_name in core.STOCK_CHOICES:
        for sample in merged['stock_profiles'][stock_name]['samples']:
            all_samples.append(('stock', stock_name, sample))
        for sample in incoming_data.get('stock_profiles', {}).get(stock_name, {}).get('samples', []):
            all_samples.append(('stock', stock_name, sample))

    merged_samples = merge_sample_lists([], all_samples, summary)
    merged['pricing']['samples'] = []
    for stock_name in core.STOCK_CHOICES:
        merged['stock_profiles'][stock_name]['samples'] = []

    for scope, stock_name, sample in merged_samples:
        if scope == 'global' or not stock_name:
            merged['pricing']['samples'].append(sample)
        else:
            merged['stock_profiles'][stock_name]['samples'].append(sample)

    merged['stock_profiles'] = merge_stock_profiles(
        merged['stock_profiles'],
        incoming_data.get('stock_profiles', {}),
        incoming_preferred=incoming_preferred,
    )

    merged = core.normalize_data(merged)
    return merged, summary


def build_result_summary(spreadsheet, data, merge_summary, snapshot_info=None):
    snapshot_info = snapshot_info or {}
    return {
        'spreadsheet_title': spreadsheet.title,
        'active_account_count': len(data['accounts']),
        'sold_account_count': len(data.get('sold_accounts', {})),
        'deleted_account_count': len(data.get('deleted_accounts', [])),
        'market_sample_count': len(rows_from_market_samples(data)),
        'stock_profile_count': len(core.STOCK_CHOICES),
        'duplicates_merged': merge_summary['duplicates_merged'],
        'ambiguous_duplicates': merge_summary['ambiguous_duplicates'],
        'code_collisions_resolved': merge_summary['code_collisions_resolved'],
        'same_code_updates': merge_summary['same_code_updates'],
        'sold_promotions': merge_summary['sold_promotions'],
        'deletions_applied': merge_summary['deletions_applied'],
        'market_sample_duplicates_skipped': merge_summary['market_sample_duplicates_skipped'],
        'sheet_last_push_at': snapshot_info.get('meta', {}).get('pushed_at', ''),
    }


def push_data_to_sheets(local_data):
    spreadsheet = open_spreadsheet()
    sheet_data, snapshot_info = read_spreadsheet_snapshot(spreadsheet)
    merged_data, merge_summary = merge_databases(
        sheet_data,
        local_data,
        incoming_label='local device',
        incoming_preferred=True,
    )

    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_ACCOUNTS,
        ACCOUNT_HEADERS,
        rows_from_account_records(merged_data['accounts']),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_SOLD_ACCOUNTS,
        SOLD_ACCOUNT_HEADERS,
        rows_from_account_records(merged_data.get('sold_accounts', {}), include_sale_fields=True),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_DELETED_ACCOUNTS,
        DELETED_ACCOUNT_HEADERS,
        rows_from_deleted_accounts(merged_data),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_MARKET_SAMPLES,
        MARKET_SAMPLE_HEADERS,
        rows_from_market_samples(merged_data),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_STOCK_PROFILES,
        STOCK_PROFILE_HEADERS,
        rows_from_stock_profiles(merged_data),
    )
    write_rows_to_worksheet(
        spreadsheet,
        WORKSHEET_META,
        META_HEADERS,
        rows_from_meta(merged_data, merge_summary=merge_summary),
    )

    return merged_data, build_result_summary(
        spreadsheet,
        merged_data,
        merge_summary,
        snapshot_info=snapshot_info,
    )


def pull_data_from_sheets(local_data):
    spreadsheet = open_spreadsheet()
    sheet_data, snapshot_info = read_spreadsheet_snapshot(spreadsheet)
    merged_data, merge_summary = merge_databases(
        local_data,
        sheet_data,
        incoming_label='google sheets',
        incoming_preferred=True,
    )

    return merged_data, build_result_summary(
        spreadsheet,
        merged_data,
        merge_summary,
        snapshot_info=snapshot_info,
    )
