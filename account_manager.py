#!/usr/bin/env python3
"""Termux account storage CLI with a phone-friendly MAUS interface."""

import json
import os
import shutil
import sys
import textwrap

DATA_FILE = os.path.expanduser('~/.termux_accounts.json')
STOCK_CHOICES = ('RA', 'PR', 'ON', 'MN', 'RP')
ACCOUNT_CODE_PREFIX = 'ACC-'
ACCOUNT_CODE_DIGITS = 4
APP_TITLE = 'MAUS ACCOUNT TRACKER'
APP_SUBTITLE = 'Phone-ready stock console'
APP_OWNER = 'Owner codename: MAUS'
MENU_OPTIONS = (
    ('1', 'Paste/add account(s)', 'Bulk add one stock batch at a time'),
    ('2', 'List accounts', 'See every stored account and store value'),
    ('3', 'View/fetch account', 'Open full details by code or name'),
    ('4', 'Delete account', 'Remove a stock entry safely'),
    ('5', 'Add market price sample', 'Feed auto-pricing with market data'),
    ('6', 'Set stock info', 'Save notes for RA, PR, ON, MN, or RP'),
    ('7', 'View pricing summary', 'Review prices, samples, and totals'),
    ('8', 'Exit', 'Close the MAUS console'),
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


def print_panel(title, lines, tone='bright_blue'):
    width = terminal_width()
    border = '+' + ('-' * (width - 2)) + '+'
    inner_width = width - 4
    title_text = f' {title[:inner_width]} '

    print(style(border, tone))
    print(style(f'| {title_text.ljust(inner_width)} |', 'bold', tone))
    print(style(border, tone))

    for raw_line in lines:
        for segment in wrap_text(raw_line, inner_width):
            print(f'| {segment.ljust(inner_width)} |')

    print(style(border, tone))


def pause_for_continue():
    prompt_input('\nPress Enter to return to the MAUS dashboard... ', 'bright_black')


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
    return choice_map.get(normalized, normalized)


def normalize_optional_text(value):
    cleaned = str(value).strip()
    if cleaned.upper() in ('-', 'NONE', 'N/A'):
        return ''
    return cleaned


def normalize_non_negative_int(value, default=0):
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized >= 0 else default


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
        stock_name = str(info.get('stock_name', '')).strip().upper()
        if not stock_name:
            stock_name = str(info.get('tag', '')).strip().upper()
        if not stock_name and raw_key and not looks_like_account_code(raw_key):
            stock_name = raw_key.upper()

        record = {
            'code': str(info.get('code', '')).strip().upper(),
            'stock_name': stock_name,
            'name': str(info.get('name', '')).strip(),
            'link': normalize_optional_text(info.get('link', '')),
            'email': str(info.get('email', '')).strip(),
            'password': str(info.get('password', '')).strip(),
            'legacy_password_hash': str(
                info.get('legacy_password_hash') or info.get('password_hash', '')
            ).strip(),
            'notes': normalize_optional_text(info.get('notes', '')),
            'fbfs': normalize_non_negative_int(info.get('fbfs', 0)),
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
            }
        )

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


def normalize_data(raw_data):
    database = default_database()
    if not isinstance(raw_data, dict):
        return database

    if 'accounts' in raw_data or 'pricing' in raw_data or 'stock_profiles' in raw_data or 'tag_profiles' in raw_data:
        database['accounts'] = normalize_accounts(raw_data.get('accounts', {}))

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

    with open(DATA_FILE, 'r', encoding='utf-8') as file_handle:
        try:
            raw_data = json.load(file_handle)
        except json.JSONDecodeError:
            return default_database()

    return normalize_data(raw_data)


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)


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


def generate_next_account_code(data):
    return generate_unique_account_code(set(data['accounts'].keys()))


def format_account_brief(data, account):
    stock_name = account.get('stock_name', '')
    metrics = get_stock_price_metrics(data, stock_name)

    parts = [
        account.get('code', 'NO-CODE'),
        stock_name or 'UNKNOWN',
    ]
    if account.get('name'):
        parts.append(account['name'])
    parts.append(f'fbfs: {account.get("fbfs", 0)}')
    if metrics:
        parts.append(format_php(metrics['unit_price']))

    return ' | '.join(parts)


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


def build_stock_overview_line(data):
    segments = []
    for stock_name in STOCK_CHOICES:
        inventory_count = count_accounts_for_stock(data, stock_name)
        metrics = get_stock_price_metrics(data, stock_name)
        price_text = format_php(metrics['unit_price']) if metrics else 'no price'
        segments.append(f'{stock_name} {inventory_count} @ {price_text}')
    return ' | '.join(segments)


