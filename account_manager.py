#!/usr/bin/env python3
"""Termux account storage CLI with tag-based pricing."""

import getpass
import json
import os

DATA_FILE = os.path.expanduser('~/.termux_accounts.json')
VALID_TAGS = ('RA', 'RP', 'MX', 'ON')
ACCOUNT_CODE_PREFIX = 'ACC-'
ACCOUNT_CODE_DIGITS = 4


def default_tag_profiles():
    return {
        tag: {
            'info': '',
            'samples': [],
        }
        for tag in VALID_TAGS
    }


def default_database():
    return {
        'accounts': {},
        'pricing': {
            'samples': [],
        },
        'tag_profiles': default_tag_profiles(),
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


def normalize_accounts(accounts):
    if not isinstance(accounts, dict):
        return {}

    normalized = {}
    used_codes = set()
    pending_records = []

    for name, info in accounts.items():
        if not isinstance(info, dict):
            continue

        raw_key = str(name).strip()
        password = str(info.get('password', '')).strip()
        legacy_password_hash = str(
            info.get('legacy_password_hash') or info.get('password_hash', '')
        ).strip()
        fbfs = info.get('fbfs', 0)
        try:
            fbfs = int(fbfs)
        except (TypeError, ValueError):
            fbfs = 0
        if fbfs < 0:
            fbfs = 0

        stock_name = str(info.get('stock_name', '')).strip()
        if not stock_name and raw_key and not looks_like_account_code(raw_key):
            stock_name = raw_key

        record = {
            'code': str(info.get('code', '')).strip().upper(),
            'stock_name': stock_name,
            'name': str(info.get('name', '')).strip(),
            'link': str(info.get('link', '')).strip(),
            'email': str(info.get('email', '')).strip(),
            'password': password,
            'legacy_password_hash': legacy_password_hash,
            'tag': str(info.get('tag', '')).upper().strip(),
            'notes': str(info.get('notes', '')).strip(),
            'fbfs': fbfs,
        }

        if not record['code'] and looks_like_account_code(raw_key):
            record['code'] = raw_key.upper()

        if record['code'] and looks_like_account_code(record['code']) and record['code'] not in used_codes:
            used_codes.add(record['code'])
            if not record['stock_name']:
                record['stock_name'] = record['name'] or record['code']
            normalized[record['code']] = record
        else:
            pending_records.append(record)

    for record in pending_records:
        code = generate_unique_account_code(used_codes)
        record['code'] = code
        if not record['stock_name']:
            record['stock_name'] = record['name'] or code
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


def normalize_tag_profiles(raw_profiles):
    profiles = default_tag_profiles()
    if not isinstance(raw_profiles, dict):
        return profiles

    for tag in VALID_TAGS:
        raw_profile = raw_profiles.get(tag, {})
        if not isinstance(raw_profile, dict):
            continue

        profiles[tag] = {
            'info': str(raw_profile.get('info', '')).strip(),
            'samples': normalize_samples(raw_profile.get('samples', [])),
        }

    return profiles


def normalize_data(raw_data):
    database = default_database()
    if not isinstance(raw_data, dict):
        return database

    if 'accounts' in raw_data or 'pricing' in raw_data or 'tag_profiles' in raw_data:
        database['accounts'] = normalize_accounts(raw_data.get('accounts', {}))

        pricing = raw_data.get('pricing', {})
        if isinstance(pricing, dict):
            database['pricing']['samples'] = normalize_samples(pricing.get('samples', []))

        database['tag_profiles'] = normalize_tag_profiles(raw_data.get('tag_profiles', {}))
        return database

    # Backward compatibility for the original flat account-only JSON format.
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


def count_accounts_for_tag(data, tag):
    return sum(1 for account in data['accounts'].values() if account.get('tag') == tag)


def get_global_price_metrics(data, inventory_count=None):
    if inventory_count is None:
        inventory_count = len(data['accounts'])

    metrics = build_price_metrics(data['pricing']['samples'], inventory_count)
    if metrics:
        metrics['source'] = 'global market samples'
    return metrics


def get_tag_price_metrics(data, tag):
    inventory_count = count_accounts_for_tag(data, tag)
    profile = data['tag_profiles'].get(tag, {'info': '', 'samples': []})

    metrics = build_price_metrics(profile.get('samples', []), inventory_count)
    if metrics:
        metrics['source'] = f'{tag} market samples'
        return metrics

    metrics = get_global_price_metrics(data, inventory_count=inventory_count)
    if metrics:
        metrics['source'] = f'global market samples fallback for {tag}'
        return metrics

    return None


def get_tag_info(data, tag):
    profile = data['tag_profiles'].get(tag, {})
    return str(profile.get('info', '')).strip()


def generate_next_account_code(data):
    return generate_unique_account_code(set(data['accounts'].keys()))


def format_account_brief(data, account):
    tag = account.get('tag', '')
    metrics = get_tag_price_metrics(data, tag)

    parts = [
        account.get('code', 'NO-CODE'),
        account.get('stock_name', 'Unnamed stock'),
    ]
    if account.get('name'):
        parts.append(account['name'])
    parts.append(f'[{tag}]')
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

    for tag in VALID_TAGS:
        metrics = get_tag_price_metrics(data, tag)
        if not metrics:
            continue

        total_value += metrics['inventory_value']
        priced_accounts += metrics['inventory_count']

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


def prompt_non_negative_int(message, default=0):
    raw_value = input(message).strip()
    if not raw_value:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        print('Please enter a whole number.')
        return None

    if value < 0:
        print('Value cannot be negative.')
        return None

    return value


def prompt_tag(message, allow_blank=False):
    print(message)
    for index, tag in enumerate(VALID_TAGS, start=1):
        print(f'{index}) {tag}')
    if allow_blank:
        print('0) Global fallback')

    raw_value = input('Choose tag number or name: ').strip().upper()
    if allow_blank and raw_value in ('', '0'):
        return ''

    choice_map = {str(index): tag for index, tag in enumerate(VALID_TAGS, start=1)}
    tag = choice_map.get(raw_value, raw_value)

    if tag not in VALID_TAGS:
        print(f'Invalid tag. Use one of {", ".join(VALID_TAGS)}.')
        return None

    return tag


def print_tag_snapshot(data, tag):
    info = get_tag_info(data, tag)
    metrics = get_tag_price_metrics(data, tag)

    print(f'Tag selected: {tag}')
    if info:
        print(f'Tag info: {info}')
    else:
        print(f'No saved info yet for {tag}. Use "Set tag info" to store details.')

    if metrics:
        print(f'Auto price for {tag}: {format_php(metrics["unit_price"])} ({metrics["source"]})')
    else:
        print(f'No saved market price yet for {tag}. Add a market sample for this tag.')


def add_account(data):
    accounts = data['accounts']
    stock_name = input('Stock/account name: ').strip()
    account_name = input('Account name: ').strip()
    link = input('Account link (optional): ').strip()
    if not stock_name or not account_name:
        print('Stock/account name and account name cannot be empty.')
        return

    email = input('Email: ').strip()
    password = getpass.getpass('Password: ').strip()
    fbfs = prompt_non_negative_int('fbfs count (default 0): ')
    if fbfs is None:
        return
    tag = prompt_tag('Choose a tag for this account:')
    if tag is None:
        return

    print_tag_snapshot(data, tag)
    notes = input('Notes (optional): ').strip()

    if not email or not password:
        print('Email and password cannot be empty.')
        return

    code = generate_next_account_code(data)
    accounts[code] = {
        'code': code,
        'stock_name': stock_name,
        'name': account_name,
        'link': link,
        'email': email,
        'password': password,
        'legacy_password_hash': '',
        'tag': tag,
        'notes': notes,
        'fbfs': fbfs,
    }
    save_data(data)
    print(f'Added stock/account: {stock_name} ({tag})')
    print(f'Account code: {code}')

    metrics = get_tag_price_metrics(data, tag)
    if metrics:
        print(f'Estimated price for {code}: {format_php(metrics["unit_price"])}')


def list_accounts(data):
    accounts = data['accounts']
    if not accounts:
        print('No accounts stored.')
        return

    print('\nStored accounts:')
    for key in sorted(accounts.keys()):
        account = accounts[key]
        tag = account.get('tag', '')
        info = get_tag_info(data, tag)
        metrics = get_tag_price_metrics(data, tag)

        line = f'- {account.get("code", key)} | {account.get("stock_name", "Unnamed stock")}'
        if account.get('name'):
            line += f' | name: {account["name"]}'
        line += f' [{tag}]'
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

    tag = account.get('tag', '')
    info = get_tag_info(data, tag)
    metrics = get_tag_price_metrics(data, tag)
    password = account.get('password', '')
    legacy_password_hash = account.get('legacy_password_hash', '')

    print(
        f"\n{account.get('stock_name', 'Unnamed stock')}:"
        f"\n  code: {account.get('code', 'no code')}"
        f"\n  name: {account.get('name') or 'no name saved'}"
        f"\n  link: {account.get('link') or 'no link saved'}"
        f"\n  email: {account.get('email')}"
        f"\n  tag: {tag}"
        f"\n  tag_info: {info or 'no saved info'}"
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
    stock_name = account.get('stock_name', 'Unnamed stock')
    confirm = input(f'Confirm delete {code} ({stock_name})? (y/N): ').strip().lower()
    if confirm == 'y':
        del data['accounts'][code]
        save_data(data)
        print('Deleted.')
    else:
        print('Delete canceled.')


def add_market_sample(data):
    tag = prompt_tag(
        'Choose a tag for this market listing:',
        allow_blank=True,
    )
    if tag is None:
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

    if tag:
        data['tag_profiles'][tag]['samples'].append(sample)
        save_data(data)

        unit_price = total_price_php / account_count
        print(
            f'Added {tag} market sample: {format_php(total_price_php)} for '
            f'{account_count} account(s) -> {format_php(unit_price)} each'
        )

        metrics = get_tag_price_metrics(data, tag)
        if metrics:
            print(f'Updated auto price for {tag}: {format_php(metrics["unit_price"])}')
            print(f'Estimated {tag} inventory value: {format_php(metrics["inventory_value"])}')
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


def set_tag_info(data):
    tag = prompt_tag('Choose a tag to configure:')
    if tag is None:
        return

    current_info = get_tag_info(data, tag)
    if current_info:
        print(f'Current info for {tag}: {current_info}')
    else:
        print(f'No info saved yet for {tag}.')

    info = input(f'Info/description for {tag} (leave blank to clear): ').strip()
    data['tag_profiles'][tag]['info'] = info
    save_data(data)

    if info:
        print(f'Saved info for {tag}.')
    else:
        print(f'Cleared info for {tag}.')

    metrics = get_tag_price_metrics(data, tag)
    if metrics:
        print(f'Current auto price for {tag}: {format_php(metrics["unit_price"])}')


def show_pricing_summary(data):
    print('\nTag pricing summary:')
    for tag in VALID_TAGS:
        info = get_tag_info(data, tag) or 'no saved info'
        profile_samples = data['tag_profiles'][tag]['samples']
        metrics = get_tag_price_metrics(data, tag)
        inventory_count = count_accounts_for_tag(data, tag)

        print(f'- {tag}: {info}')
        print(f'  stored accounts: {inventory_count}')
        print(f'  tag-specific market samples: {len(profile_samples)}')

        if metrics:
            print(f'  auto price: {format_php(metrics["unit_price"])}')
            print(f'  pricing source: {metrics["source"]}')
            print(f'  estimated tag inventory value: {format_php(metrics["inventory_value"])}')
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
        print('1) Add stock/account')
        print('2) List accounts')
        print('3) View/fetch account')
        print('4) Delete account')
        print('5) Add market price sample')
        print('6) Set tag info')
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
            set_tag_info(data)
        elif choice == '7':
            show_pricing_summary(data)
        elif choice == '8':
            print('Bye')
            break
        else:
            print('Invalid choice')


if __name__ == '__main__':
    main()
