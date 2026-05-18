import os
import re
import io
import json
import random
import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, render_template, request, redirect, url_for, abort, send_file, flash, jsonify, get_flashed_messages, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///instance/books.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')

# In production (Render sets RENDER=true, or DATABASE_URL starts with postgres),
# enforce secure cookies and HTTPS. Disabled for local HTTP development.
_is_prod = bool(
    os.environ.get('RENDER')
    or os.environ.get('DATABASE_URL', '').startswith('postgres')
)
app.config['SESSION_COOKIE_SECURE'] = _is_prod
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)
migrate = Migrate()
csrf = CSRFProtect()
talisman = Talisman()
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access your library.'
limiter = Limiter(key_func=get_remote_address, storage_uri='memory://', default_limits=[])

# Valid username pattern: letters, numbers, underscores, 3–30 chars
USERNAME_RE = re.compile(r'^[A-Za-z0-9_]{3,30}$')

# The one fixed admin username — admin access is tied to this name, not the DB flag
ADMIN_USERNAME = 'Admin'

SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What city were you born in?",
    "What was the name of your primary school?",
    "What is your favourite book?",
    "What was the street you grew up on?",
    "What was your childhood nickname?",
    "What was the make of your first car?",
    "What is your mother's maiden name?",
]


# ─── Models ──────────────────────────────────────────────────