def show_dashboard(data):
    store_summary = get_store_value_summary(data)
    lines = [
        APP_OWNER,
        APP_SUBTITLE,
        '',
        f'Inventory: {store_summary["inventory_count"]} account(s)',
        f'Priced: {store_summary["priced_accounts"]} | Unpriced: {store_summary["unpriced_accounts"]}',
        f'Estimated store value: {format_php(store_summary["inventory_value"])}',
        '',
        'Stock overview:',
        build_stock_overview_line(data),
    ]
    print_panel(APP_TITLE, lines, tone='bright_cyan')


def show_main_menu(data):
    clear_screen()
    show_dashboard(data)

    menu_lines = []
    for key, label, description in MENU_OPTIONS:
        menu_lines.append(f'[{key}] {label}')
        menu_lines.append(f'    {description}')
        if key != MENU_OPTIONS[-1][0]:
            menu_lines.append('')

    print_panel('Main Menu', menu_lines, tone='bright_blue')


def show_action_header(title, detail=''):
    lines = [detail] if detail else ['']
    print_panel(title, lines, tone='bright_magenta')


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
        value = int(raw_value)
    except ValueError:
        print_error('Please enter a whole number.')
        return None

    if value <= 0:
        print_error('Value must be greater than zero.')
        return None

    return value


def prompt_stock_choice(message, allow_blank=False):
    lines = [message, '']
    for index, stock_name in enumerate(STOCK_CHOICES, start=1):
        lines.append(f'[{index}] {stock_name}')
    if allow_blank:
        lines.append('[0] Global fallback')

    print_panel('Select Stock', lines, tone='bright_blue')

    raw_value = prompt_input('Choose stock number or name: ').strip().upper()
    if allow_blank and raw_value in ('', '0'):
        return ''

    stock_name = parse_stock_choice(raw_value)
    if stock_name not in STOCK_CHOICES:
        print_error(f'Invalid stock name. Use one of {", ".join(STOCK_CHOICES)}.')
        return None

    return stock_name


def print_stock_snapshot(data, stock_name):
    info = get_stock_info(data, stock_name)
    metrics = get_stock_price_metrics(data, stock_name)

    lines = [f'Chosen stock: {stock_name}']
    if info:
        lines.append(f'Info: {info}')
    else:
        lines.append(f'Info: No saved info yet for {stock_name}.')

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
        fbfs_value = int(fbfs)
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
            'legacy_password_hash': '',
            'notes': notes,
            'fbfs': fbfs_value,
        },
    )


def parse_row_account_line(line):
    parts = [part.strip() for part in line.split('|')]
    if len(parts) != 6:
        return None, 'Use 6 fields: name | link | email | password | fbfs | notes'

    return {
        'name': parts[0],
        'link': parts[1],
        'email': parts[2],
        'password': parts[3],
        'fbfs': parts[4],
        'notes': parts[5],
    }, None


