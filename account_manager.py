#!/usr/bin/env python3
"""Termux account storage CLI with a phone-friendly MAUS interface."""

import json
import os
import re
import shutil
import sys
import textwrap
import unicodedata
from datetime import datetime

DATA_FILE = os.path.expanduser('~/.termux_accounts.json')
PRE_SHEETS_PULL_BACKUP_FILE = os.path.expanduser('~/.termux_accounts.pre_sheets_pull_backup.json')
STOCK_CHOICES = ('RA', 'PR', 'ON', 'MN', 'RP', 'SA')
STOCK_FULL_NAMES = {
    'RA': 'REAL ACCOUNT',
    'PR': 'PREMIUM ACCOUNT',
    'ON': 'ONE NAME',
    'MN': 'MIX NAME',
    'RP': 'RPNORMS',
    'SA': 'SELLER ACCOUNT',
}
ACCOUNT_CODE_PREFIX = 'ACC-'
ACCOUNT_CODE_DIGITS = 4
BACK_ACTION = '__BACK__'
SECTION_BREAK = '__SECTION_BREAK__'
APP_TITLE = 'MAUS ACCOUNT TRACKER'
APP_SUBTITLE = 'Phone-ready stock console'
APP_OWNER = 'Owner codename: MAUS'
ACCOUNT_FIELD_ALIASES = {
    'name': 'name',
    'fullname': 'name',
    'accountname': 'name',
    'account': 'name',
    'user': 'name',
    'username': 'name',
    'email': 'email',
    'mail': 'email',
    'gmail': 'email',
    'link': 'link',
    'url': 'link',
    'profile': 'link',
    'profilelink': 'link',
    'password': 'password',
    'pass': 'password',
    'pw': 'password',
    'fbfs': 'fbfs',
    'friends': 'fbfs',
    'friendcount': 'fbfs',
    'note': 'notes',
    'notes': 'notes',
    'remark': 'notes',
    'remarks': 'notes',
    'info': 'notes',
}
ACCOUNT_FIELD_SYMBOL_ALIASES = {
    '✉': 'email',
    '✉️': 'email',
    '📧': 'email',
    '🗝': 'password',
    '🗝️': 'password',
    '🔑': 'password',
    '🔗': 'link',
    '🌐': 'link',
    '👥': 'fbfs',
    '👤': 'name',
    '📝': 'notes',
}
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
URL_PATTERN = re.compile(r'^(?:https?://|www\.|[a-z0-9.-]+\.[a-z]{2,}(?:[/?#]|$))', re.IGNORECASE)
MENU_OPTIONS = (
    ('1', 'Add account', 'Bulk add one stock batch at a time'),
    ('2', 'List accounts', 'See every stored account and store value'),
    ('3', 'Get stock', 'Open full details by code or name'),
    ('4', 'Manage account', 'Edit, sell, delete, or set stock info from one place'),
    ('5', 'View sold history', 'Check sold price, market comparison, and date'),
    ('6', 'Add market price sample', 'Feed auto-pricing with market data'),
    ('7', 'View market state', 'See the latest market condition per stock'),
    ('8', 'View pricing summary', 'Review prices, samples, and totals'),
    ('9', 'Push local data to Google Sheets', 'Merge this device into your shared spreadsheet backup'),
    ('10', 'Pull data from Google Sheets', 'Merge the shared spreadsheet backup into this device'),
    ('11', 'Exit', 'Close the MAUS console'),
)
ANSI_CODES = {
    'reset': '\033[0m',
    'bold': '\033[1m',
    'dim': '\033[2m',
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'magenta': '\033[35m',
    'cyan': '\033[36m',
    'white': '\033[37m',
    'bright_black': '\033[90m',
    'bright_red': '\033[91m',
    'bright_green': '\033[92m',
    'bright_yellow': '\033[93m',
    'bright_blue': '\033[94m',
    'bright_magenta': '\033[95m',
    'bright_cyan': '\033[96m',
}


def color_enabled():
    if os.environ.get('NO_COLOR'):
        return False
    return sys.stdout.isatty() and os.environ.get('TERM', '').lower() != 'dumb'


def style(text, *tokens):
    if not color_enabled():
        return text

    prefix = ''.join(ANSI_CODES.get(token, '') for token in tokens)
    if not prefix:
        return text
    return f'{prefix}{text}{ANSI_CODES["reset"]}'


def terminal_width():
    try:
        columns = shutil.get_terminal_size((84, 20)).columns
    except OSError:
        columns = 84
    return min(max(columns, 30), 110)


def wrap_text(value, width):
    text = str(value)
    if not text:
        return ['']

    return textwrap.wrap(
        text,
        width=width,
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=True,
    ) or ['']


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_message(label, message, *tone):
    print(style(f'[{label}] {message}', *tone))


def print_info(message):
    print_message('INFO', message, 'bright_cyan')


def print_success(message):
    print_message('OK', message, 'bold', 'bright_green')


def print_warning(message):
    print_message('WARN', message, 'bold', 'bright_yellow')


def print_error(message):
    print_message('ERROR', message, 'bold', 'bright_red')


def prompt_input(message, *tone):
    prompt = style(message, *(tone or ('bright_cyan', 'bold')))
    return input(prompt)


def section_rule(character='.'):
    width = min(terminal_width(), 44)
    return character * width


def format_detail_line(label, value, label_width=11):
    cleaned_label = str(label).strip().upper()
    return f'{cleaned_label:<{label_width}} {value}'


def panel_line_prefix(text):
    raw_text = str(text)
    stripped_text = raw_text.lstrip()
    if not stripped_text:
        return ''
    if raw_text.startswith(' ') or stripped_text.startswith('['):
        return ''
    return '  '


def print_panel(title, lines, tone='bright_blue'):
    width = terminal_width()
    divider_length = min(width, max(24, len(title) + 8))

    print()
    print(style(f':: {title}', 'bold', tone))
    print(style('-' * divider_length, 'dim', tone))

    for raw_line in lines:
        line_text = raw_line
        line_tones = ()
        if isinstance(raw_line, (tuple, list)) and raw_line:
            line_text = raw_line[0]
            line_tones = tuple(raw_line[1:])

        if line_text == SECTION_BREAK:
            print(style(section_rule(), 'dim', tone))
            continue

        prefix = panel_line_prefix(line_text)
        wrap_width = max(10, width - len(prefix))
        wrapped_segments = wrap_text(line_text, wrap_width)
        if not wrapped_segments:
            print()
            continue

        for segment in wrapped_segments:
            if line_tones:
                segment = style(segment, *line_tones)
            print(f'{prefix}{segment}')

    print()


def pause_for_continue():
    prompt_input('\nPress Enter to return to the MAUS dashboard... ', 'bright_black')


def expand_user_path(path_value):
    return os.path.abspath(os.path.expanduser(str(path_value).strip()))


def default_stock_profiles():
    return {
        stock_name: {
            'info': '',
            'samples': [],
        }
        for stock_name in STOCK_CHOICES
    }


def default_database():
    return {
        'accounts': {},
        'sold_accounts': {},
        'deleted_accounts': [],
        'pricing': {
            'samples': [],
        },
        'stock_profiles': default_stock_profiles(),
    }


def looks_like_account_code(value):
    if not isinstance(value, str):
        return False

    normalized = value.strip().upper()
    return normalized.startswith(ACCOUNT_CODE_PREFIX) and normalized[len(ACCOUNT_CODE_PREFIX):].isdigit()


def make_account_code(number):
    return f'{ACCOUNT_CODE_PREFIX}{number:0{ACCOUNT_CODE_DIGITS}d}'


def stock_alias_key(value):
    return ''.join(character for character in str(value).upper() if character.isalnum())


def normalize_stock_name(value):
    cleaned = str(value).strip()
    if not cleaned:
        return ''

    upper_cleaned = cleaned.upper()
    if upper_cleaned in STOCK_CHOICES:
        return upper_cleaned

    alias_map = {stock_alias_key(stock_name): stock_name for stock_name in STOCK_CHOICES}
    alias_map.update({stock_alias_key(full_name): stock_name for stock_name, full_name in STOCK_FULL_NAMES.items()})
    return alias_map.get(stock_alias_key(cleaned), upper_cleaned)


def get_stock_full_name(stock_name):
    normalized = normalize_stock_name(stock_name)
    return STOCK_FULL_NAMES.get(normalized, normalized or str(stock_name).strip() or 'UNKNOWN')


def format_stock_label(stock_name):
    normalized = normalize_stock_name(stock_name)
    if normalized in STOCK_FULL_NAMES:
        return f'{normalized} - {STOCK_FULL_NAMES[normalized]}'
    return normalized or str(stock_name).strip() or 'UNKNOWN'


def get_stock_sheet_name(stock_name):
    normalized = normalize_stock_name(stock_name)
    if normalized in STOCK_FULL_NAMES:
        return STOCK_FULL_NAMES[normalized]
    return normalized or str(stock_name).strip()


