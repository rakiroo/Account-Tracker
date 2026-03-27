#!/usr/bin/env python3
from __future__ import annotations

"""Private web app for MAUS Account Tracker."""

import os
from functools import wraps
from threading import Lock

from flask import Flask, flash, redirect, render_template, request, session, url_for

import account_manager as core

DATA_LOCK = Lock()
WEB_PASSWORD = os.environ.get('MAUS_WEB_PASSWORD', '').strip()
WEB_SECRET = os.environ.get('MAUS_WEB_SECRET_KEY', 'maus-web-secret-change-me').strip()
WEB_HOST = os.environ.get('MAUS_WEB_HOST', '127.0.0.1').strip() or '127.0.0.1'
WEB_PORT = int(os.environ.get('MAUS_WEB_PORT', '5000'))


def build_account_form_values(form_data=None, account=None):
    source = form_data or {}
    account = account or {}
    return {
        'stock_name': source.get('stock_name', account.get('stock_name', core.STOCK_CHOICES[0])),
        'name': source.get('name', account.get('name', '')),
        'link': source.get('link', account.get('link', '')),
        'email': source.get('email', account.get('email', '')),
        'password': source.get('password', account.get('password', '')),
        'fbfs': source.get('fbfs', account.get('fbfs', 0)),
        'notes': source.get('notes', account.get('notes', '')),
    }


def parse_account_form(form_data):
    stock_name = core.parse_stock_choice(form_data.get('stock_name', ''))
    if stock_name not in core.STOCK_CHOICES:
        return None, f'Choose a valid stock: {", ".join(core.STOCK_CHOICES)}'

    name = str(form_data.get('name', '')).strip()
    email = str(form_data.get('email', '')).strip()
    password = str(form_data.get('password', '')).strip()
    link = core.normalize_optional_text(form_data.get('link', ''))
    notes = core.normalize_optional_text(form_data.get('notes', ''))

    if not name:
        return None, 'Name is required.'
    if not email:
        return None, 'Email is required.'
    if not password:
        return None, 'Password is required.'

    try:
        fbfs = int(str(form_data.get('fbfs', '0')).strip())
    except ValueError:
        return None, 'fbfs must be a whole number.'
    if fbfs < 0:
        return None, 'fbfs cannot be negative.'

    return {
        'stock_name': stock_name,
        'name': name,
        'link': link,
        'email': email,
        'password': password,
        'fbfs': fbfs,
        'notes': notes,
    }, None


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not WEB_PASSWORD:
            return view_func(*args, **kwargs)
        if session.get('maus_authenticated'):
            return view_func(*args, **kwargs)
        return redirect(url_for('login', next=request.path))

    return wrapped_view


