"""Simple role-based lost and found application."""
import os
import secrets
from io import BytesIO
from functools import wraps
from datetime import date

import click
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from PIL import Image, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from database import DatabaseManager
from models import Item

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
db = DatabaseManager(os.environ.get('DATABASE_PATH', 'lost_found.db'))


@app.cli.command('create-admin')
@click.argument('username')
@click.password_option(confirmation_prompt=True)
def create_admin(username, password):
    """Create an administrator without exposing admin registration on the web."""
    if not username.strip() or len(password) < 8:
        raise click.ClickException('A username and password of at least 8 characters are required.')
    try:
        with db.get_connection() as conn:
            conn.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                         (username.strip(), generate_password_hash(password), 'admin'))
    except __import__('sqlite3').IntegrityError:
        raise click.ClickException('Username already exists.')
    click.echo('Administrator created.')


@app.before_request
def csrf_protection():
    if request.method == 'POST':
        token = session.get('csrf_token', '')
        if not token or not secrets.compare_digest(token, request.form.get('csrf_token', '')):
            abort(400, 'Invalid form token. Refresh the page and try again.')


@app.context_processor
def inject_token():
    return {'csrf_token': session.setdefault('csrf_token', secrets.token_hex(32))}


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get('user_id'):
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


@app.route('/')
def index():
    return redirect(url_for('dashboard') if session.get('user_id') else url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or len(password) < 8:
            flash('Enter a username and a password of at least 8 characters.')
        else:
            try:
                with db.get_connection() as conn:
                    conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
                                 (username, generate_password_hash(password)))
                flash('Account created. Please log in.')
                return redirect(url_for('login'))
            except __import__('sqlite3').IntegrityError:
                flash('That username is already taken.')
    return render_template('auth.html', register=True)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        with db.get_connection() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?',
                                (request.form.get('username', '').strip(),)).fetchone()
        selected_role = request.form.get('role', 'user')
        if user and selected_role in ('user', 'admin') and user['role'] == selected_role and check_password_hash(user['password_hash'], request.form.get('password', '')):
            session.clear()
            session.update(user_id=user['id'], username=user['username'], role=user['role'])
            return redirect(url_for('dashboard'))
        flash('Incorrect username, password, or selected account type.')
    return render_template('auth.html', register=False)


@app.post('/logout')
@login_required()
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.get('/dashboard')
@login_required()
def dashboard():
    search = request.args.get('q', '').strip()
    tab = request.args.get('tab', 'lost')
    if tab not in ('lost', 'found', 'returned', 'claims'):
        tab = 'lost'
    status = request.args.get('status', '')
    conditions = ["status = 'Returned'" if tab == 'returned' else "item_type = ? AND status != 'Returned'"]
    values = [] if tab == 'returned' else [tab]
    if search:
        conditions.append('(title LIKE ? OR description LIKE ? OR category LIKE ? OR location LIKE ?)')
        values.extend(['%' + search + '%'] * 4)
    if status in ('Open', 'Pending Verification', 'Claimed') and tab != 'returned':
        conditions.append('status = ?')
        values.append(status)
    with db.get_connection() as conn:
        items = []
        if tab != 'claims':
            query = 'SELECT items.*, photo IS NOT NULL AS has_photo FROM items WHERE ' + ' AND '.join(conditions) + ' ORDER BY id DESC'
            items = conn.execute(query, values).fetchall()
        if session['role'] == 'admin':
            claims = conn.execute('''SELECT claims.*, items.title, users.username FROM claims
                JOIN items ON items.id = claims.item_id JOIN users ON users.id = claims.user_id
                ORDER BY claims.id DESC''').fetchall()
        else:
            claims = conn.execute('''SELECT claims.*, items.title FROM claims JOIN items
                ON items.id = claims.item_id WHERE claims.user_id = ? ORDER BY claims.id DESC''',
                                  (session['user_id'],)).fetchall()
    return render_template('dashboard.html', items=items, claims=claims, search=search, tab=tab, status=status)


@app.get('/items/<int:item_id>/photo')
@login_required()
def item_photo(item_id):
    with db.get_connection() as conn:
        item = conn.execute('SELECT photo, photo_type FROM items WHERE id = ?', (item_id,)).fetchone()
    if not item or not item['photo']:
        abort(404)
    return send_file(BytesIO(item['photo']), mimetype=item['photo_type'])