def generate_unique_account_code(used_codes):
    highest_number = 0
    for code in used_codes:
        if looks_like_account_code(code):
            highest_number = max(highest_number, int(code[len(ACCOUNT_CODE_PREFIX):]))

    next_number = highest_number + 1
    while True:
        code = make_account_code(next_number)
        if code not in used_codes:
            return code
        next_number += 1


def parse_stock_choice(raw_value):
    normalized = str(raw_value).strip().upper()
    choice_map = {str(index): stock_name for index, stock_name in enumerate(STOCK_CHOICES, start=1)}
    return normalize_stock_name(choice_map.get(normalized, normalized))


def normalize_optional_text(value):
    cleaned = str(value).strip()
    if cleaned.upper() in ('-', 'NONE', 'N/A'):
        return ''
    return cleaned


def is_decorative_character(character):
    if not character:
        return False
    if character.isalnum():
        return False
    if character in '@/#&.=+_-':
        return False

    category = unicodedata.category(character)
    if category.startswith('S'):
        return True
    if category in ('Cf', 'Mn'):
        return True
    return character in '?:;|~`^*()[]{}<>,'


def strip_decorative_prefix(value):
    text = str(value).strip()
    while text and (text[0].isspace() or is_decorative_character(text[0])):
        text = text[1:].lstrip()
    return text


def parse_whole_number_text(value):
    cleaned = strip_decorative_prefix(value).replace(',', '').replace('_', '').replace(' ', '')
    if not cleaned:
        raise ValueError('empty whole number')
    return int(cleaned)


def normalize_account_field_label(value):
    return ''.join(character for character in str(value).lower() if character.isalnum())


def parse_labeled_account_part(value):
    text = str(value).strip()
    if not text:
        return None, None

    match = re.match(r'^(.{1,24}?)\s*[:=]\s*(.*)$', text)
    if not match:
        return None, None

    raw_label = match.group(1).strip()
    field_value = match.group(2).strip()
    normalized_label = normalize_account_field_label(raw_label)
    compact_label = ''.join(raw_label.split())
    field_name = ACCOUNT_FIELD_ALIASES.get(normalized_label) or ACCOUNT_FIELD_SYMBOL_ALIASES.get(compact_label)

    if not field_name:
        if looks_like_email(field_value):
            field_name = 'email'
        elif looks_like_link(field_value):
            field_name = 'link'
        elif looks_like_fbfs(field_value):
            field_name = 'fbfs'
        elif any(token in normalized_label for token in ('password', 'pass', 'pw', 'key')):
            field_name = 'password'
        elif not normalized_label or '?' in raw_label:
            field_name = 'password'

    if not field_name:
        return None, None

    return field_name, field_value


def looks_like_email(value):
    return bool(EMAIL_PATTERN.match(strip_decorative_prefix(value)))


def looks_like_link(value):
    text = strip_decorative_prefix(value)
    if not text or looks_like_email(text):
        return False
    return bool(URL_PATTERN.match(text))


def looks_like_fbfs(value):
    try:
        parse_whole_number_text(value)
    except (TypeError, ValueError):
        return False
    return True


def pop_best_matching_part(parts, predicate):
    for index, value in enumerate(parts):
        if predicate(value):
            return parts.pop(index)
    return ''


