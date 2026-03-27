#!/usr/bin/env python3
"""Termux account storage CLI with stock-based pricing."""

import json
import os

DATA_FILE = os.path.expanduser('~/.termux_accounts.json')
STOCK_CHOICES = ('RA', 'PR', 'ON', 'MN', 'RP')
ACCOUNT_CODE_PREFIX = 'ACC-'
ACCOUNT_CODE_DIGITS = 4


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
    query = input(prompt_message).strip()
    matches = search_accounts(data, query)
    if not matches:
        print(empty_message)
        return None

    if len(matches) == 1:
        return matches[0]

    print('\nMultiple matches found:')
    for account in matches:
        print(f'- {format_account_brief(data, account)}')

    matching_codes = {account.get('code', '') for account in matches}
    chosen_code = input('Enter the account code to continue: ').strip().upper()
    if chosen_code not in matching_codes:
        print('Invalid code.')
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


def prompt_positive_float(message):
    raw_value = input(message).strip()
    try:
        value = parse_price_text(raw_value)
    except ValueError:
        print('Please enter a valid price, for example 54, 54php, PHP 54, or 1,250.')
        return None

    if value <= 0:
        print('Value must be greater than zero.')
        return None

    return round(value, 2)


def prompt_positive_int(message):
    raw_value = input(message).strip()
    try:
        value = int(raw_value)
    except ValueError:
        print('Please enter a whole number.')
        return None

    if value <= 0:
        print('Value must be greater than zero.')
        return None

    return value


def prompt_stock_choice(message, allow_blank=False):
    print(message)
    for index, stock_name in enumerate(STOCK_CHOICES, start=1):
        print(f'{index}) {stock_name}')
    if allow_blank:
        print('0) Global fallback')

    raw_value = input('Choose stock number or name: ').strip().upper()
    if allow_blank and raw_value in ('', '0'):
        return ''

    stock_name = parse_stock_choice(raw_value)
    if stock_name not in STOCK_CHOICES:
        print(f'Invalid stock name. Use one of {", ".join(STOCK_CHOICES)}.')
        return None

    return stock_name


def print_stock_snapshot(data, stock_name):
    info = get_stock_info(data, stock_name)
    metrics = get_stock_price_metrics(data, stock_name)

    print(f'Stock chosen: {stock_name}')
    if info:
        print(f'Stock info: {info}')
    else:
        print(f'No saved info yet for {stock_name}. Use "Set stock info" to store details.')

    if metrics:
        print(f'Auto price for {stock_name}: {format_php(metrics["unit_price"])} ({metrics["source"]})')
    else:
        print(f'No saved market price yet for {stock_name}. Add a market sample for this stock.')


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
        print(record_or_error)
        return None

    data['accounts'][code] = record_or_error
    metrics = get_stock_price_metrics(data, record_or_error['stock_name'])
    print(f'Added {code}: {record_or_error["stock_name"]} | {record_or_error["name"]}')
    if metrics:
        print(f'  auto price: {format_php(metrics["unit_price"])}')
    return code


