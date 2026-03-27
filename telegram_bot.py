#!/usr/bin/env python3
from __future__ import annotations

"""Telegram bot interface for MAUS Account Tracker."""

import logging
import os
from functools import wraps
from threading import Lock

import account_manager as app

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing
    Update = None
    Application = None
    ContextTypes = None
    CommandHandler = None
    MessageHandler = None
    filters = None


logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    level=logging.INFO,
)
LOGGER = logging.getLogger('maus.telegram')
DATA_LOCK = Lock()
MAX_LIST_RESULTS = 25
MAX_SEARCH_RESULTS = 10
MAX_SOLD_RESULTS = 15


def get_bot_token():
    return os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()


def get_allowed_user_ids():
    raw_value = os.environ.get('TELEGRAM_ALLOWED_USER_IDS', '').strip()
    if not raw_value:
        return set()

    allowed_ids = set()
    for part in raw_value.split(','):
        cleaned = part.strip()
        if not cleaned:
            continue
        allowed_ids.add(int(cleaned))
    return allowed_ids


ALLOWED_USER_IDS = get_allowed_user_ids()


def build_help_text():
    return '\n'.join(
        [
            'MAUS Telegram Bot',
            '',
            '/stats - inventory and sales totals',
            '/list [stock] - list active accounts, optionally filtered by RA/PR/ON/MN/RP',
            '/find <code or name> - fetch account details',
            '/market [stock|global] - show market state',
            '/sold [limit] - show recent sold accounts',
            '/setfbfs <code> <number> - update fbfs for one active account',
            '/sell <code> <price> [note] - mark an active account as sold',
            '/help - show this command list',
        ]
    )


def build_account_detail_text(data, account):
    return '\n'.join(app.build_account_detail_lines(data, account))


def build_market_state_text(label, state):
    if not state:
        return f'{label}: no market samples yet'

    lines = [
        f'{label}',
        f'Latest: {app.format_php(state["latest_unit_price"])}',
        f'Observed: {state["latest_recorded_at"] or "unknown time"}',
        f'Weighted: {app.format_php(state["weighted_unit_price"])}',
        f'Range: {app.format_php(state["lowest_unit_price"])} to {app.format_php(state["highest_unit_price"])}',
        f'Samples: {state["sample_count"]}',
    ]
    if state['movement_php'] is None:
        lines.append('Trend: not enough data yet')
    else:
        lines.append(f'Trend: {state["direction"]} {app.format_signed_php(state["movement_php"])} vs previous sample')
    if state.get('latest_note'):
        lines.append(f'Latest note: {state["latest_note"]}')
    return '\n'.join(lines)


async def reply(update, text):
    if update.effective_message:
        await update.effective_message.reply_text(text)


def admin_only(handler):
    @wraps(handler)
    async def wrapper(update, context):
        user = update.effective_user
        if user is None or user.id not in ALLOWED_USER_IDS:
            LOGGER.warning('Denied Telegram access for user_id=%s', getattr(user, 'id', None))
            await reply(update, 'Access denied.')
            return
        return await handler(update, context)

    return wrapper


@admin_only
async def start_command(update, context):
    await reply(update, build_help_text())


@admin_only
async def help_command(update, context):
    await reply(update, build_help_text())


@admin_only
async def stats_command(update, context):
    with DATA_LOCK:
        data = app.load_data()

    store_summary = app.get_store_value_summary(data)
    sales_summary = app.get_sales_summary(data)
    lines = [
        'MAUS Stats',
        f'Active accounts: {store_summary["inventory_count"]}',
        f'Priced accounts: {store_summary["priced_accounts"]}',
        f'Estimated inventory value: {app.format_php(store_summary["inventory_value"])}',
        f'Sold accounts: {sales_summary["sold_count"]}',
        f'Total sold value: {app.format_php(sales_summary["total_sales_value"])}',
    ]

    for stock_name in app.STOCK_CHOICES:
        active_count = app.count_accounts_for_stock(data, stock_name)
        sold_count = app.count_sold_accounts_for_stock(data, stock_name)
        metrics = app.get_stock_price_metrics(data, stock_name)
        price_text = app.format_php(metrics['unit_price']) if metrics else 'no market data'
        lines.append(f'{stock_name}: active {active_count} | sold {sold_count} | {price_text}')

    await reply(update, '\n'.join(lines))