def parse_multiline_account_block(lines):
    if len(lines) != 6:
        return None, 'A multiline account block needs exactly 6 lines.'

    return {
        'name': lines[0].strip(),
        'link': lines[1].strip(),
        'email': lines[2].strip(),
        'password': lines[3].strip(),
        'fbfs': lines[4].strip(),
        'notes': lines[5].strip(),
    }, None


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
    show_action_header('Paste/Add Account(s)', 'Choose one stock, then paste one or many accounts into the batch.')
    stock_name = prompt_stock_choice('Choose stock name for the account(s):')
    if stock_name is None:
        return

    print_stock_snapshot(data, stock_name)
    print_panel(
        'Paste Guide',
        [
            'You can paste accounts in either format.',
            '',
            '1) One row: name | link | email | password | fbfs | notes',
            '2) Six lines in this order:',
            '   name',
            '   link',
            '   email',
            '   password',
            '   fbfs',
            '   notes',
            '',
            'Use "-" for blank link or blank notes in multiline mode.',
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
                if len(multiline_buffer) == 6:
                    row, error = parse_multiline_account_block(multiline_buffer)
                    if error:
                        print_error(error)
                    else:
                        code = add_row_account(data, stock_name, row)
                        if code:
                            added_codes.append(code)
                else:
                    print_warning(
                        f'Ignored incomplete multiline block with {len(multiline_buffer)} line(s). '
                        'Each account needs 6 lines.'
                    )
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

            if len(multiline_buffer) == 6:
                row, error = parse_multiline_account_block(multiline_buffer)
                if error:
                    print_error(error)
                else:
                    code = add_row_account(data, stock_name, row)
                    if code:
                        added_codes.append(code)
                multiline_buffer = []
            else:
                print_warning(
                    f'Current multiline block has {len(multiline_buffer)} line(s). '
                    'Each account needs 6 lines.'
                )
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
        stock_name = account.get('stock_name', '')
        info = get_stock_info(data, stock_name)
        metrics = get_stock_price_metrics(data, stock_name)

        line = f'- {account.get("code", key)} | {stock_name or "UNKNOWN"}'
        if account.get('name'):
            line += f' | name: {account["name"]}'
        if info:
            line += f' | {info}'
        line += f' | fbfs: {account.get("fbfs", 0)}'
        if metrics:
            line += f' -> {format_php(metrics["unit_price"])}'
        else:
            line += ' -> no price yet'
        lines.append(line)

        detail_parts = []
        if info:
            detail_parts.append(f'info: {info}')
        if account.get('email'):
            detail_parts.append(f'email: {account["email"]}')
        if detail_parts:
            lines.append('  ' + ' | '.join(detail_parts))
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
    show_action_header('View/Fetch Account', 'Search by account code, stock name, account name, or email.')
    account = pick_account(data, 'Enter account code or name to fetch: ')
    if not account:
        return

    stock_name = account.get('stock_name', '')
    info = get_stock_info(data, stock_name)
    metrics = get_stock_price_metrics(data, stock_name)
    password = account.get('password', '')
    legacy_password_hash = account.get('legacy_password_hash', '')

    lines = [
        f'Code: {account.get("code", "no code")}',
        f'Stock: {stock_name or "UNKNOWN"}',
        f'Name: {account.get("name") or "no name saved"}',
        f'Link: {account.get("link") or "no link saved"}',
        f'Email: {account.get("email")}',
        f'Stock info: {info or "no saved info"}',
        f'fbfs: {account.get("fbfs", 0)}',
        f'Notes: {account.get("notes") or "no notes"}',
    ]
    if password:
        lines.append(f'Password: {password}')
    elif legacy_password_hash:
        lines.append(f'Legacy password hash: {legacy_password_hash}')
        lines.append('Password: old record still only has the previous hash')
    else:
        lines.append('Password: not saved')

    if metrics:
        lines.append(f'Estimated price: {format_php(metrics["unit_price"])}')
        lines.append(f'Pricing source: {metrics["source"]}')
    else:
        lines.append('Estimated price: no market data')

    print_panel(f'Account {account.get("code", "NO-CODE")}', lines, tone='bright_green')


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
            f'Stock: {stock_name}',
            f'Name: {name}',
        ],
        tone='bright_yellow',
    )

    confirm = prompt_input(f'Confirm delete {code} ({stock_name})? (y/N): ', 'bright_yellow', 'bold').strip().lower()
    if confirm == 'y':
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
    if stock_name is None:
        return

    total_price_php = prompt_positive_float('Observed market price in PHP: ')
    if total_price_php is None:
        return

    account_count = prompt_positive_int('How many accounts were included in that listing? ')
    if account_count is None:
        return

    note = prompt_input('Note/source (optional): ').strip()
    sample = {
        'total_price_php': total_price_php,
        'account_count': account_count,
        'note': note,
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
        ]
        if metrics:
            lines.append(f'Updated global fallback price: {format_php(metrics["unit_price"])}')
        print_panel('Global Sample Saved', lines, tone='bright_green')


def set_stock_info(data):
    show_action_header('Set Stock Info', 'Save a note or description for one stock choice.')
    stock_name = prompt_stock_choice('Choose a stock name to configure:')
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

        stock_lines.append(f'{stock_name} | stored {inventory_count} | samples {len(profile_samples)}')
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
            delete_account(data)
            pause_for_continue()
        elif choice == '5':
            add_market_sample(data)
            pause_for_continue()
        elif choice == '6':
            set_stock_info(data)
            pause_for_continue()
        elif choice == '7':
            show_pricing_summary(data)
            pause_for_continue()
        elif choice == '8':
            print_panel('Exit', ['MAUS console closed.'], tone='bright_cyan')
            break
        else:
            print_error('Invalid choice.')
            pause_for_continue()


if __name__ == '__main__':
    main()
