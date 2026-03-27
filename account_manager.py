#!/usr/bin/env python3
"""Termux account storage CLI with tag-based pricing."""

import getpass
import hashlib
import json
import os

DATA_FILE = os.path.expanduser('~/.termux_accounts.json')
VALID_TAGS = ('RA', 'RP', 'MX', 'ON')


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


def normalize_accounts(accounts):
    if not isinstance(accounts, dict):
        return {}

    normalized = {}
    for name, info in accounts.items():
        if not isinstance(info, dict):
            continue

        normalized[name] = {
            'email': str(info.get('email', '')).strip(),
            'password_hash': str(info.get('password_hash', '')).strip(),
            'tag': str(info.get('tag', '')).upper().strip(),
            'notes': str(info.get('notes', '')).strip(),
        }

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


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


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
    name = input('Account/stock name (e.g. gmail, github, stock code): ').strip()
    if not name:
        print('Name cannot be empty.')
        return

    if name in accounts:
        print('Account exists. Use a different name.')
        return

    email = input('Email: ').strip()
    password = getpass.getpass('Password (hidden): ').strip()
    tag = prompt_tag('Choose a tag for this account:')
    if tag is None:
        return

    print_tag_snapshot(data, tag)
    notes = input('Notes (optional): ').strip()

    if not email or not password:
        print('Email and password cannot be empty.')
        return

    accounts[name] = {
        'email': email,
        'password_hash': hash_password(password),
        'tag': tag,
        'notes': notes,
    }
    save_data(data)
    print(f'Added stock/account: {name} ({tag})')

    metrics = get_tag_price_metrics(data, tag)
    if metrics:
        print(f'Estimated price for {name}: {format_php(metrics["unit_price"])}')


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

        line = f'- {key} [{tag}]'
        if info:
            line += f' | {info}'
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
    accounts = data['accounts']
    name = input('Account name to view: ').strip()
    if name not in accounts:
        print('Not found.')
        return

    account = accounts[name]
    tag = account.get('tag', '')
    info = get_tag_info(data, tag)
    metrics = get_tag_price_metrics(data, tag)

    print(
        f"\n{name}:"
        f"\n  email: {account.get('email')}"
        f"\n  tag: {tag}"
        f"\n  tag_info: {info or 'no saved info'}"
        f"\n  notes: {account.get('notes')}"
        f"\n  password_hash: {account.get('password_hash')}"
    )

    if metrics:
        print(f'  estimated_price_php: {format_php(metrics["unit_price"])}')
        print(f'  pricing_source: {metrics["source"]}')
    else:
        print('  estimated_price_php: no market data')


def delete_account(data):
    accounts = data['accounts']
    name = input('Account name to delete: ').strip()
    if name not in accounts:
        print('Not found.')
        return

    confirm = input(f'Confirm delete {name}? (y/N): ').strip().lower()
    if confirm == 'y':
        del accounts[name]
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
        print('3) View account')
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