@admin_only
async def list_command(update, context):
    stock_filter = ''
    if context.args:
        stock_filter = context.args[0].strip().upper()
        if stock_filter not in app.STOCK_CHOICES:
            await reply(update, f'Invalid stock. Use one of: {", ".join(app.STOCK_CHOICES)}')
            return

    with DATA_LOCK:
        data = app.load_data()

    accounts = sorted(data['accounts'].values(), key=lambda account: account.get('code', ''))
    if stock_filter:
        accounts = [account for account in accounts if account.get('stock_name') == stock_filter]

    if not accounts:
        message = 'No active accounts found.'
        if stock_filter:
            message = f'No active accounts found for {stock_filter}.'
        await reply(update, message)
        return

    lines = [f'Active accounts: {len(accounts)}']
    if stock_filter:
        lines.append(f'Filter: {stock_filter}')

    for account in accounts[:MAX_LIST_RESULTS]:
        metrics = app.get_stock_price_metrics(data, account.get('stock_name', ''))
        price_text = app.format_php(metrics['unit_price']) if metrics else 'no price'
        lines.append(
            f'{account.get("code", "no code")} | {account.get("stock_name", "UNKNOWN")} | '
            f'{account.get("name") or "no name"} | fbfs {account.get("fbfs", 0)} | {price_text}'
        )

    if len(accounts) > MAX_LIST_RESULTS:
        lines.append(f'...and {len(accounts) - MAX_LIST_RESULTS} more')

    await reply(update, '\n'.join(lines))


@admin_only
async def find_command(update, context):
    query = ' '.join(context.args).strip()
    if not query:
        await reply(update, 'Usage: /find <code or name>')
        return

    with DATA_LOCK:
        data = app.load_data()
        matches = app.search_accounts(data, query)

    if not matches:
        await reply(update, 'No matching active account found.')
        return

    if len(matches) == 1:
        await reply(update, build_account_detail_text(data, matches[0]))
        return

    lines = [f'Multiple matches: {len(matches)}']
    for account in matches[:MAX_SEARCH_RESULTS]:
        lines.append(app.format_account_brief(data, account))
    if len(matches) > MAX_SEARCH_RESULTS:
        lines.append(f'...and {len(matches) - MAX_SEARCH_RESULTS} more')
    lines.append('Use /find with the exact code for one result.')
    await reply(update, '\n'.join(lines))


@admin_only
async def market_command(update, context):
    query = context.args[0].strip().upper() if context.args else ''

    with DATA_LOCK:
        data = app.load_data()

    if not query:
        lines = ['Market State']
        for stock_name in app.STOCK_CHOICES:
            state = app.get_stock_market_state(data, stock_name)
            if state:
                lines.append(
                    f'{stock_name}: {app.format_php(state["latest_unit_price"])} | '
                    f'{state["direction"]} | samples {state["sample_count"]}'
                )
            else:
                lines.append(f'{stock_name}: no market samples yet')

        global_state = app.get_global_market_state(data)
        if global_state:
            lines.append(f'GLOBAL: {app.format_php(global_state["latest_unit_price"])} | {global_state["direction"]}')
        else:
            lines.append('GLOBAL: no market samples yet')

        await reply(update, '\n'.join(lines))
        return

    if query in ('GLOBAL', 'FALLBACK'):
        state = app.get_global_market_state(data)
        await reply(update, build_market_state_text('Global Fallback', state))
        return

    if query not in app.STOCK_CHOICES:
        await reply(update, f'Invalid stock. Use one of: {", ".join(app.STOCK_CHOICES)} or global')
        return

    state = app.get_stock_market_state(data, query)
    await reply(update, build_market_state_text(f'{query} Market State', state))


@admin_only
async def sold_command(update, context):
    limit = MAX_SOLD_RESULTS
    if context.args:
        try:
            limit = max(1, min(int(context.args[0]), 50))
        except ValueError:
            await reply(update, 'Usage: /sold [limit]')
            return

    with DATA_LOCK:
        data = app.load_data()

    sold_accounts = list(data.get('sold_accounts', {}).values())
    if not sold_accounts:
        await reply(update, 'No sold accounts yet.')
        return

    sold_accounts.sort(
        key=lambda account: (
            account.get('sold_at', ''),
            account.get('code', ''),
        ),
        reverse=True,
    )

    lines = [f'Sold accounts: {len(sold_accounts)}']
    for account in sold_accounts[:limit]:
        lines.append(
            f'{account.get("code", "no code")} | {account.get("stock_name", "UNKNOWN")} | '
            f'{account.get("name") or "no name"} | sold {app.format_php(account.get("sold_price_php", 0.0))} | '
            f'{account.get("sold_at") or "no date"}'
        )
        lines.append(f'  {app.describe_sale_vs_market(account)}')

    if len(sold_accounts) > limit:
        lines.append(f'...and {len(sold_accounts) - limit} more')

    await reply(update, '\n'.join(lines))


