import os
import re
import io
import random
import math
import secrets
import sys
from datetime import datetime
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, render_template, request, redirect, url_for, abort, send_file, send_from_directory, flash, jsonify, get_flashed_messages, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as sa
from sqlalchemy.orm import selectinload
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Media service lives under app/services/ (no app/__init__.py so this app.py
# module is not shadowed — gunicorn app:app / FLASK_APP=app.py keep working).
_APP_SERVICES_PARENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app')
if _APP_SERVICES_PARENT not in sys.path:
    sys.path.insert(0, _APP_SERVICES_PARENT)
from services.media_service import MediaService, MediaValidationError  # noqa: E402
from services.reading_service import ReadingService  # noqa: E402
from services.statistics_service import StatisticsService  # noqa: E402
from services.share_engine import ShareEngine, ShareFormat  # noqa: E402
from services.book_metadata_service import BookMetadataService  # noqa: E402
from domain.reading_status import ReadingStatus  # noqa: E402
from config.media_settings import MediaSettings  # noqa: E402
from utils import has_rating, since_date, safe_next_url  # noqa: E402

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_SQLITE = 'sqlite:///' + os.path.join(_BASE_DIR, 'instance', 'books.db').replace('\\', '/')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', _DEFAULT_SQLITE)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')

# Centralized media / upload settings (override via env or Flask config)
_media_settings = MediaSettings.from_mapping({
    'UPLOAD_ROOT': os.environ.get('UPLOAD_ROOT'),
    'MEDIA_COVER_MAX_BYTES': os.environ.get('MEDIA_COVER_MAX_BYTES'),
    'MEDIA_COVER_MAX_EDGE': os.environ.get('MEDIA_COVER_MAX_EDGE'),
    'MEDIA_AVATAR_MAX_BYTES': os.environ.get('MEDIA_AVATAR_MAX_BYTES'),
})
app.config['UPLOAD_ROOT'] = str(_media_settings.upload_root)
app.config['MEDIA_COVER_MAX_BYTES'] = _media_settings.cover_max_bytes
app.config['MEDIA_AVATAR_MAX_BYTES'] = _media_settings.avatar_max_bytes
app.config['MAX_CONTENT_LENGTH'] = _media_settings.cover_max_bytes

media_service = MediaService(settings=_media_settings)
reading_service = ReadingService()
statistics_service = StatisticsService()
book_metadata_service = BookMetadataService()
share_engine = ShareEngine(
    cover_resolver=media_service.resolve_book_cover_path,
)

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
    avatar               = db.Column(db.Text, nullable=True)
    is_active            = db.Column(db.Boolean, default=True, nullable=False)
    security_question    = db.Column(db.String(200), nullable=True)
    security_answer_hash = db.Column(db.String(256), nullable=True)
    books                = db.relationship('Book', backref='owner', lazy=True)
    quotes           = db.relationship('Quote', backref='reader', lazy=True)
    reading_goals    = db.relationship(
        'ReadingGoal', backref='user', lazy=True, cascade='all, delete-orphan'
    )


class Book(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(200), nullable=False)
    author         = db.Column(db.String(200), nullable=False)
    rating         = db.Column(db.Integer, nullable=False)
    reading_status = db.Column(
        db.String(20),
        nullable=False,
        default=ReadingStatus.FINISHED,
        server_default=ReadingStatus.FINISHED,
    )
    is_wild        = db.Column(db.Boolean, nullable=False, default=False)
    cover_filename = db.Column(db.String(255), nullable=True)
    started_reading_at  = db.Column(db.Date, nullable=True)
    finished_reading_at = db.Column(db.Date, nullable=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    date_added     = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    quotes         = db.relationship('Quote', backref='book', lazy=True, cascade='all, delete-orphan')

class Quote(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    text       = db.Column(db.String(2000), nullable=False)
    page_ref   = db.Column(db.String(20), nullable=True)
    book_id    = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class ReadingGoal(db.Model):
    """One annual reading target per user per calendar year."""
    __tablename__ = 'reading_goal'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'year', name='uq_reading_goal_user_year'),
    )

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    year         = db.Column(db.Integer, nullable=False)
    target_count = db.Column(db.Integer, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


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
_db_cli = len(sys.argv) > 1 and sys.argv[1] == 'db'
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

    import base64
    mime_map = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'GIF': 'image/gif', 'WEBP': 'image/webp'}
    current_user.avatar = f'data:{mime_map[fmt]};base64,{base64.b64encode(data).decode()}'
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
    return since_date(period)