def add_account(data):
    stock_name = prompt_stock_choice('Choose stock name for the account(s):')
    if stock_name is None:
        return

    print_stock_snapshot(data, stock_name)
    print('\nYou can paste accounts in either format:')
    print('1) One row: name | link | email | password | fbfs | notes')
    print('2) Six lines in this order:')
    print('   name')
    print('   link')
    print('   email')
    print('   password')
    print('   fbfs')
    print('   notes')
    print('Use "-" for blank link or blank notes in multiline mode.')
    print('Type DONE on its own line when finished.')

    added_codes = []
    multiline_buffer = []

    while True:
        line = input('input> ')
        stripped = line.strip()

        if stripped.upper() == 'DONE':
            if multiline_buffer:
                if len(multiline_buffer) == 6:
                    row, error = parse_multiline_account_block(multiline_buffer)
                    if error:
                        print(error)
                    else:
                        code = add_row_account(data, stock_name, row)
                        if code:
                            added_codes.append(code)
                else:
                    print(
                        f'Ignored incomplete multiline block with {len(multiline_buffer)} line(s). '
                        'Each account needs 6 lines.'
                    )
            break

        if '|' in line:
            if multiline_buffer:
                print('Finish the current multiline block first or type DONE.')
                continue

            row, error = parse_row_account_line(line)
            if error:
                print(error)
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
                    print(error)
                else:
                    code = add_row_account(data, stock_name, row)
                    if code:
                        added_codes.append(code)
                multiline_buffer = []
            else:
                print(
                    f'Current multiline block has {len(multiline_buffer)} line(s). '
                    'Each account needs 6 lines.'
                )
            continue

        multiline_buffer.append(line)
        if len(multiline_buffer) == 6:
            row, error = parse_multiline_account_block(multiline_buffer)
            if error:
                print(error)
            else:
                code = add_row_account(data, stock_name, row)
                if code:
                    added_codes.append(code)
            multiline_buffer = []

    if not added_codes:
        print('No accounts added.')
        return

    save_data(data)
    print(f'Saved {len(added_codes)} account(s).')


def list_accounts(data):
    accounts = data['accounts']
    if not accounts:
        print('No accounts stored.')
        return

    print('\nStored accounts:')
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
        print(line)

    store_summary = get_store_value_summary(data)
    print('\nStore summary:')
    print(f'- Accounts in inventory: {store_summary["inventory_count"]}')
    print(f'- Accounts with price: {store_summary["priced_accounts"]}')
    print(f'- Accounts without price: {store_summary["unpriced_accounts"]}')
    print(f'- Estimated store value: {format_php(store_summary["inventory_value"])}')


def show_account(data):
    account = pick_account(data, 'Enter account code or name to fetch: ')
    if not account:
        return

    stock_name = account.get('stock_name', '')
    info = get_stock_info(data, stock_name)
    metrics = get_stock_price_metrics(data, stock_name)
    password = account.get('password', '')
    legacy_password_hash = account.get('legacy_password_hash', '')

    print(
        f"\n{stock_name or 'UNKNOWN'}:"
        f"\n  code: {account.get('code', 'no code')}"
        f"\n  name: {account.get('name') or 'no name saved'}"
        f"\n  link: {account.get('link') or 'no link saved'}"
        f"\n  email: {account.get('email')}"
        f"\n  stock_info: {info or 'no saved info'}"
        f"\n  fbfs: {account.get('fbfs', 0)}"
        f"\n  notes: {account.get('notes')}"
    )
    if password:
        print(f'  password: {password}')
    elif legacy_password_hash:
        print(f'  legacy_password_hash: {legacy_password_hash}')
        print('  password: old record still only has the previous hash')
    else:
        print('  password: not saved')

    if metrics:
        print(f'  estimated_price_php: {format_php(metrics["unit_price"])}')
        print(f'  pricing_source: {metrics["source"]}')
    else:
        print('  estimated_price_php: no market data')


def delete_account(data):
    account = pick_account(data, 'Enter account code or name to delete: ')
    if not account:
        return

    code = account.get('code', '')
    stock_name = account.get('stock_name', 'UNKNOWN')
    confirm = input(f'Confirm delete {code} ({stock_name})? (y/N): ').strip().lower()
    if confirm == 'y':
        del data['accounts'][code]
        save_data(data)
        print('Deleted.')
    else:
        print('Delete canceled.')