class User(db.Model, UserMixin):
    id               = db.Column(db.Integer, primary_key=True)
    username         = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash    = db.Column(db.String(256), nullable=False)
    is_admin         = db.Column(db.Boolean, default=False, nullable=False)
    # Billing stubs — unused now, ready for Stripe integration later
    plan             = db.Column(db.String(20), default='free', nullable=False)
    stripe_customer_id = db.Column(db.String(120), nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    avatar               = db.Column(db.String(120), nullable=True)
    is_active            = db.Column(db.Boolean, default=True, nullable=False)
    security_question    = db.Column(db.String(200), nullable=True)
    security_answer_hash = db.Column(db.String(256), nullable=True)
    books                = db.relationship('Book', backref='owner', lazy=True)
    quotes           = db.relationship('Quote', backref='reader', lazy=True)


class Book(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(200), nullable=False)
    author     = db.Column(db.String(200), nullable=False)
    rating     = db.Column(db.Integer, nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    quotes     = db.relationship('Quote', backref='book', lazy=True, cascade='all, delete-orphan')


class Quote(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    text       = db.Column(db.String(2000), nullable=False)
    page_ref   = db.Column(db.String(20), nullable=True)
    book_id    = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# ─── Extension Init ──────────────────────────────────────────

migrate.init_app(app, db)
csrf.init_app(app)
talisman.init_app(app, content_security_policy=None, force_https=_is_prod)
login_manager.init_app(app)
limiter.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Fallback: create missing tables so the app can respond even if
# the migration startup hook didn't run (safe for simple schemas).
# Skip during `flask db` commands so Alembic can diff correctly.
import sys as _sys
_db_cli = len(_sys.argv) > 1 and _sys.argv[1] == 'db'
if not _db_cli:
    try:
        from sqlalchemy import inspect as sa_inspect
        with app.app_context():
            _inspector = sa_inspect(db.engine)
            _tables = _inspector.get_table_names()
            if 'user' not in _tables or 'book' not in _tables:
                try:
                    app.logger.info('Tables missing — creating via db.create_all()')
                    db.create_all()
                except Exception:
                    app.logger.exception('Failed to create tables via db.create_all()')
    except Exception:
        pass


# ─── Admin Helpers ──────────────────────────────────────────

def admin_required(f):
    """Decorator: require the current user to be logged-in with the admin username."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if current_user.username != ADMIN_USERNAME:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.before_request
def check_user_active():
    """Immediately log out users whose accounts have been disabled by an admin."""
    if current_user.is_authenticated and not current_user.is_active:
        logout_user()
        flash('Your account has been disabled. Please contact an administrator.', 'login_error')
        return redirect(url_for('login'))


# ─── Auth Routes ─────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('authors_page'))
    error = None
    if request.method == 'POST':
        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        confirm    = request.form.get('confirm', '')
        security_q = request.form.get('security_question', '').strip()
        security_a = request.form.get('security_answer', '').strip().lower()
        if not USERNAME_RE.match(username):
            error = 'Username must be 3–30 characters: letters, numbers, and underscores only.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif not security_q or security_q not in SECURITY_QUESTIONS:
            error = 'Please select a security question.'
        elif len(security_a) < 2:
            error = 'Security answer must be at least 2 characters.'
        elif User.query.filter_by(username=username).first():
            error = 'That username is already taken.'
        else:
            user = User(
                username=username,
                password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
                security_question=security_q,
                security_answer_hash=generate_password_hash(security_a, method='pbkdf2:sha256'),
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('authors_page'))
    return render_template('register.html', error=error, security_questions=SECURITY_QUESTIONS)


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        if current_user.username == ADMIN_USERNAME:
            return redirect(url_for('admin_users'))
        return redirect(url_for('authors_page'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                error = 'Your account has been disabled. Please contact an administrator.'
            else:
                login_user(user)
                next_url = request.form.get('next', '').strip()
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                if user.username == ADMIN_USERNAME:
                    return redirect(url_for('admin_users'))
                return redirect(url_for('authors_page'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error, next=request.args.get('next', ''))


@app.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def forgot_password():
    reset_uid = session.get('_reset_uid')
    reset_ok  = session.get('_reset_ok')

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'lookup':
            username = request.form.get('username', '').strip()
            user = User.query.filter_by(username=username).first()
            if user and user.security_question:
                session['_reset_uid'] = user.id
                session.pop('_reset_ok', None)
            else:
                flash('No security question is set for that username.', 'fp_error')
            return redirect(url_for('forgot_password'))

        elif action == 'answer' and reset_uid:
            user = User.query.get(reset_uid)
            answer = request.form.get('security_answer', '').strip().lower()
            if user and user.security_answer_hash and check_password_hash(user.security_answer_hash, answer):
                session['_reset_ok'] = True
            else:
                flash('Incorrect answer. Please try again.', 'fp_error')
            return redirect(url_for('forgot_password'))

        elif action == 'reset' and reset_uid and reset_ok:
            user = User.query.get(reset_uid)
            new_pw     = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if len(new_pw) < 8:
                flash('Password must be at least 8 characters.', 'fp_error')
            elif new_pw != confirm_pw:
                flash('Passwords do not match.', 'fp_error')
            elif user:
                user.password_hash = generate_password_hash(new_pw, method='pbkdf2:sha256')
                db.session.commit()
                session.pop('_reset_uid', None)
                session.pop('_reset_ok', None)
                flash('Password reset successfully. Please sign in.', 'pw_success')
                return redirect(url_for('login'))
            return redirect(url_for('forgot_password'))

        else:
            session.pop('_reset_uid', None)
            session.pop('_reset_ok', None)
            return redirect(url_for('forgot_password'))

    # GET — determine step
    step = 1
    security_question = None
    if reset_uid and reset_ok:
        step = 3
    elif reset_uid:
        user = User.query.get(reset_uid)
        if user and user.security_question:
            step = 2
            security_question = user.security_question
        else:
            session.pop('_reset_uid', None)
            step = 1

    fp_errors = [m for c, m in get_flashed_messages(with_categories=True) if c == 'fp_error']
    return render_template('forgot_password.html', step=step,
                           security_question=security_question,
                           fp_errors=fp_errors)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


_AVATAR_ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB


@app.route('/settings/avatar', methods=['POST'])
@login_required
def upload_avatar():
    f = request.files.get('avatar')
    if not f or f.filename == '':
        return redirect(url_for('authors_page'))

    raw = f.read(_MAX_AVATAR_BYTES + 1)
    if len(raw) > _MAX_AVATAR_BYTES:
        flash('Image must be under 2 MB.', 'avatar_error')
        return redirect(url_for('authors_page'))

    # Validate with Pillow and re-encode to strip EXIF / malicious data
    try:
        src = Image.open(io.BytesIO(raw))
        src.load()
        fmt = src.format or 'PNG'
        if fmt not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
            raise ValueError('unsupported format')
        # Normalise palette/RGBA → RGB for JPEG, keep RGBA for PNG
        if fmt == 'JPEG' and src.mode != 'RGB':
            src = src.convert('RGB')
        # Resize if larger than 400×400 to save space
        src.thumbnail((400, 400))
        ext = 'jpg' if fmt == 'JPEG' else fmt.lower()
        out = io.BytesIO()
        save_kw = {'quality': 85, 'optimize': True} if fmt == 'JPEG' else {}
        src.save(out, format=fmt, **save_kw)
        data = out.getvalue()
    except Exception:
        flash('Could not process image. Please upload a valid JPEG, PNG, GIF, or WEBP.', 'avatar_error')
        return redirect(url_for('authors_page'))

    avatars_dir = os.path.join(app.root_path, 'static', 'avatars')
    os.makedirs(avatars_dir, exist_ok=True)

    # Remove any previously stored avatar for this user
    if current_user.avatar:
        old_path = os.path.join(avatars_dir, current_user.avatar)
        if os.path.isfile(old_path):
            os.remove(old_path)

    filename = f'{current_user.id}.{ext}'
    with open(os.path.join(avatars_dir, filename), 'wb') as fh:
        fh.write(data)

    current_user.avatar = filename
    db.session.commit()
    return redirect(url_for('authors_page'))


@app.route('/settings/password', methods=['GET', 'POST'])
@login_required
def change_password():
    error = None
    if request.method == 'POST':
        current_pw  = request.form.get('current_password', '')
        new_pw      = request.form.get('new_password', '')
        confirm_pw  = request.form.get('confirm_password', '')
        if not check_password_hash(current_user.password_hash, current_pw):
            error = 'Current password is incorrect.'
        elif len(new_pw) < 8:
            error = 'New password must be at least 8 characters.'
        elif new_pw != confirm_pw:
            error = 'New passwords do not match.'
        else:
            current_user.password_hash = generate_password_hash(new_pw, method='pbkdf2:sha256')
            db.session.commit()
            logout_user()
            flash('Password updated. Please sign in with your new password.', 'pw_success')
            return redirect(url_for('login'))
    return render_template('settings.html', error=error)


@app.route('/settings/security-question', methods=['POST'])
@login_required
def set_security_question():
    question = request.form.get('security_question', '').strip()
    answer   = request.form.get('security_answer', '').strip().lower()
    password = request.form.get('sq_password', '')
    if not check_password_hash(current_user.password_hash, password):
        flash('Incorrect password.', 'sq_error')
    elif question not in SECURITY_QUESTIONS:
        flash('Please select a valid security question.', 'sq_error')
    elif len(answer) < 2:
        flash('Answer must be at least 2 characters.', 'sq_error')
    else:
        current_user.security_question    = question
        current_user.security_answer_hash = generate_password_hash(answer, method='pbkdf2:sha256')
        db.session.commit()
        flash('Security question saved.', 'sq_success')
    return redirect(url_for('change_password'))


# ─── Ranking Helpers ─────────────────────────────────────────

def _since_date(period):
    """Return a cutoff datetime for a period string, or None for all time."""
    if period == 'month':
        return datetime.utcnow() - timedelta(days=30)
    return None


def top_authors(user_id, since=None, limit=5):
    query = Book.query.filter_by(user_id=user_id)
    if since:
        query = query.filter(Book.date_added >= since)
    books = query.all()
    author_map = {}
    for b in books:
        entry = author_map.setdefault(
            b.author, {'name': b.author, 'book_count': 0, 'rating_sum': 0}
        )
        entry['book_count'] += 1
        entry['rating_sum'] += b.rating
    result = []
    for a in author_map.values():
        avg = round(a['rating_sum'] / a['book_count'], 2) if a['book_count'] else 0
        result.append({'name': a['name'], 'avg_rating': avg, 'book_count': a['book_count']})
    result.sort(key=lambda x: (-x['avg_rating'], -x['book_count'], x['name']))
    return result[:limit]


def top_books(user_id, since=None, limit=5):
    query = (
        Book.query
        .filter_by(user_id=user_id)
        .order_by(Book.rating.desc(), Book.date_added.desc())
    )
    if since:
        query = query.filter(Book.date_added >= since)
    books = query.limit(limit).all()
    return [{'title': b.title, 'author': b.author, 'rating': b.rating} for b in books]


# ─── PNG Share Card Generation ───────────────────────────────

def generate_share_card(username, items, list_type, period_label):
    """Build and return an 800×500 PNG share card as a BytesIO buffer."""
    W, H   = 800, 500
    BG     = (18, 20, 40)
    ACCENT = (108, 99, 255)
    WHITE  = (255, 255, 255)
    MUTED  = (160, 165, 200)

    img  = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Accent gradient strip at top
    for y in range(6):
        shade = tuple(int(c * (1 - y * 0.12)) for c in ACCENT)
        draw.rectangle([(0, y), (W, y + 1)], fill=shade)

    # Fonts — requires Pillow ≥10.1 for the size keyword argument
    try:
        font_title = ImageFont.load_default(size=30)
        font_sub   = ImageFont.load_default(size=15)
        font_item  = ImageFont.load_default(size=19)
        font_small = ImageFont.load_default(size=13)
    except TypeError:
        # Older Pillow fallback — text will be small but functional
        font_title = font_sub = font_item = font_small = ImageFont.load_default()

    # Header
    draw.text((40, 28), f"{username}'s Top {len(items)} {list_type}", fill=WHITE, font=font_title)
    draw.text((40, 68), period_label, fill=MUTED, font=font_sub)
    draw.rectangle([(40, 93), (W - 40, 95)], fill=ACCENT)

    # Ranked items
    y = 112
    for i, item in enumerate(items, 1):
        bx, by = 40, y + 2
        draw.ellipse([(bx, by), (bx + 28, by + 28)], fill=ACCENT)
        badge_num = str(i)
        bw = len(badge_num) * 7
        draw.text((bx + (28 - bw) // 2, by + 6), badge_num, fill=WHITE, font=font_small)

        if list_type == 'Authors':
            name_line = item['name'][:52]
            stars = '★' * round(item['avg_rating']) + '☆' * (5 - round(item['avg_rating']))
            sub_line  = f"{stars}  {item['avg_rating']:.1f}  ·  {item['book_count']} book{'s' if item['book_count'] != 1 else ''}"
        else:
            name_line = item['title'][:52]
            sub_line  = f"by {item['author'][:30]}   {'★' * item['rating']}{'☆' * (5 - item['rating'])}"

        draw.text((82, y + 1), name_line, fill=WHITE, font=font_item)
        draw.text((82, y + 24), sub_line,  fill=MUTED, font=font_small)
        y += 64

    # Footer
    app_url = os.environ.get('APP_URL', 'booktrackerapp.onrender.com')
    draw.text((40, H - 26), app_url, fill=MUTED, font=font_small)
    draw.rectangle([(W - 138, H - 30), (W - 30, H - 12)], fill=ACCENT)
    draw.text((W - 134, H - 29), 'Book Tracker', fill=WHITE, font=font_small)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


# ─── Public Share Routes ─────────────────────────────────────

@app.route('/share/<username>')
def share_page(username):
    user = User.query.filter_by(username=username).first_or_404()
    period = request.args.get('period', 'all')
    if period not in ('month', 'all'):
        period = 'all'
    since   = _since_date(period)
    authors = top_authors(user.id, since=since, limit=5)
    books   = top_books(user.id, since=since, limit=5)
    return render_template('share.html', profile_user=user, authors=authors, books=books, period=period)


@app.route('/share/<username>/card.png')
@limiter.limit('30 per minute')
def share_card(username):
    user = User.query.filter_by(username=username).first_or_404()
    list_type = request.args.get('type', 'authors').lower()
    period    = request.args.get('period', 'all')
    if period not in ('month', 'all'):
        period = 'all'
    try:
        limit = min(max(int(request.args.get('limit', 5)), 1), 10)
    except (ValueError, TypeError):
        limit = 5
    since        = _since_date(period)
    period_label = 'Past Month' if period == 'month' else 'All Time'

    if list_type == 'books':
        items = top_books(user.id, since=since, limit=limit)
        label = 'Books'
    else:
        items = top_authors(user.id, since=since, limit=limit)
        label = 'Authors'

    buf = generate_share_card(user.username, items, label, period_label)
    return send_file(
        buf,
        mimetype='image/png',
        as_attachment=True,
        download_name=f"{username}_top_{list_type}_{period}.png",
    )


# ─── App Routes ──────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('authors_page'))
    return redirect(url_for('login'))


@app.route('/authors')
@login_required
def authors_page():
    books = Book.query.filter_by(user_id=current_user.id).all()
    author_map = {}
    total_books = 0
    total_rating_sum = 0
    total_rating_count = 0
    for b in books:
        total_books += 1
        total_rating_sum += (b.rating or 0)
        total_rating_count += 1
        entry = author_map.setdefault(
            b.author, {'name': b.author, 'bookCount': 0, 'titles': [], 'ratingSum': 0}
        )
        entry['bookCount'] += 1
        entry['titles'].append(b.title)
        entry['ratingSum'] += (b.rating or 0)

    authors = []
    for a in author_map.values():
        avg = round((a['ratingSum'] / a['bookCount']) if a['bookCount'] else 0, 2)
        authors.append({'name': a['name'], 'bookCount': a['bookCount'], 'titles': a['titles'], 'avgRating': avg})

    overall_avg = round((total_rating_sum / total_rating_count), 2) if total_rating_count else 0
    most_active = max(authors, key=lambda x: x['bookCount'])['name'] if authors else ''
    authors = sorted(authors, key=lambda x: x['name'] or '')

    return render_template(
        'index.html',
        authors=authors,
        total_books=total_books,
        overall_avg=overall_avg,
        most_active=most_active,
    )


@app.route('/author/<author>')
@login_required
def author_books(author):
    books = Book.query.filter_by(author=author, user_id=current_user.id).all()
    return render_template('author_books.html', author=author, books=books, author_count=len(books))


@app.route('/cover')
def cover():
    return render_template('cover.html')


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    book = Book.query.get_or_404(id)
    if book.user_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        book.title  = request.form['title']
        book.author = request.form['author']
        book.rating = int(request.form['rating'])
        db.session.commit()
        return redirect(url_for('authors_page'))
    return render_template('edit_book.html', book=book)


@app.route('/delete/<int:id>')
@login_required
def delete(id):
    book = Book.query.get_or_404(id)
    if book.user_id != current_user.id:
        abort(403)
    db.session.delete(book)
    db.session.commit()
    return redirect(url_for('authors_page'))


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        new_book = Book(
            title=request.form['title'],
            author=request.form['author'],
            rating=int(request.form['rating']),
            user_id=current_user.id,
        )
        db.session.add(new_book)
        db.session.commit()
        next_url = request.form.get('next') or request.referrer or url_for('authors_page')
        if not isinstance(next_url, str) or not next_url.startswith('/'):
            next_url = url_for('authors_page')
        sep = '&' if '?' in next_url else '?'
        return redirect(next_url + sep + 'added=1')
    next_param = request.args.get('next') or request.referrer or url_for('authors_page')
    return render_template('add_book.html', next=next_param)


# ─── Quotes Routes ───────────────────────────────────────────

@app.route('/quotes/add', methods=['POST'])
@login_required
def add_quote():
    text = request.form.get('text', '').strip()
    page_ref = request.form.get('page_ref', '').strip() or None
    try:
        book_id = int(request.form.get('book_id', 0))
    except (ValueError, TypeError):
        abort(400)
    if not text or len(text) > 2000:
        abort(400)
    book = Book.query.get_or_404(book_id)
    if book.user_id != current_user.id:
        abort(403)
    quote = Quote(text=text, page_ref=page_ref, book_id=book_id, user_id=current_user.id)
    db.session.add(quote)
    db.session.commit()
    return redirect(url_for('author_books', author=book.author))


@app.route('/quotes/<int:quote_id>/delete', methods=['POST'])
@login_required
def delete_quote(quote_id):
    quote = Quote.query.get_or_404(quote_id)
    if quote.user_id != current_user.id:
        abort(403)
    db.session.delete(quote)
    db.session.commit()
    return redirect(url_for('quotes_page'))


@app.route('/quotes/<int:quote_id>/edit', methods=['POST'])
@login_required
def edit_quote(quote_id):
    quote = Quote.query.get_or_404(quote_id)
    if quote.user_id != current_user.id:
        abort(403)
    text = request.form.get('text', '').strip()
    page_ref = request.form.get('page_ref', '').strip() or None
    if not text or len(text) > 2000:
        abort(400)
    quote.text = text
    quote.page_ref = page_ref
    db.session.commit()
    return redirect(url_for('quotes_page'))


@app.route('/api/quotes/random')
@login_required
def random_quote():
    quotes = Quote.query.filter_by(user_id=current_user.id).all()
    if not quotes:
        return ('', 204)
    q = random.choice(quotes)
    return jsonify({
        'id': q.id,
        'text': q.text,
        'page_ref': q.page_ref,
        'book_title': q.book.title,
        'author': q.book.author,
    })


@app.route('/quotes')
@login_required
def quotes_page():
    quotes = Quote.query.filter_by(user_id=current_user.id).order_by(Quote.date_added.desc()).all()
    # Group by book, ordered by most-recently-quoted book first
    seen = {}
    groups = []
    for q in quotes:
        if q.book_id not in seen:
            seen[q.book_id] = len(groups)
            groups.append({'book': q.book, 'quotes': []})
        groups[seen[q.book_id]]['quotes'].append(q)
    return render_template('quotes.html', groups=groups, quote_count=len(quotes))


# ─── Admin Routes ────────────────────────────────────────────

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.asc()).all()
    non_admin = [u for u in users if u.username != ADMIN_USERNAME]

    # ── KPI counts ──────────────────────────────────────────
    total_users    = len(users)
    active_users   = sum(1 for u in users if u.is_active)
    disabled_users = total_users - active_users
    total_books    = Book.query.count()
    total_quotes   = Quote.query.count()

    most_active = max(non_admin, key=lambda u: len(u.books), default=None)
    newest_user = max(non_admin, key=lambda u: u.created_at, default=None)

    # ── Books added per month (last 12 months) ───────────────
    now = datetime.utcnow()
    month_keys   = []
    month_labels = []
    for i in range(11, -1, -1):
        # step back i months from current
        y = now.year + (now.month - 1 - i) // 12
        m = (now.month - 1 - i) % 12 + 1
        month_keys.append(f'{y}-{m:02d}')
        month_labels.append(datetime(y, m, 1).strftime('%b %y'))

    counts = defaultdict(int)
    for b in Book.query.all():
        if b.date_added:
            counts[b.date_added.strftime('%Y-%m')] += 1
    books_per_month = json.dumps([counts.get(k, 0) for k in month_keys])
    month_labels_js = json.dumps(month_labels)

    # ── Books per user (non-admin only) ─────────────────────
    users_labels_js = json.dumps([u.username for u in non_admin])
    users_books_js  = json.dumps([len(u.books) for u in non_admin])

    # ── Top 5 authors across all users ──────────────────────
    author_counts  = defaultdict(lambda: {'count': 0, 'rating_sum': 0})
    for b in Book.query.all():
        author_counts[b.author]['count']      += 1
        author_counts[b.author]['rating_sum'] += b.rating
    top_authors_global = sorted(
        [{'name': a, 'count': v['count'],
          'avg_rating': round(v['rating_sum'] / v['count'], 1)}
         for a, v in author_counts.items()],
        key=lambda x: (-x['count'], -x['avg_rating'])
    )[:5]

    # ── Top 5 books across all users ────────────────────────
    book_agg = defaultdict(lambda: {'count': 0, 'rating_sum': 0, 'author': ''})
    for b in Book.query.all():
        key = b.title
        book_agg[key]['count']      += 1
        book_agg[key]['rating_sum'] += b.rating
        book_agg[key]['author']      = b.author
    top_books_global = sorted(
        [{'title': t, 'author': v['author'], 'count': v['count'],
          'avg_rating': round(v['rating_sum'] / v['count'], 1)}
         for t, v in book_agg.items()],
        key=lambda x: (-x['avg_rating'], -x['count'])
    )[:5]

    flash_errors   = get_flashed_messages(category_filter=['admin_error'])
    flash_messages = get_flashed_messages(category_filter=['admin_success'])
    return render_template(
        'admin_users.html',
        users=users,
        total_users=total_users,
        active_users=active_users,
        disabled_users=disabled_users,
        total_books=total_books,
        total_quotes=total_quotes,
        most_active=most_active,
        newest_user=newest_user,
        month_labels_js=month_labels_js,
        books_per_month=books_per_month,
        users_labels_js=users_labels_js,
        users_books_js=users_books_js,
        top_authors_global=top_authors_global,
        top_books_global=top_books_global,
        flash_errors=flash_errors,
        flash_messages=flash_messages,
    )


@app.route('/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def admin_toggle_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot disable your own account.', 'admin_error')
        return redirect(url_for('admin_users'))
    user.is_active = not user.is_active
    db.session.commit()
    action = 'enabled' if user.is_active else 'disabled'
    flash(f'Account for "{user.username}" has been {action}.', 'admin_success')
    return redirect(url_for('admin_users'))



@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'admin_error')
        return redirect(url_for('admin_users'))
    # Cascade-delete quotes then books, then user
    for q in Quote.query.filter_by(user_id=user.id).all():
        db.session.delete(q)
    for b in Book.query.filter_by(user_id=user.id).all():
        db.session.delete(b)
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" and all their data have been deleted.', 'admin_success')
    return redirect(url_for('admin_users'))


if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite') and not _is_prod:
        with app.app_context():
            db.create_all()
    app.run(debug=debug, host='0.0.0.0', port=port)