@app.route('/report', methods=['GET', 'POST'])
@login_required('user')
def report():
    if request.method == 'POST':
        fields = {key: request.form.get(key, '').strip() for key in
                  ('title', 'category', 'item_type', 'description', 'location', 'date_reported', 'reporter_contact')}
        if not all(fields.values()) or fields['item_type'] not in ('lost', 'found'):
            flash('Please complete all fields and select lost or found.')
        else:
            photo, photo_type = None, None
            upload = request.files.get('photo')
            if upload and upload.filename:
                try:
                    photo = upload.read()
                    with Image.open(BytesIO(photo)) as image:
                        image.verify()
                        photo_type = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}.get(image.format)
                    if not photo_type:
                        raise ValueError('Unsupported image')
                except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                    flash('Please upload a valid JPEG, PNG, or WebP image.')
                    return render_template('report.html'), 400
            try:
                date.fromisoformat(fields['date_reported'])
            except ValueError:
                flash('Enter a valid date.')
                return render_template('report.html')
            item = Item(**fields, reporter_name=session['username'])
            # Insert both the report and its owner in one transaction.
            with db.get_connection() as conn:
                conn.execute('''INSERT INTO items (title, category, item_type, description, location,
                    date_reported, reporter_name, reporter_contact, status, reward, created_at, user_id, photo, photo_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (item.title, item.category, item.item_type, item.description, item.location,
                     item.date_reported, item.reporter_name, item.reporter_contact, item.status,
                      item.reward, item.created_at, session['user_id'], photo, photo_type))
            flash('Your report was posted.')
            return redirect(url_for('dashboard', tab=fields['item_type']))
    return render_template('report.html')


@app.post('/items/<int:item_id>/claim')
@login_required('user')
def claim(item_id):
    details = request.form.get('details', '').strip()
    with db.get_connection() as conn:
        item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            abort(404)
        if item['item_type'] != 'found' or item['status'] not in ('Open', 'Pending Verification') or item['user_id'] == session['user_id']:
            abort(400, 'This item cannot be claimed.')
        if not details:
            flash('Provide details that help the admin verify your claim.')
        elif conn.execute("SELECT 1 FROM claims WHERE item_id = ? AND user_id = ? AND status IN ('Pending', 'Approved')", (item_id, session['user_id'])).fetchone():
            flash('You already have a pending or approved claim for this item.')
        else:
            conn.execute('INSERT INTO claims (item_id, user_id, details) VALUES (?, ?, ?)', (item_id, session['user_id'], details))
            conn.execute("UPDATE items SET status = 'Pending Verification' WHERE id = ?", (item_id,))
            flash('Your claim was submitted for admin review.')
    return redirect(url_for('dashboard', tab='claims'))


@app.post('/claims/<int:claim_id>/review')
@login_required('admin')
def review_claim(claim_id):
    decision = request.form.get('decision')
    if decision not in ('Approved', 'Rejected'):
        abort(400)
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        claim_row = conn.execute('SELECT * FROM claims WHERE id = ?', (claim_id,)).fetchone()
        if not claim_row:
            abort(404)
        if claim_row['status'] != 'Pending':
            abort(400, 'This claim has already been reviewed.')
        conn.execute('UPDATE claims SET status = ? WHERE id = ?', (decision, claim_id))
        if decision == 'Approved':
            conn.execute("UPDATE claims SET status = 'Rejected' WHERE item_id = ? AND status = 'Pending'", (claim_row['item_id'],))
            conn.execute("UPDATE items SET status = 'Claimed' WHERE id = ?", (claim_row['item_id'],))
        elif not conn.execute("SELECT 1 FROM claims WHERE item_id = ? AND status = 'Pending'", (claim_row['item_id'],)).fetchone():
            conn.execute("UPDATE items SET status = 'Open' WHERE id = ?", (claim_row['item_id'],))
    flash('Claim reviewed.')
    return redirect(url_for('dashboard', tab='claims'))


@app.post('/items/<int:item_id>/returned')
@login_required('admin')
def mark_returned(item_id):
    with db.get_connection() as conn:
        result = conn.execute("UPDATE items SET status = 'Returned' WHERE id = ? AND status = 'Claimed'", (item_id,))
        if not result.rowcount:
            abort(400, 'Only claimed items can be marked returned.')
    flash('Item marked as returned.')
    return redirect(url_for('dashboard', tab='returned'))


if __name__ == '__main__':
    app.run(port=5000)