def add_market_sample(data):
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

    note = input('Note/source (optional): ').strip()
    sample = {
        'total_price_php': total_price_php,
        'account_count': account_count,
        'note': note,
    }

    if stock_name:
        data['stock_profiles'][stock_name]['samples'].append(sample)
        save_data(data)

        unit_price = total_price_php / account_count
        print(
            f'Added {stock_name} market sample: {format_php(total_price_php)} for '
            f'{account_count} account(s) -> {format_php(unit_price)} each'
        )

        metrics = get_stock_price_metrics(data, stock_name)
        if metrics:
            print(f'Updated auto price for {stock_name}: {format_php(metrics["unit_price"])}')
            print(f'Estimated {stock_name} inventory value: {format_php(metrics["inventory_value"])}')
    else:
        data['pricing']['samples'].append(sample)
        save_data(data)

        unit_price = total_price_php / account_count
        print(
            f'Added global market sample: {format_php(total_price_php)} for '
            f'{account_count} account(s) -> {format_php(unit_price)} each'
        )

        metrics = get_global_price_metrics(data)
        if metrics:
            print(f'Updated global fallback price: {format_php(metrics["unit_price"])}')


def set_stock_info(data):
    stock_name = prompt_stock_choice('Choose a stock name to configure:')
    if stock_name is None:
        return

    current_info = get_stock_info(data, stock_name)
    if current_info:
        print(f'Current info for {stock_name}: {current_info}')
    else:
        print(f'No info saved yet for {stock_name}.')

    info = input(f'Info/description for {stock_name} (leave blank to clear): ').strip()
    data['stock_profiles'][stock_name]['info'] = info
    save_data(data)

    if info:
        print(f'Saved info for {stock_name}.')
    else:
        print(f'Cleared info for {stock_name}.')

    metrics = get_stock_price_metrics(data, stock_name)
    if metrics:
        print(f'Current auto price for {stock_name}: {format_php(metrics["unit_price"])}')


def show_pricing_summary(data):
    print('\nStock pricing summary:')
    for stock_name in STOCK_CHOICES:
        info = get_stock_info(data, stock_name) or 'no saved info'
        profile_samples = data['stock_profiles'][stock_name]['samples']
        metrics = get_stock_price_metrics(data, stock_name)
        inventory_count = count_accounts_for_stock(data, stock_name)

        print(f'- {stock_name}: {info}')
        print(f'  stored accounts: {inventory_count}')
        print(f'  stock-specific market samples: {len(profile_samples)}')

        if metrics:
            print(f'  auto price: {format_php(metrics["unit_price"])}')
            print(f'  pricing source: {metrics["source"]}')
            print(f'  estimated stock inventory value: {format_php(metrics["inventory_value"])}')
        else:
            print('  auto price: no market data')

    global_metrics = get_global_price_metrics(data)
    print('\nGlobal fallback pricing:')
    print(f'- global market samples: {len(data["pricing"]["samples"])}')
    if global_metrics:
        print(f'- fallback unit price: {format_php(global_metrics["unit_price"])}')
    else:
        print('- fallback unit price: no global market data')

    store_summary = get_store_value_summary(data)
    print('\nStore totals:')
    print(f'- Accounts in inventory: {store_summary["inventory_count"]}')
    print(f'- Accounts with price: {store_summary["priced_accounts"]}')
    print(f'- Accounts without price: {store_summary["unpriced_accounts"]}')
    print(f'- Estimated store value: {format_php(store_summary["inventory_value"])}')


def main():
    data = load_data()

    while True:
        print('\nChoose an action:')
        print('1) Paste/add account(s)')
        print('2) List accounts')
        print('3) View/fetch account')
        print('4) Delete account')
        print('5) Add market price sample')
        print('6) Set stock info')
        print('7) View pricing summary')
        print('8) Exit')
        choice = input('> ').strip()

        if choice == '1':
            add_account(data)
        elif choice == '2':
            list_accounts(data)
        elif choice == '3':
            show_account(data)
        elif choice == '4':
            delete_account(data)
        elif choice == '5':
            add_market_sample(data)
        elif choice == '6':
            set_stock_info(data)
        elif choice == '7':
            show_pricing_summary(data)
        elif choice == '8':
            print('Bye')
            break
        else:
            print('Invalid choice')


if __name__ == '__main__':
    main()