def pop_best_name_part(parts):
    for index, value in enumerate(parts):
        text = strip_decorative_prefix(value)
        if ' ' in text:
            return strip_decorative_prefix(parts.pop(index))
    for index, value in enumerate(parts):
        text = strip_decorative_prefix(value)
        letter_count = sum(character.isalpha() for character in text)
        if letter_count >= max(3, len(text) // 2):
            return strip_decorative_prefix(parts.pop(index))
    return strip_decorative_prefix(parts.pop(0)) if parts else ''


def pop_best_password_part(parts):
    for index, value in enumerate(parts):
        if ' ' not in str(value).strip():
            return parts.pop(index)
    return parts.pop(0) if parts else ''


def clean_detected_account_value(field_name, value):
    text = str(value).strip()
    if field_name != 'password':
        text = strip_decorative_prefix(text)
    if field_name == 'fbfs' and text:
        try:
            return str(parse_whole_number_text(text))
        except ValueError:
            return text
    return text


def parse_flexible_account_parts(parts):
    stripped_parts = [str(part).strip() for part in parts if str(part).strip()]
    if len(stripped_parts) < 4:
        return None, 'Need at least name, email, password, and fbfs.'

    row = {
        'name': '',
        'link': '',
        'email': '',
        'password': '',
        'fbfs': '',
        'notes': '',
    }
    leftovers = []

    for part in stripped_parts:
        field_name, field_value = parse_labeled_account_part(part)
        if field_name and not row[field_name]:
            row[field_name] = clean_detected_account_value(field_name, field_value)
        else:
            leftovers.append(part)

    if not row['email']:
        row['email'] = clean_detected_account_value('email', pop_best_matching_part(leftovers, looks_like_email))
    if not row['link']:
        row['link'] = clean_detected_account_value('link', pop_best_matching_part(leftovers, looks_like_link))
    if not row['fbfs']:
        detected_fbfs = pop_best_matching_part(leftovers, looks_like_fbfs)
        if detected_fbfs:
            row['fbfs'] = clean_detected_account_value('fbfs', detected_fbfs)

    if not row['name']:
        row['name'] = clean_detected_account_value('name', pop_best_name_part(leftovers))
    if not row['password']:
        row['password'] = clean_detected_account_value('password', pop_best_password_part(leftovers))
    if not row['notes'] and leftovers:
        row['notes'] = ' | '.join(clean_detected_account_value('notes', part) for part in leftovers if str(part).strip())

    return row, None


def normalize_non_negative_int(value, default=0):
    try:
        normalized = parse_whole_number_text(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized >= 0 else default


def normalize_non_negative_float(value, default=0.0):
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized >= 0 else default


def normalize_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def current_timestamp_text():
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def current_date_text():
    return datetime.now().strftime('%Y-%m-%d')


def normalize_accounts(accounts):
    if not isinstance(accounts, dict):
        return {}

    normalized = {}
    used_codes = set()
    pending_records = []

    for key, info in accounts.items():
        if not isinstance(info, dict):
            continue

        raw_key = str(key).strip()
        stock_name = normalize_stock_name(info.get('stock_name', ''))
        if not stock_name:
            stock_name = normalize_stock_name(info.get('tag', ''))
        if not stock_name and raw_key and not looks_like_account_code(raw_key):
            stock_name = normalize_stock_name(raw_key) or raw_key.upper()

        record = {
            'code': str(info.get('code', '')).strip().upper(),
            'stock_name': stock_name,
            'name': str(info.get('name', '')).strip(),
            'link': normalize_optional_text(info.get('link', '')),
            'email': str(info.get('email', '')).strip(),
            'password': str(info.get('password', '')).strip(),
            'notes': normalize_optional_text(info.get('notes', '')),
            'fbfs': normalize_non_negative_int(info.get('fbfs', 0)),
            'updated_at': str(info.get('updated_at', '')).strip(),
        }

        if not record['code'] and looks_like_account_code(raw_key):
            record['code'] = raw_key.upper()

        if record['code'] and looks_like_account_code(record['code']) and record['code'] not in used_codes:
            used_codes.add(record['code'])
            if not record['stock_name']:
                record['stock_name'] = 'UNKNOWN'
            normalized[record['code']] = record
        else:
            pending_records.append(record)

    for record in pending_records:
        code = generate_unique_account_code(used_codes)
        record['code'] = code
        if not record['stock_name']:
            record['stock_name'] = 'UNKNOWN'
        used_codes.add(code)
        normalized[code] = record

    return normalized


def normalize_samples(samples):
    if not isinstance(samples, list):
        return []

    normalized = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue

        try:
            total_price_php = float(sample.get('total_price_php', 0))
            account_count = int(sample.get('account_count', 0))
        except (TypeError, ValueError):
            continue

        if total_price_php <= 0 or account_count <= 0:
            continue

        normalized.append(
            {
                'total_price_php': round(total_price_php, 2),
                'account_count': account_count,
                'note': str(sample.get('note', '')).strip(),
                'recorded_at': str(
                    sample.get('recorded_at') or sample.get('created_at') or ''
                ).strip(),
            }
        )

    return normalized


def normalize_sold_accounts(raw_sold_accounts):
    if not isinstance(raw_sold_accounts, dict):
        return {}

    normalized = {}
    used_codes = set()
    pending_records = []

    for key, info in raw_sold_accounts.items():
        if not isinstance(info, dict):
            continue

        raw_key = str(key).strip()
        stock_name = normalize_stock_name(info.get('stock_name', ''))
        if not stock_name:
            stock_name = normalize_stock_name(info.get('tag', ''))
        if not stock_name and raw_key and not looks_like_account_code(raw_key):
            stock_name = normalize_stock_name(raw_key) or raw_key.upper()

        market_price_php = normalize_non_negative_float(info.get('market_price_php'))
        sold_price_php = normalize_non_negative_float(info.get('sold_price_php'))
        difference_php = sold_price_php - market_price_php if market_price_php > 0 else 0.0
        difference_percent = 0.0
        if market_price_php > 0:
            difference_percent = (difference_php / market_price_php) * 100

        record = {
            'code': str(info.get('code', '')).strip().upper(),
            'stock_name': stock_name,
            'name': str(info.get('name', '')).strip(),
            'link': normalize_optional_text(info.get('link', '')),
            'email': str(info.get('email', '')).strip(),
            'password': str(info.get('password', '')).strip(),
            'notes': normalize_optional_text(info.get('notes', '')),
            'fbfs': normalize_non_negative_int(info.get('fbfs', 0)),
            'updated_at': str(info.get('updated_at', info.get('sold_at', ''))).strip(),
            'sold_price_php': round(sold_price_php, 2),
            'sold_at': str(info.get('sold_at', '')).strip(),
            'sold_note': normalize_optional_text(info.get('sold_note', info.get('sale_note', ''))),
            'market_price_php': round(market_price_php, 2) if market_price_php > 0 else 0.0,
            'price_difference_php': round(
                normalize_float(info.get('price_difference_php', difference_php), difference_php),
                2,
            ),
            'price_difference_percent': round(
                normalize_float(info.get('price_difference_percent', difference_percent), difference_percent),
                2,
            ),
            'pricing_source': str(info.get('pricing_source', '')).strip(),
        }

        if not record['code'] and looks_like_account_code(raw_key):
            record['code'] = raw_key.upper()

        if record['code'] and looks_like_account_code(record['code']) and record['code'] not in used_codes:
            used_codes.add(record['code'])
            if not record['stock_name']:
                record['stock_name'] = 'UNKNOWN'
            normalized[record['code']] = record
        else:
            pending_records.append(record)

    for record in pending_records:
        code = generate_unique_account_code(used_codes)
        record['code'] = code
        if not record['stock_name']:
            record['stock_name'] = 'UNKNOWN'
        used_codes.add(code)
        normalized[code] = record

    return normalized


def normalize_stock_profiles(raw_profiles):
    profiles = default_stock_profiles()
    if not isinstance(raw_profiles, dict):
        return profiles

    for stock_name in STOCK_CHOICES:
        raw_profile = raw_profiles.get(stock_name, {})
        if not isinstance(raw_profile, dict):
            continue

        profiles[stock_name] = {
            'info': str(raw_profile.get('info', '')).strip(),
            'samples': normalize_samples(raw_profile.get('samples', [])),
        }

    return profiles


def deleted_account_signature(entry):
    return (
        str(entry.get('code', '')).strip().upper(),
        str(entry.get('email', '')).strip().lower(),
        normalize_optional_text(entry.get('link', '')).lower(),
        normalize_stock_name(entry.get('stock_name', '')),
        str(entry.get('name', '')).strip().lower(),
    )


def normalize_deleted_accounts(raw_deleted_accounts):
    if isinstance(raw_deleted_accounts, dict):
        candidate_items = raw_deleted_accounts.values()
    elif isinstance(raw_deleted_accounts, list):
        candidate_items = raw_deleted_accounts
    else:
        return []

    normalized = {}
    for item in candidate_items:
        if not isinstance(item, dict):
            continue

        record = {
            'code': str(item.get('code', '')).strip().upper(),
            'stock_name': normalize_stock_name(item.get('stock_name', '')),
            'name': str(item.get('name', '')).strip(),
            'link': normalize_optional_text(item.get('link', '')),
            'email': str(item.get('email', '')).strip(),
            'password': str(item.get('password', '')).strip(),
            'deleted_at': str(item.get('deleted_at', item.get('updated_at', ''))).strip(),
        }

        signature = deleted_account_signature(record)
        if not any(signature):
            continue

        existing = normalized.get(signature)
        if not existing or record['deleted_at'] >= existing.get('deleted_at', ''):
            normalized[signature] = record

    return sorted(
        normalized.values(),
        key=lambda entry: (
            entry.get('deleted_at', ''),
            entry.get('code', ''),
            entry.get('email', ''),
            entry.get('name', ''),
        ),
        reverse=True,
    )


def normalize_data(raw_data):
    database = default_database()
    if not isinstance(raw_data, dict):
        return database

    if 'accounts' in raw_data or 'pricing' in raw_data or 'stock_profiles' in raw_data or 'tag_profiles' in raw_data:
        database['accounts'] = normalize_accounts(raw_data.get('accounts', {}))
        database['sold_accounts'] = normalize_sold_accounts(raw_data.get('sold_accounts', {}))
        database['deleted_accounts'] = normalize_deleted_accounts(raw_data.get('deleted_accounts', []))

        pricing = raw_data.get('pricing', {})
        if isinstance(pricing, dict):
            database['pricing']['samples'] = normalize_samples(pricing.get('samples', []))

        raw_profiles = raw_data.get('stock_profiles', raw_data.get('tag_profiles', {}))
        database['stock_profiles'] = normalize_stock_profiles(raw_profiles)
        return database

    database['accounts'] = normalize_accounts(raw_data)
    return database


def load_data():
    if not os.path.exists(DATA_FILE):
        return default_database()

    try:
        return load_data_from_path(DATA_FILE)
    except json.JSONDecodeError:
        return default_database()


def save_data(data):
    save_data_to_path(data, DATA_FILE)


def load_data_from_path(path):
    with open(path, 'r', encoding='utf-8') as file_handle:
        raw_data = json.load(file_handle)
    return normalize_data(raw_data)


def save_data_to_path(data, path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)


def build_deleted_account_entry(account, deleted_at=''):
    return {
        'code': str(account.get('code', '')).strip().upper(),
        'stock_name': normalize_stock_name(account.get('stock_name', '')),
        'name': str(account.get('name', '')).strip(),
        'link': normalize_optional_text(account.get('link', '')),
        'email': str(account.get('email', '')).strip(),
        'password': str(account.get('password', '')).strip(),
        'deleted_at': str(deleted_at or current_timestamp_text()).strip(),
    }


def remember_deleted_account(data, account, deleted_at=''):
    deleted_accounts = list(data.get('deleted_accounts', []))
    deleted_accounts.append(build_deleted_account_entry(account, deleted_at=deleted_at))
    data['deleted_accounts'] = normalize_deleted_accounts(deleted_accounts)


def format_php(amount):
    return f'PHP {amount:,.2f}'


def parse_price_text(raw_value):
    cleaned = (
        raw_value.strip()
        .lower()
        .replace('php', '')
        .replace('\u20b1', '')
        .replace(',', '')
        .strip()
    )
    return float(cleaned)


def build_price_metrics(samples, inventory_count):
    if not samples:
        return None

    total_price = sum(sample['total_price_php'] for sample in samples)
    total_accounts = sum(sample['account_count'] for sample in samples)
    if total_accounts <= 0:
        return None

    unit_price = total_price / total_accounts
    return {
        'sample_count': len(samples),
        'market_account_count': total_accounts,
        'market_total_price': total_price,
        'unit_price': unit_price,
        'inventory_count': inventory_count,
        'inventory_value': unit_price * inventory_count,
    }


def count_accounts_for_stock(data, stock_name):
    return sum(1 for account in data['accounts'].values() if account.get('stock_name') == stock_name)


def get_global_price_metrics(data, inventory_count=None):
    if inventory_count is None:
        inventory_count = len(data['accounts'])

    metrics = build_price_metrics(data['pricing']['samples'], inventory_count)
    if metrics:
        metrics['source'] = 'global market samples'
    return metrics


def get_stock_price_metrics(data, stock_name):
    inventory_count = count_accounts_for_stock(data, stock_name)
    profile = data['stock_profiles'].get(stock_name, {'info': '', 'samples': []})

    metrics = build_price_metrics(profile.get('samples', []), inventory_count)
    if metrics:
        metrics['source'] = f'{stock_name} market samples'
        return metrics

    metrics = get_global_price_metrics(data, inventory_count=inventory_count)
    if metrics:
        metrics['source'] = f'global market samples fallback for {stock_name}'
        return metrics

    return None


def get_stock_info(data, stock_name):
    profile = data['stock_profiles'].get(stock_name, {})
    return str(profile.get('info', '')).strip()


def get_all_account_codes(data):
    codes = set(data['accounts'].keys())
    codes.update(data.get('sold_accounts', {}).keys())
    return codes


def generate_next_account_code(data):
    return generate_unique_account_code(get_all_account_codes(data))


def count_sold_accounts_for_stock(data, stock_name):
    return sum(1 for account in data.get('sold_accounts', {}).values() if account.get('stock_name') == stock_name)


def get_sales_summary(data):
    sold_accounts = list(data.get('sold_accounts', {}).values())
    sold_count = len(sold_accounts)
    total_sales_value = sum(account.get('sold_price_php', 0.0) for account in sold_accounts)

    sold_with_market = [account for account in sold_accounts if account.get('market_price_php', 0.0) > 0]
    total_market_reference = sum(account.get('market_price_php', 0.0) for account in sold_with_market)
    total_difference = sum(account.get('price_difference_php', 0.0) for account in sold_with_market)

    return {
        'sold_count': sold_count,
        'total_sales_value': total_sales_value,
        'market_compared_count': len(sold_with_market),
        'total_market_reference': total_market_reference,
        'total_difference': total_difference,
    }


def format_signed_php(amount):
    sign = '+' if amount >= 0 else '-'
    return f'{sign}{format_php(abs(amount))}'


def format_signed_percent(amount):
    sign = '+' if amount >= 0 else '-'
    return f'{sign}{abs(amount):.2f}%'


def get_sample_unit_price(sample):
    account_count = sample.get('account_count', 0)
    if account_count <= 0:
        return 0.0
    return sample.get('total_price_php', 0.0) / account_count


def get_market_state(samples):
    if not samples:
        return None

    metrics = build_price_metrics(samples, inventory_count=0)
    latest_sample = samples[-1]
    latest_unit_price = get_sample_unit_price(latest_sample)

    previous_unit_price = None
    movement_php = None
    direction = 'steady'
    if len(samples) >= 2:
        previous_unit_price = get_sample_unit_price(samples[-2])
        movement_php = latest_unit_price - previous_unit_price
        if movement_php > 0:
            direction = 'up'
        elif movement_php < 0:
            direction = 'down'

    unit_prices = [get_sample_unit_price(sample) for sample in samples]
    return {
        'sample_count': len(samples),
        'weighted_unit_price': metrics['unit_price'] if metrics else 0.0,
        'latest_unit_price': latest_unit_price,
        'latest_total_price': latest_sample.get('total_price_php', 0.0),
        'latest_account_count': latest_sample.get('account_count', 0),
        'latest_note': latest_sample.get('note', ''),
        'latest_recorded_at': latest_sample.get('recorded_at', ''),
        'previous_unit_price': previous_unit_price,
        'movement_php': movement_php,
        'direction': direction,
        'highest_unit_price': max(unit_prices),
        'lowest_unit_price': min(unit_prices),
    }


def get_stock_market_state(data, stock_name):
    profile = data['stock_profiles'].get(stock_name, {'samples': []})
    return get_market_state(profile.get('samples', []))


def get_global_market_state(data):
    return get_market_state(data['pricing']['samples'])


def describe_sale_vs_market(sold_record):
    market_price = sold_record.get('market_price_php', 0.0)
    if market_price <= 0:
        return 'No market comparison saved.'

    difference_php = sold_record.get('price_difference_php', 0.0)
    difference_percent = sold_record.get('price_difference_percent', 0.0)
    if difference_php > 0:
        return f'Above market by {format_signed_php(difference_php)} ({format_signed_percent(difference_percent)})'
    if difference_php < 0:
        return f'Below market by {format_php(abs(difference_php))} ({format_signed_percent(difference_percent)})'
    return 'Matched market price.'


def format_account_brief(data, account):
    stock_name = account.get('stock_name', '')
    metrics = get_stock_price_metrics(data, stock_name)

    parts = [
        account.get('code', 'NO-CODE'),
        format_stock_label(stock_name),
    ]
    if account.get('name'):
        parts.append(account['name'])
    if account.get('password'):
        parts.append(f'pass: {account["password"]}')
    parts.append(f'fbfs: {account.get("fbfs", 0)}')
    if metrics:
        parts.append(format_php(metrics['unit_price']))

    return ' | '.join(parts)


def format_inventory_stock_tag(stock_name):
    normalized = normalize_stock_name(stock_name)
    if normalized in STOCK_CHOICES:
        return get_stock_full_name(normalized)
    return get_stock_full_name(stock_name)


def build_inventory_account_lines(data, account):
    stock_name = account.get('stock_name', '')
    metrics = get_stock_price_metrics(data, stock_name)
    price_text = format_php(metrics['unit_price']) if metrics else 'no price yet'
    price_tone = ('bold', 'bright_green') if metrics else ('bold', 'bright_yellow')

    lines = [
        (f'[{account.get("code", "NO-CODE")}]  {format_inventory_stock_tag(stock_name)}', 'bold', 'bright_cyan'),
        format_detail_line('Name', account.get('name') or 'no name saved'),
        (format_detail_line('Price', price_text), *price_tone),
        SECTION_BREAK,
    ]

    return lines


def search_accounts(data, query):
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    normalized_code = cleaned_query.upper()
    if normalized_code in data['accounts']:
        return [data['accounts'][normalized_code]]

    lowered_query = cleaned_query.lower()
    exact_matches = []
    partial_matches = []

    for account in data['accounts'].values():
        fields = [
            account.get('code', ''),
            account.get('stock_name', ''),
            get_stock_full_name(account.get('stock_name', '')),
            account.get('name', ''),
            account.get('email', ''),
        ]
        lowered_fields = [field.lower() for field in fields if field]
        if lowered_query in lowered_fields:
            exact_matches.append(account)
        elif any(lowered_query in field for field in lowered_fields):
            partial_matches.append(account)

    matches = exact_matches if exact_matches else partial_matches
    return sorted(matches, key=lambda account: account.get('code', ''))


def pick_account(data, prompt_message, empty_message='No matching account found.'):
    query = prompt_input(prompt_message).strip()
    matches = search_accounts(data, query)
    if not matches:
        print_warning(empty_message)
        return None

    if len(matches) == 1:
        return matches[0]

    lines = [
        'Multiple matches found. Use the code of the account you want.',
        '',
    ]
    for account in matches:
        lines.append(format_account_brief(data, account))

    print_panel('Multiple Matches', lines, tone='bright_yellow')

    matching_codes = {account.get('code', '') for account in matches}
    chosen_code = prompt_input('Enter the account code to continue: ', 'bright_yellow', 'bold').strip().upper()
    if chosen_code not in matching_codes:
        print_error('Invalid code.')
        return None

    return data['accounts'][chosen_code]


def get_store_value_summary(data):
    total_value = 0.0
    priced_accounts = 0

    for account in data['accounts'].values():
        metrics = get_stock_price_metrics(data, account.get('stock_name', ''))
        if not metrics:
            continue
        total_value += metrics['unit_price']
        priced_accounts += 1

    inventory_count = len(data['accounts'])
    return {
        'inventory_count': inventory_count,
        'priced_accounts': priced_accounts,
        'unpriced_accounts': inventory_count - priced_accounts,
        'inventory_value': total_value,
    }


def build_stock_overview_lines(data):
    lines = []
    for stock_name in STOCK_CHOICES:
        inventory_count = count_accounts_for_stock(data, stock_name)
        sold_count = count_sold_accounts_for_stock(data, stock_name)
        metrics = get_stock_price_metrics(data, stock_name)
        price_text = format_php(metrics['unit_price']) if metrics else 'no price'
        line_tone = ('bold', 'bright_green') if metrics else ('bold', 'bright_yellow')
        lines.append((f'[{stock_name}]', 'bold', 'bright_cyan'))
        lines.append((format_detail_line('In stock', inventory_count), 'white'))
        lines.append((format_detail_line('Sold', sold_count), 'bright_black'))
        lines.append((format_detail_line('Price', price_text), *line_tone))
        lines.append(SECTION_BREAK)

    if lines and lines[-1] == SECTION_BREAK:
        lines.pop()
    return lines


def build_menu_lines(options, accent_tone='bright_cyan'):
    lines = []
    for key, label, description in options:
        lines.append((f'[{key}] {label}', 'bold', accent_tone))
        lines.append((f'    {description}', 'bright_black'))
        lines.append('')

    if lines and not lines[-1]:
        lines.pop()
    return lines


def show_dashboard(data):
    store_summary = get_store_value_summary(data)
    sales_summary = get_sales_summary(data)
    lines = [
        (APP_OWNER, 'bright_magenta'),
        (APP_SUBTITLE, 'bright_black'),
        SECTION_BREAK,
        (format_detail_line('Inventory', f'{store_summary["inventory_count"]} account(s)'), 'bold', 'white'),
        (format_detail_line('Priced', store_summary["priced_accounts"]), 'bright_black'),
        (format_detail_line('Unpriced', store_summary["unpriced_accounts"]), 'bright_black'),
        (format_detail_line('Store value', format_php(store_summary["inventory_value"])), 'bold', 'bright_green'),
        (format_detail_line('Sold value', format_php(sales_summary["total_sales_value"])), 'bold', 'bright_yellow'),
        SECTION_BREAK,
        ('Stock overview', 'bold', 'bright_cyan'),
    ]
    lines.extend(build_stock_overview_lines(data))
    print_panel(APP_TITLE, lines, tone='bright_cyan')


def show_main_menu(data):
    clear_screen()
    show_dashboard(data)
    print_panel('Main Menu', build_menu_lines(MENU_OPTIONS), tone='bright_blue')


def show_action_header(title, detail=''):
    lines = [detail] if detail else ['']
    print_panel(title, lines, tone='bright_magenta')


def manage_account_menu(data):
    show_action_header('Manage Account', 'Edit, sell, delete, or set stock info without crowding the main menu.')
    lines = build_menu_lines(
        (
            ('1', 'Edit account', 'Update fbfs, password, notes, or other saved fields.'),
            ('2', 'Mark account as sold', 'Move an active account into sold history.'),
            ('3', 'Set stock info', 'Save notes for RA, PR, ON, MN, RP, or SA.'),
            ('4', 'Delete account', 'Remove a stock entry safely.'),
            ('0', 'Back', 'Return to the main menu.'),
        )
    )
    print_panel('Manage Menu', lines, tone='bright_blue')

    choice = prompt_input('Choose manage action: ').strip()
    clear_screen()

    if choice in ('0', 'B', 'BACK'):
        print_warning('Back to main menu.')
        return
    if choice == '1':
        edit_account(data)
        return
    if choice == '2':
        mark_account_sold(data)
        return
    if choice == '3':
        set_stock_info(data)
        return
    if choice == '4':
        delete_account(data)
        return

    print_error('Invalid choice.')


def prompt_positive_float(message):
    raw_value = prompt_input(message).strip()
    try:
        value = parse_price_text(raw_value)
    except ValueError:
        print_error('Please enter a valid price, for example 54, 54php, PHP 54, or 1,250.')
        return None

    if value <= 0:
        print_error('Value must be greater than zero.')
        return None

    return round(value, 2)


def prompt_positive_int(message):
    raw_value = prompt_input(message).strip()
    try:
        value = parse_whole_number_text(raw_value)
    except ValueError:
        print_error('Please enter a whole number.')
        return None

    if value <= 0:
        print_error('Value must be greater than zero.')
        return None

    return value


def prompt_timestamp_with_default(message, default_value):
    raw_value = prompt_input(message).strip()
    return raw_value or default_value


def format_current_value(value, blank_label='blank'):
    text = str(value).strip()
    return text if text else blank_label


def prompt_edit_text(field_name, current_value, allow_clear=False):
    current_text = format_current_value(current_value)
    while True:
        suffix = ' (Enter to keep'
        if allow_clear:
            suffix += ', "-" to clear'
        suffix += '): '

        raw_value = prompt_input(f'{field_name} [{current_text}]{suffix}').strip()
        if raw_value == '':
            return str(current_value).strip()
        if allow_clear and raw_value == '-':
            return ''
        return raw_value


def prompt_edit_fbfs(current_value):
    current_fbfs = normalize_non_negative_int(current_value, 0)
    while True:
        raw_value = prompt_input(f'fbfs [{current_fbfs}] (Enter to keep): ').strip()
        if raw_value == '':
            return current_fbfs
        try:
            updated_fbfs = parse_whole_number_text(raw_value)
        except ValueError:
            print_error('fbfs must be a whole number.')
            continue
        if updated_fbfs < 0:
            print_error('fbfs cannot be negative.')
            continue
        return updated_fbfs


def prompt_edit_stock_name(current_stock_name):
    current_stock_name = str(current_stock_name).strip().upper() or 'UNKNOWN'
    while True:
        raw_value = prompt_input(
            f'Stock [{format_stock_label(current_stock_name)}] (Enter to keep, number/name to change, 0 to cancel): '
        ).strip().upper()
        if raw_value == '':
            return current_stock_name
        if raw_value in ('0', 'B', 'BACK'):
            return BACK_ACTION

        stock_name = parse_stock_choice(raw_value)
        if stock_name not in STOCK_CHOICES:
            print_error(f'Invalid stock name. Use one of {", ".join(STOCK_CHOICES)}.')
            continue
        return stock_name


def prompt_stock_choice(message, allow_blank=False):
    lines = [message, '']
    for index, stock_name in enumerate(STOCK_CHOICES, start=1):
        lines.append(f'[{index}] {format_stock_label(stock_name)}')
    lines.append('[0] Back')
    if allow_blank:
        lines.append('[G] Global fallback')

    print_panel('Select Stock', lines, tone='bright_blue')

    raw_value = prompt_input('Choose stock number or name: ').strip().upper()
    if raw_value in ('0', 'B', 'BACK'):
        return BACK_ACTION

    if allow_blank and raw_value in ('', 'G', 'GLOBAL'):
        return ''

    stock_name = parse_stock_choice(raw_value)
    if stock_name not in STOCK_CHOICES:
        print_error(f'Invalid stock name. Use one of {", ".join(STOCK_CHOICES)}.')
        return None

    return stock_name


def print_stock_snapshot(data, stock_name):
    info = get_stock_info(data, stock_name)
    metrics = get_stock_price_metrics(data, stock_name)

    lines = [f'Chosen stock: {format_stock_label(stock_name)}']
    if info:
        lines.append(f'Info: {info}')
    else:
        lines.append(f'Info: No saved info yet for {format_stock_label(stock_name)}.')

    if metrics:
        lines.append(f'Auto price: {format_php(metrics["unit_price"])}')
        lines.append(f'Source: {metrics["source"]}')
    else:
        lines.append('Auto price: No saved market price yet.')
        lines.append('Source: Add a market sample for this stock or use global fallback.')

    print_panel('Stock Snapshot', lines, tone='bright_green')


def create_account_record(data, stock_name, account_name, link, email, password, fbfs, notes):
    stock_name = parse_stock_choice(stock_name)
    account_name = str(account_name).strip()
    link = normalize_optional_text(link)
    email = str(email).strip()
    password = str(password).strip()
    notes = normalize_optional_text(notes)

    if stock_name not in STOCK_CHOICES:
        return None, f'Invalid stock name. Use one of {", ".join(STOCK_CHOICES)}.'

    if not account_name:
        return None, 'Account name cannot be empty.'

    if not email or not password:
        return None, 'Email and password cannot be empty.'

    try:
        fbfs_value = parse_whole_number_text(fbfs)
    except (TypeError, ValueError):
        return None, 'fbfs must be a whole number.'

    if fbfs_value < 0:
        return None, 'fbfs cannot be negative.'

    code = generate_next_account_code(data)
    return (
        code,
        {
            'code': code,
            'stock_name': stock_name,
            'name': account_name,
            'link': link,
            'email': email,
            'password': password,
            'notes': notes,
            'fbfs': fbfs_value,
            'updated_at': current_timestamp_text(),
        },
    )


def parse_row_account_line(line):
    parts = [part.strip() for part in line.split('|')]
    return parse_flexible_account_parts(parts)


def parse_multiline_account_block(lines):
    return parse_flexible_account_parts(lines)


def add_row_account(data, stock_name, row):
    code, record_or_error = create_account_record(
        data,
        stock_name,
        row['name'],
        row['link'],
        row['email'],
        row['password'],
        row['fbfs'],
        row['notes'],
    )
    if code is None:
        print_error(record_or_error)
        return None

    data['accounts'][code] = record_or_error
    metrics = get_stock_price_metrics(data, record_or_error['stock_name'])
    print_success(f'Added {code}: {record_or_error["stock_name"]} | {record_or_error["name"]}')
    if metrics:
        print_info(f'Auto price: {format_php(metrics["unit_price"])}')
    return code


def add_account(data):
    show_action_header('Add Account', 'Choose one stock, then paste one or many accounts into the batch.')
    stock_name = prompt_stock_choice('Choose stock name for the account(s):')
    if stock_name == BACK_ACTION:
        print_warning('Back to main menu.')
        return
    if stock_name is None:
        return

    print_stock_snapshot(data, stock_name)
    print_panel(
        'Paste Guide',
        [
            'You can paste accounts in mixed order. MAUS will try to detect which field is which.',
            '',
            '1) One row with | separators in any order',
            '   Example: email | password | name | fbfs | link | notes',
            '',
            '2) Multiline block, also in any order',
            '   Example lines: John Doe / john@email.com / pass123 / 1500',
            '',
            '3) Labeled fields also work',
            '   Example: name: John Doe | fbfs: 1500 | email: john@email.com',
            '',
            'Link and notes are optional.',
            'Type DONE on its own line when finished.',
        ],
        tone='bright_blue',
    )

    added_codes = []
    multiline_buffer = []

    while True:
        line = prompt_input('input> ', 'bright_green', 'bold')
        stripped = line.strip()

        if stripped.upper() == 'DONE':
            if multiline_buffer:
                row, error = parse_multiline_account_block(multiline_buffer)
                if error:
                    print_error(error)
                else:
                    code = add_row_account(data, stock_name, row)
                    if code:
                        added_codes.append(code)
            break

        if '|' in line:
            if multiline_buffer:
                print_warning('Finish the current multiline block first or type DONE.')
                continue

            row, error = parse_row_account_line(line)
            if error:
                print_error(error)
                continue

            code = add_row_account(data, stock_name, row)
            if code:
                added_codes.append(code)
            continue

        if not stripped:
            if not multiline_buffer:
                continue

            row, error = parse_multiline_account_block(multiline_buffer)
            if error:
                print_warning(
                    f'Could not detect that block yet ({len(multiline_buffer)} line(s)). '
                    'Make sure it includes name, email, password, and fbfs.'
                )
            else:
                code = add_row_account(data, stock_name, row)
                if code:
                    added_codes.append(code)
                multiline_buffer = []
            continue

        multiline_buffer.append(line)
        if len(multiline_buffer) == 6:
            row, error = parse_multiline_account_block(multiline_buffer)
            if error:
                print_error(error)
            else:
                code = add_row_account(data, stock_name, row)
                if code:
                    added_codes.append(code)
            multiline_buffer = []

    if not added_codes:
        print_warning('No accounts added.')
        return

    save_data(data)
    print_panel(
        'Batch Saved',
        [
            f'Saved {len(added_codes)} account(s).',
            f'Codes: {", ".join(added_codes)}',
        ],
        tone='bright_green',
    )


def list_accounts(data):
    show_action_header('Stored Accounts', 'Inventory view with MAUS pricing and quick account details.')
    accounts = data['accounts']
    if not accounts:
        print_warning('No accounts stored.')
        return

    lines = []
    for key in sorted(accounts.keys()):
        account = accounts[key]
        lines.extend(build_inventory_account_lines(data, account))
        lines.append('')

    if lines and not lines[-1]:
        lines.pop()

    store_summary = get_store_value_summary(data)
    print_panel('Inventory', lines, tone='bright_blue')
    print_panel(
        'Store Summary',
        [
            f'Accounts in inventory: {store_summary["inventory_count"]}',
            f'Accounts with price: {store_summary["priced_accounts"]}',
            f'Accounts without price: {store_summary["unpriced_accounts"]}',
            f'Estimated store value: {format_php(store_summary["inventory_value"])}',
        ],
        tone='bright_green',
    )


def show_account(data):
    show_action_header('Get Stock', 'Search by account code, stock name, account name, or email.')
    account = pick_account(data, 'Enter account code or name to fetch: ')
    if not account:
        return

    stock_name = account.get('stock_name', '')
    info = get_stock_info(data, stock_name)
    metrics = get_stock_price_metrics(data, stock_name)
    password = account.get('password', '')

    lines = [
        ('Identity', 'bold', 'bright_cyan'),
        format_detail_line('Code', account.get("code", "no code")),
        format_detail_line('Stock', format_stock_label(stock_name)),
        format_detail_line('Name', account.get("name") or "no name saved"),
        SECTION_BREAK,
        ('Access', 'bold', 'bright_magenta'),
        format_detail_line('Email', account.get("email")),
        format_detail_line('Link', account.get("link") or "no link saved"),
    ]
    if password:
        lines.append((format_detail_line('Password', password), 'bold', 'bright_yellow'))
    else:
        lines.append((format_detail_line('Password', 'not saved'), 'bright_black'))

    lines.extend(
        [
            SECTION_BREAK,
            ('Notes', 'bold', 'bright_cyan'),
            format_detail_line('fbfs', account.get("fbfs", 0)),
            format_detail_line('Stock info', info or "no saved info"),
            format_detail_line('Notes', account.get("notes") or "no notes"),
            SECTION_BREAK,
            ('Pricing', 'bold', 'bright_green'),
        ]
    )

    if metrics:
        lines.append((format_detail_line('Price', format_php(metrics["unit_price"])), 'bold', 'bright_green'))
        lines.append(format_detail_line('Source', metrics["source"]))
    else:
        lines.append((format_detail_line('Price', 'no market data'), 'bold', 'bright_yellow'))

    print_panel(f'Account {account.get("code", "NO-CODE")}', lines, tone='bright_green')


def edit_account(data):
    show_action_header('Edit Account', 'Update fbfs, password, notes, or other saved fields for an active account.')
    account = pick_account(data, 'Enter account code or name to edit: ')
    if not account:
        return

    current_stock_name = account.get('stock_name', '')
    current_info = get_stock_info(data, current_stock_name)
    current_metrics = get_stock_price_metrics(data, current_stock_name)

    preview_lines = [
        f'Code: {account.get("code", "no code")}',
        f'Stock: {format_stock_label(current_stock_name)}',
        f'Name: {account.get("name") or "no name saved"}',
        f'Link: {account.get("link") or "no link saved"}',
        f'Email: {account.get("email") or "no email saved"}',
        f'fbfs: {account.get("fbfs", 0)}',
        f'Notes: {account.get("notes") or "no notes"}',
        'Tip: press Enter to keep the current value. Use "-" to clear link or notes.',
    ]
    if current_info:
        preview_lines.append(f'Current stock info: {current_info}')
    if current_metrics:
        preview_lines.append(f'Current auto price: {format_php(current_metrics["unit_price"])}')
    print_panel('Edit Preview', preview_lines, tone='bright_yellow')

    updated_stock_name = prompt_edit_stock_name(current_stock_name)
    if updated_stock_name == BACK_ACTION:
        print_warning('Edit canceled.')
        return

    updated_name = prompt_edit_text('Name', account.get('name', ''))
    updated_link = prompt_edit_text('Link', account.get('link', ''), allow_clear=True)
    updated_email = prompt_edit_text('Email', account.get('email', ''))
    updated_password = prompt_edit_text('Password', account.get('password', ''))
    updated_fbfs = prompt_edit_fbfs(account.get('fbfs', 0))
    updated_notes = prompt_edit_text('Notes', account.get('notes', ''), allow_clear=True)

    changes = []
    field_updates = {
        'stock_name': updated_stock_name,
        'name': updated_name,
        'link': normalize_optional_text(updated_link),
        'email': updated_email,
        'password': updated_password,
        'fbfs': updated_fbfs,
        'notes': normalize_optional_text(updated_notes),
    }

    for field_name, updated_value in field_updates.items():
        if account.get(field_name) != updated_value:
            account[field_name] = updated_value
            changes.append(field_name)

    if not changes:
        print_warning('No changes saved.')
        return

    account['updated_at'] = current_timestamp_text()

    save_data(data)

    result_lines = [
        f'Updated {account.get("code", "no code")}.',
        f'Changed fields: {", ".join(changes)}',
        f'New fbfs: {account.get("fbfs", 0)}',
    ]

    new_metrics = get_stock_price_metrics(data, account.get('stock_name', ''))
    new_info = get_stock_info(data, account.get('stock_name', ''))
    if new_info:
        result_lines.append(f'Stock info: {new_info}')
    if new_metrics:
        result_lines.append(f'Current auto price: {format_php(new_metrics["unit_price"])}')

    print_panel('Account Updated', result_lines, tone='bright_green')


def mark_account_sold(data):
    show_action_header('Mark Account As Sold', 'Pick an active account, then log the sold price and sold date.')
    account = pick_account(data, 'Enter account code or name to mark as sold: ')
    if not account:
        return

    stock_name = account.get('stock_name', '')
    metrics = get_stock_price_metrics(data, stock_name)
    market_price_php = metrics['unit_price'] if metrics else 0.0
    pricing_source = metrics['source'] if metrics else 'no market data'

    preview_lines = [
        f'Code: {account.get("code", "no code")}',
        f'Stock: {format_stock_label(stock_name)}',
        f'Name: {account.get("name") or "no name saved"}',
        f'Email: {account.get("email")}',
        f'Current market price: {format_php(market_price_php) if market_price_php > 0 else "no market data"}',
        f'Pricing source: {pricing_source}',
    ]
    print_panel('Sale Preview', preview_lines, tone='bright_yellow')

    sold_price_php = prompt_positive_float('Sold price in PHP: ')
    if sold_price_php is None:
        return

    default_sold_at = current_timestamp_text()
    sold_at = prompt_timestamp_with_default(
        f'Sold date/time (leave blank for {default_sold_at}): ',
        default_sold_at,
    )
    sold_note = prompt_input('Sale note (optional): ').strip()

    price_difference_php = sold_price_php - market_price_php if market_price_php > 0 else 0.0
    price_difference_percent = 0.0
    if market_price_php > 0:
        price_difference_percent = (price_difference_php / market_price_php) * 100

    sold_record = dict(account)
    sold_record.update(
        {
            'sold_price_php': round(sold_price_php, 2),
            'sold_at': sold_at,
            'sold_note': sold_note,
            'market_price_php': round(market_price_php, 2) if market_price_php > 0 else 0.0,
            'price_difference_php': round(price_difference_php, 2),
            'price_difference_percent': round(price_difference_percent, 2),
            'pricing_source': pricing_source,
            'updated_at': sold_at,
        }
    )

    code = account.get('code', '')
    data.setdefault('sold_accounts', {})
    data['sold_accounts'][code] = sold_record
    del data['accounts'][code]
    save_data(data)

    result_lines = [
        f'Sold {code} for {format_php(sold_price_php)}.',
        f'Sold at: {sold_at}',
    ]
    if sold_note:
        result_lines.append(f'Sale note: {sold_note}')
    if market_price_php > 0:
        result_lines.append(f'Market price at sale: {format_php(market_price_php)}')
        result_lines.append(describe_sale_vs_market(sold_record))
    else:
        result_lines.append('Market comparison: no market data available at time of sale')

    print_panel('Sale Saved', result_lines, tone='bright_green')


def show_sold_history(data):
    show_action_header('Sold History', 'See what sold, when it sold, and how it compared to the market.')
    sold_accounts = list(data.get('sold_accounts', {}).values())
    if not sold_accounts:
        print_warning('No sold accounts saved yet.')
        return

    sold_accounts.sort(
        key=lambda account: (
            account.get('sold_at', ''),
            account.get('code', ''),
        ),
        reverse=True,
    )

    lines = []
    for account in sold_accounts:
        lines.append(
            (
                f'[{account.get("code", "no code")}]  {account.get("name") or "no name"}',
                'bold',
                'bright_cyan',
            )
        )
        lines.append(format_detail_line('Stock', format_stock_label(account.get("stock_name", "UNKNOWN"))))
        lines.append((format_detail_line('Sold', format_php(account.get("sold_price_php", 0.0))), 'bold', 'bright_green'))
        lines.append(format_detail_line('When', account.get("sold_at") or "no date"))

        comparison_text = describe_sale_vs_market(account)
        comparison_tone = ('bright_yellow',)
        if comparison_text.startswith('Above market'):
            comparison_tone = ('bright_green',)
        elif comparison_text.startswith('Below market'):
            comparison_tone = ('bright_red',)
        lines.append((comparison_text, *comparison_tone))

        if account.get('market_price_php', 0.0) > 0:
            lines.append(format_detail_line('Market', format_php(account["market_price_php"])))
        if account.get('pricing_source'):
            lines.append(format_detail_line('Source', account["pricing_source"]))
        if account.get('sold_note'):
            lines.append(format_detail_line('Note', account["sold_note"]))
        lines.append(SECTION_BREAK)

    if lines and lines[-1] == SECTION_BREAK:
        lines.pop()

    print_panel('Sold Accounts', lines, tone='bright_blue')

    sales_summary = get_sales_summary(data)
    summary_lines = [
        f'Sold count: {sales_summary["sold_count"]}',
        f'Total sold value: {format_php(sales_summary["total_sales_value"])}',
        f'Compared against market: {sales_summary["market_compared_count"]}',
    ]
    if sales_summary['market_compared_count']:
        summary_lines.append(f'Market reference total: {format_php(sales_summary["total_market_reference"])}')
        summary_lines.append(f'Total difference vs market: {format_signed_php(sales_summary["total_difference"])}')

    print_panel('Sales Summary', summary_lines, tone='bright_green')


def show_market_state(data):
    show_action_header('Market State', 'See the latest market movement and recent price condition for each stock.')

    stock_lines = []
    for stock_name in STOCK_CHOICES:
        state = get_stock_market_state(data, stock_name)
        inventory_count = count_accounts_for_stock(data, stock_name)
        sold_count = count_sold_accounts_for_stock(data, stock_name)

        if not state:
            stock_lines.append((f'[{stock_name}]  {get_stock_full_name(stock_name)}', 'bold', 'bright_cyan'))
            stock_lines.append(format_detail_line('In stock', inventory_count))
            stock_lines.append(format_detail_line('Sold', sold_count))
            stock_lines.append((format_detail_line('Price', 'no market samples yet'), 'bold', 'bright_yellow'))
            stock_lines.append(SECTION_BREAK)
            continue

        stock_lines.append((f'[{stock_name}]  {get_stock_full_name(stock_name)}', 'bold', 'bright_cyan'))
        stock_lines.append(format_detail_line('In stock', inventory_count))
        stock_lines.append(format_detail_line('Sold', sold_count))
        stock_lines.append(format_detail_line('Samples', state["sample_count"]))
        stock_lines.append(
            (
                format_detail_line(
                    'Latest',
                    f'{format_php(state["latest_unit_price"])} on {state["latest_recorded_at"] or "unknown time"}',
                ),
                'bold',
                'bright_green',
            )
        )
        if state['movement_php'] is None:
            stock_lines.append((format_detail_line('Trend', 'not enough data yet'), 'bright_black'))
        else:
            movement_tone = 'bright_yellow'
            if state["movement_php"] > 0:
                movement_tone = 'bright_green'
            elif state["movement_php"] < 0:
                movement_tone = 'bright_red'
            stock_lines.append(
                (
                    format_detail_line(
                        'Trend',
                        f'{state["direction"]} {format_signed_php(state["movement_php"])} vs previous sample',
                    ),
                    movement_tone,
                )
            )
        stock_lines.append(
            format_detail_line(
                'Weighted',
                f'{format_php(state["weighted_unit_price"])} | {format_php(state["lowest_unit_price"])} to {format_php(state["highest_unit_price"])}',
            )
        )
        if state.get('latest_note'):
            stock_lines.append(format_detail_line('Note', state["latest_note"]))
        stock_lines.append(SECTION_BREAK)

    if stock_lines and stock_lines[-1] == SECTION_BREAK:
        stock_lines.pop()

    print_panel('Per-Stock Market', stock_lines, tone='bright_blue')

    global_state = get_global_market_state(data)
    global_lines = [f'Global fallback samples: {len(data["pricing"]["samples"])}']
    if global_state:
        global_lines.append(
            f'Latest fallback price: {format_php(global_state["latest_unit_price"])} on '
            f'{global_state["latest_recorded_at"] or "unknown time"}'
        )
        if global_state['movement_php'] is None:
            global_lines.append('Trend: not enough data yet')
        else:
            global_lines.append(
                f'Trend: {global_state["direction"]} {format_signed_php(global_state["movement_php"])} vs previous sample'
            )
        global_lines.append(
            f'Weighted fallback: {format_php(global_state["weighted_unit_price"])} | '
            f'range: {format_php(global_state["lowest_unit_price"])} to {format_php(global_state["highest_unit_price"])}'
        )
    else:
        global_lines.append('No global fallback market samples yet.')

    print_panel('Global Market State', global_lines, tone='bright_yellow')


def print_sheets_setup_help(extra_message=''):
    lines = []
    if extra_message:
        lines.append(extra_message)
        lines.append('')
    lines.extend(
        [
            'Required environment variables:',
            '- MAUS_GOOGLE_SERVICE_ACCOUNT_FILE',
            '- MAUS_GOOGLE_SHEETS_SPREADSHEET_ID',
            '',
            'Install dependency first:',
            '- pip install -r requirements-sheets.txt',
            '',
            'Then share the target spreadsheet with the service account email from your JSON credentials file.',
        ]
    )
    print_panel('Google Sheets Setup', lines, tone='bright_yellow')


def push_google_sheets_backup(data):
    show_action_header('Push Local Data To Google Sheets', 'Merge this device into your shared Google Sheets backup.')

    try:
        import sheets_sync
        merged_data, summary = sheets_sync.push_data_to_sheets(data)
    except ModuleNotFoundError:
        print_sheets_setup_help('Sheets sync module is missing.')
        return
    except Exception as error:
        if error.__class__.__name__ == 'SheetsSyncConfigError':
            print_sheets_setup_help(str(error))
        elif error.__class__.__name__ == 'SpreadsheetNotFound':
            print_sheets_setup_help(
                'Spreadsheet not found. Check the spreadsheet ID/URL and make sure it is shared with the service account.'
            )
        else:
            print_error(f'Google Sheets push failed: {error}')
        return

    try:
        data.clear()
        data.update(merged_data)
        save_data(data)
    except OSError as error:
        print_panel(
            'Sheets Push Partially Complete',
            [
                f'Spreadsheet updated: {summary["spreadsheet_title"]}',
                'But this device could not save the merged local snapshot.',
                f'Local save error: {error}',
            ],
            tone='bright_yellow',
        )
        return

    print_panel(
        'Sheets Push Complete',
        [
            f'Spreadsheet: {summary["spreadsheet_title"]}',
            f'Active accounts in merged backup: {summary["active_account_count"]}',
            f'Sold accounts in merged backup: {summary["sold_account_count"]}',
            f'Deleted-account sync markers: {summary["deleted_account_count"]}',
            f'Probable duplicates merged: {summary["duplicates_merged"]}',
            f'Code collisions reassigned: {summary["code_collisions_resolved"]}',
            f'Same-code account updates merged: {summary["same_code_updates"]}',
            f'Sold state wins applied: {summary["sold_promotions"]}',
            f'Deletions applied to merged backup: {summary["deletions_applied"]}',
            f'Ambiguous duplicates kept separate: {summary["ambiguous_duplicates"]}',
            f'Market sample rows in backup: {summary["market_sample_count"]}',
            'This device was also updated with the merged result.',
        ],
        tone='bright_green',
    )


def pull_google_sheets_backup(data):
    show_action_header('Pull Data From Google Sheets', 'Merge your shared Google Sheets backup into this device.')
    print_panel(
        'Pull Merge Notice',
        [
            'This now merges Google Sheets with the current local data on this device.',
            'If the same account exists on two devices, the sync will try to merge it instead of cloning it.',
            f'A safety backup will be saved first at: {PRE_SHEETS_PULL_BACKUP_FILE}',
        ],
        tone='bright_yellow',
    )

    confirm = prompt_input('Merge Google Sheets into local data? (y/N): ', 'bright_yellow', 'bold').strip().lower()
    if confirm != 'y':
        print_warning('Sheets pull canceled.')
        return

    try:
        import sheets_sync
        pulled_data, summary = sheets_sync.pull_data_from_sheets(data)
    except ModuleNotFoundError:
        print_sheets_setup_help('Sheets sync module is missing.')
        return
    except Exception as error:
        if error.__class__.__name__ == 'SheetsSyncConfigError':
            print_sheets_setup_help(str(error))
        elif error.__class__.__name__ == 'SpreadsheetNotFound':
            print_sheets_setup_help(
                'Spreadsheet not found. Check the spreadsheet ID/URL and make sure it is shared with the service account.'
            )
        else:
            print_error(f'Google Sheets pull failed: {error}')
        return

    try:
        if os.path.exists(DATA_FILE):
            save_data_to_path(data, PRE_SHEETS_PULL_BACKUP_FILE)
        data.clear()
        data.update(pulled_data)
        save_data(data)
    except OSError as error:
        print_error(f'Could not save pulled data locally: {error}')
        return

    store_summary = get_store_value_summary(data)
    sales_summary = get_sales_summary(data)
    print_panel(
        'Sheets Pull Complete',
        [
            f'Spreadsheet: {summary["spreadsheet_title"]}',
            f'Active accounts after merge: {store_summary["inventory_count"]}',
            f'Sold accounts after merge: {sales_summary["sold_count"]}',
            f'Deleted-account sync markers: {summary["deleted_account_count"]}',
            f'Probable duplicates merged: {summary["duplicates_merged"]}',
            f'Code collisions reassigned: {summary["code_collisions_resolved"]}',
            f'Same-code account updates merged: {summary["same_code_updates"]}',
            f'Sold state wins applied: {summary["sold_promotions"]}',
            f'Deletions applied during merge: {summary["deletions_applied"]}',
            f'Ambiguous duplicates kept separate: {summary["ambiguous_duplicates"]}',
            f'Market sample rows after merge: {summary["market_sample_count"]}',
            f'Safety backup saved at: {PRE_SHEETS_PULL_BACKUP_FILE}',
        ],
        tone='bright_green',
    )


def delete_account(data):
    show_action_header('Delete Account', 'Search the account first, then confirm before removing it.')
    account = pick_account(data, 'Enter account code or name to delete: ')
    if not account:
        return

    code = account.get('code', '')
    stock_name = account.get('stock_name', 'UNKNOWN')
    name = account.get('name') or 'no name'

    print_panel(
        'Delete Preview',
        [
            f'Code: {code}',
            f'Stock: {format_stock_label(stock_name)}',
            f'Name: {name}',
        ],
        tone='bright_yellow',
    )

    confirm = prompt_input(
        f'Confirm delete {code} ({format_stock_label(stock_name)})? (y/N): ',
        'bright_yellow',
        'bold',
    ).strip().lower()
    if confirm == 'y':
        remember_deleted_account(data, account)
        del data['accounts'][code]
        save_data(data)
        print_success('Deleted.')
    else:
        print_warning('Delete canceled.')


def add_market_sample(data):
    show_action_header('Add Market Price Sample', 'Feed a market listing so MAUS can auto-price your stored stock.')
    stock_name = prompt_stock_choice(
        'Choose stock name for this market listing:',
        allow_blank=True,
    )
    if stock_name == BACK_ACTION:
        print_warning('Back to main menu.')
        return
    if stock_name is None:
        return

    total_price_php = prompt_positive_float('Observed market price in PHP: ')
    if total_price_php is None:
        return

    account_count = prompt_positive_int('How many accounts were included in that listing? ')
    if account_count is None:
        return

    note = prompt_input('Note/source (optional): ').strip()
    default_recorded_at = current_timestamp_text()
    recorded_at = prompt_timestamp_with_default(
        f'Observed date/time (leave blank for {default_recorded_at}): ',
        default_recorded_at,
    )
    sample = {
        'total_price_php': total_price_php,
        'account_count': account_count,
        'note': note,
        'recorded_at': recorded_at,
    }

    unit_price = total_price_php / account_count
    if stock_name:
        data['stock_profiles'][stock_name]['samples'].append(sample)
        save_data(data)

        metrics = get_stock_price_metrics(data, stock_name)
        lines = [
            f'Added {stock_name} market sample.',
            f'Listing price: {format_php(total_price_php)}',
            f'Accounts in listing: {account_count}',
            f'Unit price: {format_php(unit_price)}',
            f'Observed at: {recorded_at}',
        ]
        if metrics:
            lines.append(f'Updated auto price: {format_php(metrics["unit_price"])}')
            lines.append(f'Estimated {stock_name} inventory value: {format_php(metrics["inventory_value"])}')
        print_panel('Sample Saved', lines, tone='bright_green')
    else:
        data['pricing']['samples'].append(sample)
        save_data(data)

        metrics = get_global_price_metrics(data)
        lines = [
            'Added global market sample.',
            f'Listing price: {format_php(total_price_php)}',
            f'Accounts in listing: {account_count}',
            f'Fallback unit price: {format_php(unit_price)}',
            f'Observed at: {recorded_at}',
        ]
        if metrics:
            lines.append(f'Updated global fallback price: {format_php(metrics["unit_price"])}')
        print_panel('Global Sample Saved', lines, tone='bright_green')


def set_stock_info(data):
    show_action_header('Set Stock Info', 'Save a note or description for one stock choice.')
    stock_name = prompt_stock_choice('Choose a stock name to configure:')
    if stock_name == BACK_ACTION:
        print_warning('Back to main menu.')
        return
    if stock_name is None:
        return

    current_info = get_stock_info(data, stock_name)
    if current_info:
        print_info(f'Current info for {stock_name}: {current_info}')
    else:
        print_warning(f'No info saved yet for {stock_name}.')

    info = prompt_input(f'Info/description for {stock_name} (leave blank to clear): ').strip()
    data['stock_profiles'][stock_name]['info'] = info
    save_data(data)

    if info:
        print_success(f'Saved info for {stock_name}.')
    else:
        print_warning(f'Cleared info for {stock_name}.')

    metrics = get_stock_price_metrics(data, stock_name)
    if metrics:
        print_info(f'Current auto price for {stock_name}: {format_php(metrics["unit_price"])}')


def show_pricing_summary(data):
    show_action_header('Pricing Summary', 'Review stock-by-stock price data, fallback pricing, and total store value.')

    stock_lines = []
    for stock_name in STOCK_CHOICES:
        info = get_stock_info(data, stock_name) or 'no saved info'
        profile_samples = data['stock_profiles'][stock_name]['samples']
        metrics = get_stock_price_metrics(data, stock_name)
        inventory_count = count_accounts_for_stock(data, stock_name)
        sold_count = count_sold_accounts_for_stock(data, stock_name)

        stock_lines.append(f'{stock_name} | stored {inventory_count} | sold {sold_count} | samples {len(profile_samples)}')
        stock_lines.append(f'  info: {info}')

        if metrics:
            stock_lines.append(f'  auto price: {format_php(metrics["unit_price"])}')
            stock_lines.append(f'  source: {metrics["source"]}')
            stock_lines.append(f'  estimated stock value: {format_php(metrics["inventory_value"])}')
        else:
            stock_lines.append('  auto price: no market data')

        stock_lines.append('')

    if stock_lines and not stock_lines[-1]:
        stock_lines.pop()

    print_panel('Stock Pricing', stock_lines, tone='bright_blue')

    global_metrics = get_global_price_metrics(data)
    global_lines = [f'Global market samples: {len(data["pricing"]["samples"])}']
    if global_metrics:
        global_lines.append(f'Fallback unit price: {format_php(global_metrics["unit_price"])}')
    else:
        global_lines.append('Fallback unit price: no global market data')

    print_panel('Global Fallback', global_lines, tone='bright_yellow')

    store_summary = get_store_value_summary(data)
    print_panel(
        'Store Totals',
        [
            f'Accounts in inventory: {store_summary["inventory_count"]}',
            f'Accounts with price: {store_summary["priced_accounts"]}',
            f'Accounts without price: {store_summary["unpriced_accounts"]}',
            f'Estimated store value: {format_php(store_summary["inventory_value"])}',
        ],
        tone='bright_green',
    )


def main():
    data = load_data()

    while True:
        show_main_menu(data)
        choice = prompt_input('Select an action: ').strip()
        clear_screen()

        if choice == '1':
            add_account(data)
            pause_for_continue()
        elif choice == '2':
            list_accounts(data)
            pause_for_continue()
        elif choice == '3':
            show_account(data)
            pause_for_continue()
        elif choice == '4':
            manage_account_menu(data)
            pause_for_continue()
        elif choice == '5':
            show_sold_history(data)
            pause_for_continue()
        elif choice == '6':
            add_market_sample(data)
            pause_for_continue()
        elif choice == '7':
            show_market_state(data)
            pause_for_continue()
        elif choice == '8':
            show_pricing_summary(data)
            pause_for_continue()
        elif choice == '9':
            push_google_sheets_backup(data)
            pause_for_continue()
        elif choice == '10':
            pull_google_sheets_backup(data)
            pause_for_continue()
        elif choice == '11':
            print_panel('Exit', ['MAUS console closed.'], tone='bright_cyan')
            break
        else:
            print_error('Invalid choice.')
            pause_for_continue()


if __name__ == '__main__':
    main()