def create_app():
    web = Flask(__name__)
    web.secret_key = WEB_SECRET
    web.jinja_env.filters['php'] = core.format_php
    web.jinja_env.filters['signed_php'] = core.format_signed_php
    web.jinja_env.filters['signed_percent'] = core.format_signed_percent

    @web.context_processor
    def inject_layout_helpers():
        return {
            'app_title': 'MAUS Web',
            'needs_login': bool(WEB_PASSWORD),
            'stock_choices': core.STOCK_CHOICES,
        }

    @web.route('/login', methods=['GET', 'POST'])
    def login():
        if not WEB_PASSWORD:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            password = request.form.get('password', '')
            if password == WEB_PASSWORD:
                session['maus_authenticated'] = True
                flash('Web vault unlocked.', 'success')
                next_url = request.args.get('next') or url_for('dashboard')
                return redirect(next_url)
            flash('Wrong password.', 'error')

        return render_template('login.html')

    @web.route('/logout')
    def logout():
        session.pop('maus_authenticated', None)
        flash('Web vault locked.', 'info')
        return redirect(url_for('login'))

    @web.route('/')
    @login_required
    def dashboard():
        with DATA_LOCK:
            data = core.load_data()

        store_summary = core.get_store_value_summary(data)
        sales_summary = core.get_sales_summary(data)
        stock_cards = []
        for stock_name in core.STOCK_CHOICES:
            metrics = core.get_stock_price_metrics(data, stock_name)
            state = core.get_stock_market_state(data, stock_name)
            stock_cards.append(
                {
                    'stock_name': stock_name,
                    'info': core.get_stock_info(data, stock_name),
                    'active_count': core.count_accounts_for_stock(data, stock_name),
                    'sold_count': core.count_sold_accounts_for_stock(data, stock_name),
                    'metrics': metrics,
                    'state': state,
                }
            )

        recent_accounts = sorted(
            data['accounts'].values(),
            key=lambda account: account.get('code', ''),
            reverse=True,
        )[:8]
        recent_sales = sorted(
            data.get('sold_accounts', {}).values(),
            key=lambda account: (account.get('sold_at', ''), account.get('code', '')),
            reverse=True,
        )[:6]

        return render_template(
            'dashboard.html',
            store_summary=store_summary,
            sales_summary=sales_summary,
            stock_cards=stock_cards,
            recent_accounts=recent_accounts,
            recent_sales=recent_sales,
        )

    @web.route('/accounts')
    @login_required
    def accounts():
        query = request.args.get('q', '').strip()
        stock_filter = request.args.get('stock', '').strip().upper()

        with DATA_LOCK:
            data = core.load_data()

        if query:
            account_list = core.search_accounts(data, query)
        else:
            account_list = sorted(data['accounts'].values(), key=lambda account: account.get('code', ''))

        if stock_filter in core.STOCK_CHOICES:
            account_list = [account for account in account_list if account.get('stock_name') == stock_filter]
        else:
            stock_filter = ''

        account_cards = []
        for account in account_list:
            stock_name = account.get('stock_name', '')
            account_cards.append(
                {
                    'account': account,
                    'info': core.get_stock_info(data, stock_name),
                    'metrics': core.get_stock_price_metrics(data, stock_name),
                }
            )

        return render_template(
            'accounts.html',
            account_cards=account_cards,
            query=query,
            stock_filter=stock_filter,
        )

    @web.route('/accounts/new', methods=['GET', 'POST'])
    @login_required
    def account_new():
        values = build_account_form_values()

        if request.method == 'POST':
            values = build_account_form_values(request.form)
            cleaned, error = parse_account_form(request.form)
            if error:
                flash(error, 'error')
            else:
                with DATA_LOCK:
                    data = core.load_data()
                    code, record_or_error = core.create_account_record(
                        data,
                        cleaned['stock_name'],
                        cleaned['name'],
                        cleaned['link'],
                        cleaned['email'],
                        cleaned['password'],
                        cleaned['fbfs'],
                        cleaned['notes'],
                    )
                    if code is None:
                        flash(record_or_error, 'error')
                    else:
                        data['accounts'][code] = record_or_error
                        core.save_data(data)
                        flash(f'Added {code}.', 'success')
                        return redirect(url_for('account_detail', code=code))

        return render_template('account_form.html', values=values, mode='new', account_code='')

    @web.route('/accounts/<code>')
    @login_required
    def account_detail(code):
        account_code = code.strip().upper()
        with DATA_LOCK:
            data = core.load_data()
            account = data['accounts'].get(account_code)

        if not account:
            flash('Active account not found.', 'error')
            return redirect(url_for('accounts'))

        return render_template(
            'account_detail.html',
            account=account,
            stock_info=core.get_stock_info(data, account.get('stock_name', '')),
            metrics=core.get_stock_price_metrics(data, account.get('stock_name', '')),
        )

    @web.route('/accounts/<code>/edit', methods=['GET', 'POST'])
    @login_required
    def account_edit(code):
        account_code = code.strip().upper()
        with DATA_LOCK:
            data = core.load_data()
            account = data['accounts'].get(account_code)

        if not account:
            flash('Active account not found.', 'error')
            return redirect(url_for('accounts'))

        values = build_account_form_values(account=account)
        if request.method == 'POST':
            values = build_account_form_values(request.form, account=account)
            cleaned, error = parse_account_form(request.form)
            if error:
                flash(error, 'error')
            else:
                with DATA_LOCK:
                    data = core.load_data()
                    account = data['accounts'].get(account_code)
                    if not account:
                        flash('Active account not found.', 'error')
                        return redirect(url_for('accounts'))

                    changes = core.update_account_fields(account, cleaned)
                    if not changes:
                        flash('No changes saved.', 'info')
                    else:
                        core.save_data(data)
                        flash(f'Updated {account_code}: {", ".join(changes)}', 'success')
                    return redirect(url_for('account_detail', code=account_code))

        return render_template('account_form.html', values=values, mode='edit', account_code=account_code)

    @web.route('/accounts/<code>/sell', methods=['POST'])
    @login_required
    def account_sell(code):
        account_code = code.strip().upper()
        sold_price_raw = request.form.get('sold_price', '').strip()
        sold_note = request.form.get('sold_note', '').strip()
        sold_at = request.form.get('sold_at', '').strip()

        try:
            sold_price = core.parse_price_text(sold_price_raw)
        except ValueError:
            flash('Sold price must look like 54, 54php, or 1,250.', 'error')
            return redirect(url_for('account_detail', code=account_code))

        if sold_price <= 0:
            flash('Sold price must be greater than zero.', 'error')
            return redirect(url_for('account_detail', code=account_code))

        with DATA_LOCK:
            data = core.load_data()
            account = data['accounts'].get(account_code)
            if not account:
                flash('Active account not found.', 'error')
                return redirect(url_for('accounts'))

            sold_record = core.sell_account_record(
                data,
                account,
                sold_price_php=sold_price,
                sold_at=sold_at or core.current_timestamp_text(),
                sold_note=sold_note,
            )
            core.save_data(data)

        flash(
            f'Sold {account_code} for {core.format_php(sold_record["sold_price_php"])}.',
            'success',
        )
        return redirect(url_for('sold_history'))

    @web.route('/accounts/<code>/delete', methods=['POST'])
    @login_required
    def account_delete(code):
        account_code = code.strip().upper()
        with DATA_LOCK:
            data = core.load_data()
            if account_code not in data['accounts']:
                flash('Active account not found.', 'error')
            else:
                del data['accounts'][account_code]
                core.save_data(data)
                flash(f'Deleted {account_code}.', 'success')
        return redirect(url_for('accounts'))

    @web.route('/sold')
    @login_required
    def sold_history():
        with DATA_LOCK:
            data = core.load_data()

        sold_accounts = sorted(
            data.get('sold_accounts', {}).values(),
            key=lambda account: (account.get('sold_at', ''), account.get('code', '')),
            reverse=True,
        )
        sold_cards = [
            {
                'account': account,
                'comparison': core.describe_sale_vs_market(account),
            }
            for account in sold_accounts
        ]
        return render_template(
            'sold.html',
            sold_cards=sold_cards,
            sales_summary=core.get_sales_summary(data),
        )

    @web.route('/market')
    @login_required
    def market():
        with DATA_LOCK:
            data = core.load_data()

        stock_rows = []
        for stock_name in core.STOCK_CHOICES:
            stock_rows.append(
                {
                    'stock_name': stock_name,
                    'info': core.get_stock_info(data, stock_name),
                    'state': core.get_stock_market_state(data, stock_name),
                    'metrics': core.get_stock_price_metrics(data, stock_name),
                    'active_count': core.count_accounts_for_stock(data, stock_name),
                    'sold_count': core.count_sold_accounts_for_stock(data, stock_name),
                    'sample_count': len(data['stock_profiles'][stock_name]['samples']),
                }
            )

        return render_template(
            'market.html',
            stock_rows=stock_rows,
            global_state=core.get_global_market_state(data),
            global_samples=len(data['pricing']['samples']),
            store_summary=core.get_store_value_summary(data),
        )

    @web.route('/market/sample', methods=['POST'])
    @login_required
    def market_sample_add():
        stock_name_raw = request.form.get('stock_name', '').strip().upper()
        if stock_name_raw in ('', 'GLOBAL'):
            stock_name = ''
        else:
            stock_name = core.parse_stock_choice(stock_name_raw)
            if stock_name not in core.STOCK_CHOICES:
                flash('Choose a valid stock or Global fallback.', 'error')
                return redirect(url_for('market'))

        try:
            total_price_php = core.parse_price_text(request.form.get('total_price_php', '').strip())
        except ValueError:
            flash('Observed market price is invalid.', 'error')
            return redirect(url_for('market'))

        try:
            account_count = int(request.form.get('account_count', '0').strip())
        except ValueError:
            flash('Account count must be a whole number.', 'error')
            return redirect(url_for('market'))

        if total_price_php <= 0 or account_count <= 0:
            flash('Price and account count must both be greater than zero.', 'error')
            return redirect(url_for('market'))

        sample = {
            'total_price_php': round(total_price_php, 2),
            'account_count': account_count,
            'note': request.form.get('note', '').strip(),
            'recorded_at': request.form.get('recorded_at', '').strip() or core.current_timestamp_text(),
        }

        with DATA_LOCK:
            data = core.load_data()
            if stock_name:
                data['stock_profiles'][stock_name]['samples'].append(sample)
            else:
                data['pricing']['samples'].append(sample)
            core.save_data(data)

        target = stock_name or 'Global fallback'
        flash(f'Added market sample for {target}.', 'success')
        return redirect(url_for('market'))

    @web.route('/market/info', methods=['POST'])
    @login_required
    def market_info_save():
        stock_name = core.parse_stock_choice(request.form.get('stock_name', '').strip())
        if stock_name not in core.STOCK_CHOICES:
            flash('Choose a valid stock.', 'error')
            return redirect(url_for('market'))

        info = request.form.get('info', '').strip()
        with DATA_LOCK:
            data = core.load_data()
            data['stock_profiles'][stock_name]['info'] = info
            core.save_data(data)

        flash(f'Saved stock info for {stock_name}.', 'success')
        return redirect(url_for('market'))

    return web


app = create_app()


if __name__ == '__main__':
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