def _parse_status_and_rating(form):
    """Validate reading_status + rating from a form via ReadingService."""
    return reading_service.parse_status_and_rating(form)


def _parse_timeline_dates(form, status):
    """Parse/validate timeline dates via ReadingService."""
    return reading_service.parse_timeline_dates(form, status)


def _has_rating(book_or_rating):
    """True when a stored rating is a real 1–5 score (not the unrated sentinel)."""
    return has_rating(book_or_rating)


def _status_counts(books):
    """Return a dict of reading_status → count for KPI cards."""
    return statistics_service.status_counts(books)


def top_authors(user_id, since=None, limit=5):
    books = statistics_service.fetch_public_books_for_user(Book, user_id, since=since)
    return statistics_service.top_authors(books, limit=limit)


def top_books(user_id, since=None, limit=5):
    books = statistics_service.fetch_top_books_for_user(
        Book, user_id, since=since, limit=limit
    )
    return statistics_service.top_books(books, limit=limit)


# ─── PNG Share Card Generation ───────────────────────────────

def generate_share_card(username, items, list_type, period_label):
    """Build and return a 1080x1920 portrait PNG share card matching the app's colour scheme."""
    W, H = 1080, 1920

    # ── App colour palette (mirrors CSS variables) ────────────────────────
    PRIMARY = (108,  99, 255)   # --color-primary  #6C63FF
    ACCENT  = ( 34, 197,  94)   # --color-accent   #22C55E
    RATING  = (246, 200,  95)   # --color-rating   #F6C85F
    TEXT1   = ( 17,  24,  39)   # --color-text-primary  #111827
    TEXT2   = (107, 114, 128)   # --color-text-secondary #6B7280
    BORDER  = (229, 231, 235)   # --color-border   #E5E7EB
    BG      = (248, 250, 252)   # --color-bg       #F8FAFC
    WHITE   = (255, 255, 255)

    badge_col = ACCENT if list_type == 'Books' else PRIMARY

    # ── Background ────────────────────────────────────────────────────────
    img  = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── Top accent bar ────────────────────────────────────────────────────
    draw.rectangle([(0, 0), (W, 8)], fill=PRIMARY)

    # ── Font loader ───────────────────────────────────────────────────────
    BOLD = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
    ]
    REGU = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        'C:/Windows/Fonts/arial.ttf',
    ]

    def _font(paths, size):
        for p in paths:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
        return ImageFont.load_default(size=size)

    fn_username = _font(BOLD, 72)
    fn_listtype = _font(BOLD, 50)
    fn_period   = _font(REGU, 26)
    fn_rank     = _font(BOLD, 38)
    fn_meta     = _font(REGU, 26)
    fn_badge    = _font(BOLD, 22)
    fn_brand    = _font(BOLD, 26)
    fn_footer   = _font(REGU, 20)
    fn_cta      = _font(REGU, 22)

    # ── Header ────────────────────────────────────────────────────────────
    draw.text((60,  52), f"{username}'s",                 fill=TEXT1,   font=fn_username)
    draw.text((62, 158), f"Top {len(items)} {list_type}", fill=PRIMARY, font=fn_listtype)
    draw.text((62, 232), period_label,                    fill=TEXT2,   font=fn_period)
    draw.rectangle([(60, 295), (W - 60, 297)],            fill=BORDER)

    # ── Star polygon helper ───────────────────────────────────────────────
    def _star_pts(cx, cy, outer_r, inner_r):
        pts = []
        for k in range(10):
            angle = math.radians(-90 + k * 36)
            r = outer_r if k % 2 == 0 else inner_r
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        return pts

    # ── Ranked rows ───────────────────────────────────────────────────────
    ROW_Y0 = 320
    ROW_H  = (H - ROW_Y0 - 220) // max(len(items), 1)

    for i, item in enumerate(items, 1):
        ry = ROW_Y0 + (i - 1) * ROW_H

        # Badge circle (single rank indicator — no duplicate numeral)
        draw.ellipse([(60, ry + 80), (122, ry + 142)], fill=badge_col)
        num_str = str(i)
        nw = int(draw.textlength(num_str, font=fn_badge))
        draw.text((60 + (62 - nw) // 2, ry + 101), num_str, fill=WHITE, font=fn_badge)

        # Text content
        if list_type == 'Authors':
            line1 = item['name'][:38]
            sub   = f"{item['book_count']} book{'s' if item['book_count'] != 1 else ''} · {item['avg_rating']:.1f} avg"
            score = f"{item['avg_rating']:.1f}"
        else:
            line1 = item['title'][:38]
            sub   = f"by {item['author'][:42]}"
            if item.get('is_wild'):
                sub += ' · WILD'
            score = str(item['rating'])

        draw.text((144, ry + 76),  line1, fill=TEXT1, font=fn_rank)
        draw.text((144, ry + 132), sub,   fill=TEXT2, font=fn_meta)

        # Right-aligned rating: score number + gold drawn star
        score_w = int(draw.textlength(score, font=fn_rank))
        star_r  = 16
        total_w = score_w + 12 + star_r * 2
        rx0     = W - 60 - total_w
        draw.text((rx0, ry + 76), score, fill=TEXT1, font=fn_rank)
        star_cx = rx0 + score_w + 12 + star_r
        star_cy = ry + 76 + 21
        draw.polygon(_star_pts(star_cx, star_cy, star_r, 7), fill=RATING)

        # Row separator
        if i < len(items):
            draw.rectangle(
                [(60, ry + ROW_H - 1), (W - 60, ry + ROW_H)],
                fill=BORDER,
            )

    # ── Footer ────────────────────────────────────────────────────────────
    FY = H - 220
    draw.rectangle([(0, FY), (W, FY + 1)], fill=BORDER)
    draw.rectangle([(0, FY + 1), (W, H)],  fill=WHITE)
    draw.text((60, FY + 40), 'Kwalitec Library',
              fill=PRIMARY, font=fn_brand)
    draw.text((60, FY + 82), 'https://personal-book-tracker-8xij.onrender.com/login',
              fill=TEXT2, font=fn_footer)
    cta   = 'Track Your Reading'
    cta_w = int(draw.textlength(cta, font=fn_cta))
    draw.rounded_rectangle(
        [(W - cta_w - 80, FY + 36), (W - 60, FY + 76)],
        radius=14, fill=PRIMARY,
    )
    draw.text((W - cta_w - 60, FY + 46), cta, fill=WHITE, font=fn_cta)

    # ── Export ────────────────────────────────────────────────────────────
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


# ─── My Reading Year ─────────────────────────────────────────

def _load_reading_year(user, year: int):
    """Build narrative payload for one user/year from existing rows only."""
    books = (
        Book.query
        .filter_by(user_id=user.id)
        .options(selectinload(Book.quotes))
        .all()
    )
    quotes = Quote.query.filter_by(user_id=user.id).all()
    goals = ReadingGoal.query.filter_by(user_id=user.id).all()
    goal = next((g for g in goals if g.year == year), None)
    available = statistics_service.available_reading_years(books, goals)
    if year not in available:
        available = sorted(set(available) | {year}, reverse=True)
    return statistics_service.reading_year(
        books,
        quotes,
        goal,
        reading_service,
        year=year,
        username=user.username,
        available_years=available,
    )


@app.route('/reading-year')
@app.route('/reading-year/<int:year>')
@login_required
def reading_year_page(year=None):
    """Narrative My Reading Year experience (Spotify Wrapped-style)."""
    if year is None:
        year = datetime.utcnow().year
    if year < 2000 or year > datetime.utcnow().year + 1:
        abort(404)
    year_data = _load_reading_year(current_user, year)
    return render_template(
        'reading_year.html',
        year_data=year_data,
        share_formats=list(ShareFormat.ALL),
        ReadingStatus=ReadingStatus,
    )


@app.route('/reading-year/<int:year>/export/<slide_id>.png')
@login_required
@limiter.limit('30 per minute')
def reading_year_export(year, slide_id):
    """Export one Reading Year slide via ShareEngine (story / portrait / square)."""
    if year < 2000 or year > datetime.utcnow().year + 1:
        abort(404)
    if slide_id not in StatisticsService.SLIDE_IDS:
        abort(404)
    fmt = (request.args.get('format') or ShareFormat.STORY).lower()
    if not ShareFormat.is_valid(fmt):
        fmt = ShareFormat.STORY
    year_data = _load_reading_year(current_user, year)
    buf = share_engine.render_reading_year_slide(slide_id, year_data, format_name=fmt)
    return send_file(
        buf,
        mimetype='image/png',
        as_attachment=True,
        download_name=f"{current_user.username}_reading_year_{year}_{slide_id}_{fmt}.png",
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
    books = (
        Book.query
        .filter_by(user_id=current_user.id)
        .options(selectinload(Book.quotes))
        .all()
    )
    dash = statistics_service.reading_dashboard(books, reading_service)
    year = datetime.utcnow().year
    goal = ReadingGoal.query.filter_by(user_id=current_user.id, year=year).first()
    reading_goal = statistics_service.annual_goal_progress(
        goal,
        dash['reading_summary']['finished_this_year'],
    )
    home = statistics_service.home_personalization(
        username=current_user.username,
        books=books,
        kpis=dash['kpis'],
        reading_summary=dash['reading_summary'],
        currently_reading=dash['currently_reading'],
        reading_goal=reading_goal,
        is_empty=dash['is_empty'],
    )

    return render_template(
        'index.html',
        authors=dash['authors'],
        books=books,
        total_books=dash['total_books'],
        overall_avg=dash['overall_avg'],
        most_active=dash['most_active'],
        wild_count=dash['wild_count'],
        status_counts=dash['status_counts'],
        kpis=dash['kpis'],
        charts=dash['charts'],
        reading_summary=dash['reading_summary'],
        recent_activity=dash['recent_activity'],
        currently_reading=dash['currently_reading'],
        is_empty=dash['is_empty'],
        reading_statuses=ReadingStatus.choices(),
        ReadingStatus=ReadingStatus,
        reading_service=reading_service,
        reading_goal=reading_goal,
        home_hero=home['hero'],
        reading_snapshot=home['snapshot'],
        recently_finished=home['recently_finished'],
    )


@app.route('/reading-goal', methods=['POST'])
@login_required
def set_reading_goal():
    """Create or update the current user's annual reading goal for this year."""
    year = datetime.utcnow().year
    raw = (request.form.get('target_count') or '').strip()
    try:
        target = int(raw)
    except (TypeError, ValueError):
        flash('Enter a whole number of books for your goal.', 'goal_error')
        return redirect(url_for('authors_page'))
    if target < 1 or target > 500:
        flash('Goal must be between 1 and 500 books.', 'goal_error')
        return redirect(url_for('authors_page'))

    goal = ReadingGoal.query.filter_by(user_id=current_user.id, year=year).first()
    if goal is None:
        goal = ReadingGoal(
            user_id=current_user.id,
            year=year,
            target_count=target,
        )
        db.session.add(goal)
        flash(f'{year} reading goal set to {target} books.', 'goal_success')
    else:
        goal.target_count = target
        goal.updated_at = datetime.utcnow()
        flash(f'{year} reading goal updated to {target} books.', 'goal_success')
    db.session.commit()
    return redirect(url_for('authors_page'))


@app.route('/author/<author>')
@login_required
def author_books(author):
    books = (
        Book.query
        .filter_by(author=author, user_id=current_user.id)
        .options(selectinload(Book.quotes))
        .all()
    )
    stats = statistics_service.author_page_stats(books)
    return render_template(
        'author_books.html',
        author=author,
        books=books,
        author_count=stats['author_count'],
        wild_count=stats['wild_count'],
        avg_rating=stats['avg_rating'],
        currently_reading_count=stats['currently_reading_count'],
        reading_statuses=ReadingStatus.choices(),
        ReadingStatus=ReadingStatus,
        reading_service=reading_service,
    )


@app.route('/cover')
def cover():
    return render_template('cover.html')


@app.route('/uploads/books/<path:filename>')
def serve_book_cover(filename):
    """Serve a processed book cover from uploads/books/."""
    path = media_service.resolve_book_cover_path(filename)
    if path is None:
        abort(404)
    return send_from_directory(media_service.books_dir, path.name)


@app.errorhandler(413)
def request_entity_too_large(_error):
    flash('Cover image must be 5 MB or smaller.', 'cover_error')
    return redirect(request.referrer or url_for('authors_page'))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    book = Book.query.get_or_404(id)
    if book.user_id != current_user.id:
        abort(403)

    def _render_edit():
        return render_template(
            'edit_book.html',
            book=book,
            reading_statuses=ReadingStatus.choices(),
            ReadingStatus=ReadingStatus,
            reading_service=reading_service,
        )

    if request.method == 'POST':
        status, rating, err = _parse_status_and_rating(request.form)
        if err:
            flash(err, 'book_error')
            return _render_edit()

        started, finished, date_err = _parse_timeline_dates(request.form, status)
        if date_err:
            flash(date_err, 'book_error')
            return _render_edit()

        book.title = request.form['title']
        book.author = request.form['author']
        book.reading_status = status
        book.rating = rating
        book.is_wild = request.form.get('is_wild') in ('on', '1', 'true', 'True')
        book.started_reading_at = started
        book.finished_reading_at = finished

        remove_cover = request.form.get('remove_cover') in ('on', '1', 'true', 'True')
        cover_file = request.files.get('cover')
        has_new_cover = cover_file and cover_file.filename

        if remove_cover and not has_new_cover:
            media_service.delete_book_cover(book.cover_filename)
            book.cover_filename = None
        elif has_new_cover:
            try:
                new_filename = media_service.save_book_cover(cover_file)
            except MediaValidationError as exc:
                flash(exc.message, 'cover_error')
                return _render_edit()
            old_filename = book.cover_filename
            book.cover_filename = new_filename
            # Delete old file only after the new one is saved successfully
            if old_filename and old_filename != new_filename:
                media_service.delete_book_cover(old_filename)

        db.session.commit()
        return redirect(url_for('authors_page'))
    return _render_edit()


@app.route('/delete/<int:id>')
@login_required
def delete(id):
    book = Book.query.get_or_404(id)
    if book.user_id != current_user.id:
        abort(403)
    cover_filename = book.cover_filename
    db.session.delete(book)
    db.session.commit()
    media_service.delete_book_cover(cover_filename)
    return redirect(url_for('authors_page'))


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    next_param = safe_next_url(
        request.form.get('next') or request.args.get('next') or request.referrer,
        url_for('authors_page'),
    )

    def _render_add():
        return render_template(
            'add_book.html',
            next=next_param,
            reading_statuses=ReadingStatus.choices(),
            ReadingStatus=ReadingStatus,
            reading_service=reading_service,
        )

    if request.method == 'POST':
        status, rating, err = _parse_status_and_rating(request.form)
        if err:
            flash(err, 'book_error')
            return _render_add()

        started, finished, date_err = _parse_timeline_dates(request.form, status)
        if date_err:
            flash(date_err, 'book_error')
            return _render_add()

        cover_filename = None
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            try:
                cover_filename = media_service.save_book_cover(cover_file)
            except MediaValidationError as exc:
                flash(exc.message, 'cover_error')
                return _render_add()
        else:
            # Optional catalog cover (provider URL). Never blocks manual entry.
            cover_url = (request.form.get('cover_url') or '').strip()
            if cover_url and book_metadata_service.is_allowed_cover_url(cover_url):
                raw = book_metadata_service.fetch_cover_bytes(
                    cover_url,
                    max_bytes=media_service.MAX_BYTES,
                )
                if raw:
                    try:
                        cover_filename = media_service.save_book_cover_from_bytes(raw)
                    except MediaValidationError:
                        cover_filename = None

        new_book = Book(
            title=request.form['title'],
            author=request.form['author'],
            rating=rating,
            reading_status=status,
            is_wild=request.form.get('is_wild') in ('on', '1', 'true', 'True'),
            cover_filename=cover_filename,
            started_reading_at=started,
            finished_reading_at=finished,
            user_id=current_user.id,
        )
        db.session.add(new_book)
        db.session.commit()
        sep = '&' if '?' in next_param else '?'
        return redirect(next_param + sep + 'added=1')
    return _render_add()


@app.route('/api/books/search')
@login_required
@limiter.limit('30 per minute')
def api_books_search():
    """Live catalog search for the Add Book form. Never mutates the database."""
    query = (request.args.get('q') or '').strip()
    try:
        limit = int(request.args.get('limit') or 8)
    except (TypeError, ValueError):
        limit = 8
    results = book_metadata_service.search_books(query, limit=limit)
    return jsonify({'results': results, 'query': query})


@app.route('/api/books/<path:book_id>')
@login_required
@limiter.limit('30 per minute')
def api_books_get(book_id):
    """Fetch one normalized catalog entry by prefixed id (gb:… / ol:…)."""
    book = book_metadata_service.get_book(book_id)
    if not book:
        return jsonify({'error': 'not_found'}), 404
    return jsonify(book)


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

@app.route('/admin')
@admin_required
def admin_home():
    return redirect(url_for('admin_users'))


@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.asc()).all()
    books = Book.query.all()
    stats = statistics_service.admin_dashboard(
        users=users,
        books=books,
        total_quotes=Quote.query.count(),
        admin_username=ADMIN_USERNAME,
        orphaned_count=Book.query.filter_by(user_id=None).count(),
    )

    flash_errors   = get_flashed_messages(category_filter=['admin_error'])
    flash_messages = get_flashed_messages(category_filter=['admin_success'])
    return render_template(
        'admin_users.html',
        users=users,
        non_admin=stats['non_admin'],
        total_users=stats['total_users'],
        active_users=stats['active_users'],
        disabled_users=stats['disabled_users'],
        total_books=stats['total_books'],
        total_quotes=stats['total_quotes'],
        wild_count=stats['wild_count'],
        currently_reading=stats['currently_reading'],
        books_added_this_week=stats['books_added_this_week'],
        most_active=stats['most_active'],
        newest_user=stats['newest_user'],
        month_labels_js=stats['month_labels_js'],
        books_per_month=stats['books_per_month'],
        users_labels_js=stats['users_labels_js'],
        users_books_js=stats['users_books_js'],
        top_authors_global=stats['top_authors_global'],
        top_books_global=stats['top_books_global'],
        orphaned_count=stats['orphaned_count'],
        flash_errors=flash_errors,
        flash_messages=flash_messages,
        admin_nav='dashboard',
    )


@app.route('/admin/explorer')
@admin_required
def admin_explorer():
    q = (request.args.get('q') or '').strip()
    sort = (request.args.get('sort') or 'books').strip().lower()
    order = (request.args.get('order') or 'desc').strip().lower()
    if sort not in {'username', 'joined', 'books', 'quotes', 'wild', 'reading', 'status'}:
        sort = 'books'
    if order not in {'asc', 'desc'}:
        order = 'desc'

    users = (
        User.query
        .options(
            selectinload(User.books),
            selectinload(User.quotes),
        )
        .order_by(User.created_at.asc())
        .all()
    )
    rows = statistics_service.admin_user_explorer(
        users, q=q, sort=sort, order=order
    )
    return render_template(
        'admin_explorer.html',
        rows=rows,
        q=q,
        sort=sort,
        order=order,
        admin_nav='explorer',
    )


@app.route('/admin/users/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    user = (
        User.query
        .options(
            selectinload(User.books).selectinload(Book.quotes),
            selectinload(User.quotes).selectinload(Quote.book),
        )
        .filter_by(id=user_id)
        .first_or_404()
    )
    books = list(user.books)
    books.sort(
        key=lambda b: (
            b.date_added is None,
            -(b.date_added.timestamp() if b.date_added else 0),
            (b.title or '').lower(),
        )
    )
    dash = statistics_service.reading_dashboard(
        books, reading_service
    )
    quotes = list(user.quotes)
    quote_groups = statistics_service.admin_group_quotes(quotes)
    flash_errors   = get_flashed_messages(category_filter=['admin_error'])
    flash_messages = get_flashed_messages(category_filter=['admin_success'])
    return render_template(
        'admin_user_detail.html',
        profile_user=user,
        books=books,
        quote_groups=quote_groups,
        quote_count=len(quotes),
        kpis=dash['kpis'],
        charts=dash['charts'],
        reading_summary=dash['reading_summary'],
        currently_reading=dash['currently_reading'],
        recent_activity=dash['recent_activity'],
        is_empty=dash['is_empty'],
        status_counts=dash['status_counts'],
        wild_count=dash['wild_count'],
        overall_avg=dash['overall_avg'],
        ReadingStatus=ReadingStatus,
        reading_service=reading_service,
        reading_statuses=ReadingStatus.choices(),
        flash_errors=flash_errors,
        flash_messages=flash_messages,
        admin_nav='explorer',
    )


@app.route('/admin/library')
@admin_required
def admin_library():
    user_id = request.args.get('user_id', type=int)
    author = (request.args.get('author') or '').strip()
    status = (request.args.get('status') or '').strip()
    rating = request.args.get('rating', type=int)
    wild_raw = (request.args.get('wild') or '').strip().lower()

    query = Book.query.options(
        selectinload(Book.quotes),
        selectinload(Book.owner),
    )
    if user_id is not None:
        query = query.filter(Book.user_id == user_id)
    if author:
        query = query.filter(Book.author.ilike(f'%{author}%'))
    if status and ReadingStatus.is_valid(status):
        query = query.filter(Book.reading_status == status)
    if rating is not None and 1 <= rating <= 5:
        query = query.filter(Book.rating == rating)
    if wild_raw in {'1', 'true', 'yes'}:
        query = query.filter(Book.is_wild.is_(True))
    elif wild_raw in {'0', 'false', 'no'}:
        query = query.filter(Book.is_wild.is_(False))

    books = query.order_by(Book.date_added.desc(), Book.id.desc()).all()
    users = User.query.order_by(User.username.asc()).all()
    authors = [
        row[0]
        for row in db.session.query(Book.author).distinct().order_by(Book.author.asc()).all()
        if row[0]
    ]

    return render_template(
        'admin_library.html',
        books=books,
        users=users,
        authors=authors,
        filter_user_id=user_id,
        filter_author=author,
        filter_status=status,
        filter_rating=rating,
        filter_wild=wild_raw,
        ReadingStatus=ReadingStatus,
        reading_service=reading_service,
        reading_statuses=ReadingStatus.choices(),
        admin_nav='library',
        total_matched=len(books),
    )


@app.route('/admin/assign-orphaned', methods=['POST'])
@admin_required
def admin_assign_orphaned():
    user_id = request.form.get('user_id', type=int)
    if not user_id:
        flash('Please select a user.', 'admin_error')
        return redirect(url_for('admin_users'))
    owner = User.query.get_or_404(user_id)
    orphaned = Book.query.filter_by(user_id=None).all()
    for b in orphaned:
        b.user_id = owner.id
    db.session.commit()
    flash(f'Assigned {len(orphaned)} orphaned book(s) to "{owner.username}".', 'admin_success')
    return redirect(url_for('admin_users'))


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
    return redirect(
        safe_next_url(request.form.get('next'), url_for('admin_users'))
    )


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'admin_error')
        return redirect(url_for('admin_users'))
    # Cascade-delete quotes then books (and their cover files), then goals, then user
    for q in Quote.query.filter_by(user_id=user.id).all():
        db.session.delete(q)
    for b in Book.query.filter_by(user_id=user.id).all():
        media_service.delete_book_cover(b.cover_filename)
        db.session.delete(b)
    for g in ReadingGoal.query.filter_by(user_id=user.id).all():
        db.session.delete(g)
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" and all their data have been deleted.', 'admin_success')
    return redirect(
        safe_next_url(request.form.get('next'), url_for('admin_explorer'))
    )

def _repair_db():
    """Add any columns missing from pre-migration production databases.
    Uses PostgreSQL's ADD COLUMN IF NOT EXISTS — completely safe to re-run."""
    with app.app_context():
        if not db.engine.url.drivername.startswith('postgresql'):
            return  # SQLite local dev: migrations handle this
        try:
            with db.engine.begin() as conn:
                conn.execute(sa.text(
                    'ALTER TABLE book '
                    'ADD COLUMN IF NOT EXISTS user_id INTEGER, '
                    'ADD COLUMN IF NOT EXISTS date_added TIMESTAMP, '
                    'ADD COLUMN IF NOT EXISTS is_wild BOOLEAN NOT NULL DEFAULT FALSE, '
                    'ADD COLUMN IF NOT EXISTS cover_filename VARCHAR(255), '
                    "ADD COLUMN IF NOT EXISTS reading_status VARCHAR(20) NOT NULL DEFAULT 'finished', "
                    'ADD COLUMN IF NOT EXISTS started_reading_at DATE, '
                    'ADD COLUMN IF NOT EXISTS finished_reading_at DATE'
                ))
                conn.execute(sa.text(
                    'ALTER TABLE "user" '
                    'ADD COLUMN IF NOT EXISTS avatar TEXT, '
                    'ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE, '
                    'ADD COLUMN IF NOT EXISTS security_question VARCHAR(200), '
                    'ADD COLUMN IF NOT EXISTS security_answer_hash VARCHAR(256)'
                ))
                conn.execute(sa.text('''
                    CREATE TABLE IF NOT EXISTS quote (
                        id SERIAL PRIMARY KEY,
                        text VARCHAR(2000) NOT NULL,
                        page_ref VARCHAR(20),
                        book_id INTEGER NOT NULL REFERENCES book(id),
                        user_id INTEGER NOT NULL REFERENCES "user"(id),
                        date_added TIMESTAMP NOT NULL
                    )
                '''))
                conn.execute(sa.text('''
                    CREATE TABLE IF NOT EXISTS reading_goal (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES "user"(id),
                        year INTEGER NOT NULL,
                        target_count INTEGER NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL,
                        CONSTRAINT uq_reading_goal_user_year UNIQUE (user_id, year)
                    )
                '''))
            print('[REPAIR] DB schema repair completed.', flush=True)
        except Exception as exc:
            print(f'[REPAIR] DB schema repair error: {exc}', flush=True)


def _seed_admin_if_needed():
    """Create the Admin account on first deploy; assign orphaned books to Kwalitec.
    Runs once at startup — safe to leave in place, no-ops when already done."""
    with app.app_context():
        try:
            admin = User.query.filter_by(username=ADMIN_USERNAME).first()
            if not admin:
                pw = secrets.token_urlsafe(16)
                admin = User(
                    username=ADMIN_USERNAME,
                    password_hash=generate_password_hash(pw),
                    is_admin=True,
                    is_active=True,
                )
                db.session.add(admin)
                db.session.commit()
                print(f'[SEED] Admin user created. ONE-TIME PASSWORD: {pw}', flush=True)
            else:
                print('[SEED] Admin user already exists — skipping.', flush=True)

            # Assign any books/quotes with no owner to Kwalitec
            owner = User.query.filter_by(username='Kwalitec').first()
            if owner:
                orphaned_books = Book.query.filter_by(user_id=None).all()
                orphaned_quotes = Quote.query.filter_by(user_id=None).all()
                for b in orphaned_books:
                    b.user_id = owner.id
                for q in orphaned_quotes:
                    q.user_id = owner.id
                if orphaned_books or orphaned_quotes:
                    db.session.commit()
                    print(f'[SEED] Assigned {len(orphaned_books)} book(s) and '
                          f'{len(orphaned_quotes)} quote(s) to Kwalitec.', flush=True)
        except Exception as exc:
            print(f'[SEED] Skipped (DB not ready yet?): {exc}', flush=True)


_repair_db()
_seed_admin_if_needed()


if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite') and not _is_prod:
        with app.app_context():
            db.create_all()
    app.run(debug=debug, host='0.0.0.0', port=port)