@admin_only
async def setfbfs_command(update, context):
    if len(context.args) != 2:
        await reply(update, 'Usage: /setfbfs <code> <number>')
        return

    code = context.args[0].strip().upper()
    try:
        fbfs_value = int(context.args[1])
    except ValueError:
        await reply(update, 'fbfs must be a whole number.')
        return

    if fbfs_value < 0:
        await reply(update, 'fbfs cannot be negative.')
        return

    with DATA_LOCK:
        data = app.load_data()
        account = data['accounts'].get(code)
        if not account:
            account_found = False
            changes = []
            metrics = None
        else:
            account_found = True
            changes = app.update_account_fields(account, {'fbfs': fbfs_value})
            if changes:
                app.save_data(data)
            metrics = app.get_stock_price_metrics(data, account.get('stock_name', ''))

    if not account_found:
        await reply(update, f'Active account not found: {code}')
        return
    if not changes:
        await reply(update, f'No change. {code} already has fbfs {fbfs_value}.')
        return

    lines = [
        f'Updated {code}',
        f'Name: {account.get("name") or "no name"}',
        f'fbfs: {account.get("fbfs", 0)}',
    ]
    if metrics:
        lines.append(f'Current auto price: {app.format_php(metrics["unit_price"])}')
    await reply(update, '\n'.join(lines))


@admin_only
async def sell_command(update, context):
    if len(context.args) < 2:
        await reply(update, 'Usage: /sell <code> <price> [note]')
        return

    code = context.args[0].strip().upper()
    try:
        sold_price_php = app.parse_price_text(context.args[1])
    except ValueError:
        await reply(update, 'Price must look like 54, 54php, or 1,250')
        return

    if sold_price_php <= 0:
        await reply(update, 'Sold price must be greater than zero.')
        return

    sold_note = ' '.join(context.args[2:]).strip()

    with DATA_LOCK:
        data = app.load_data()
        account = data['accounts'].get(code)
        if not account:
            sold_record = None
        else:
            sold_record = app.sell_account_record(
                data,
                account,
                sold_price_php=sold_price_php,
                sold_at=app.current_timestamp_text(),
                sold_note=sold_note,
            )
            app.save_data(data)

    if not sold_record:
        await reply(update, f'Active account not found: {code}')
        return

    lines = [
        f'Sold {sold_record.get("code", "no code")} for {app.format_php(sold_record.get("sold_price_php", 0.0))}',
        f'Stock: {sold_record.get("stock_name", "UNKNOWN")}',
        f'Name: {sold_record.get("name") or "no name"}',
        f'Sold at: {sold_record.get("sold_at") or "no date"}',
    ]
    if sold_note:
        lines.append(f'Note: {sold_note}')
    lines.append(app.describe_sale_vs_market(sold_record))
    await reply(update, '\n'.join(lines))


@admin_only
async def unknown_command(update, context):
    await reply(update, 'Unknown command.\n\n' + build_help_text())


def build_application():
    application = Application.builder().token(get_bot_token()).build()
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('stats', stats_command))
    application.add_handler(CommandHandler('list', list_command))
    application.add_handler(CommandHandler('find', find_command))
    application.add_handler(CommandHandler('market', market_command))
    application.add_handler(CommandHandler('sold', sold_command))
    application.add_handler(CommandHandler('setfbfs', setfbfs_command))
    application.add_handler(CommandHandler('sell', sell_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    return application


def main():
    if Application is None:
        raise SystemExit(
            'python-telegram-bot is not installed. Run: pip install -r requirements.txt'
        )

    token = get_bot_token()
    if not token:
        raise SystemExit('Missing TELEGRAM_BOT_TOKEN environment variable.')

    if not ALLOWED_USER_IDS:
        raise SystemExit(
            'Missing TELEGRAM_ALLOWED_USER_IDS environment variable. '
            'Set it to your Telegram numeric user id, or a comma-separated list.'
        )

    LOGGER.info('Starting MAUS Telegram bot for %s allowed user(s)', len(ALLOWED_USER_IDS))
    build_application().run_polling()


if __name__ == '__main__':
    main()
