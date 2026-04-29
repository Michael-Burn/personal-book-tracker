import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman

app = Flask(__name__)
# Use DATABASE_URL env var when provided (e.g. Postgres URL on hosting)
# Default to a local sqlite DB inside the instance folder for development only
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///instance/books.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Secrets and cookie protections (set SECRET_KEY in environment for production)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)
# Migrations and security helpers
migrate = Migrate()
csrf = CSRFProtect()
talisman = Talisman()

# Database Model
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)

# Create the database
# Initialize extensions after app and db created
migrate.init_app(app, db)
csrf.init_app(app)
# Apply basic security headers (strict defaults).
# Render provides TLS; Talisman will enforce secure headers in front of that.
talisman.init_app(app, content_security_policy=None)

# Do not create the database at import time. For local development
# create the sqlite DB only when running the app directly (not when
# invoked by Flask CLI or migration commands).

@app.route('/')
def index():
    # Default landing page (cover)
    return render_template('cover.html')


@app.route('/authors')
def authors_page():
    # Show a list of authors with book counts, titles and average rating
    books = Book.query.all()
    author_map = {}
    total_books = 0
    total_rating_sum = 0
    total_rating_count = 0
    for b in books:
        total_books += 1
        total_rating_sum += (b.rating or 0)
        total_rating_count += 1
        entry = author_map.setdefault(b.author, {'name': b.author, 'bookCount': 0, 'titles': [], 'ratingSum': 0})
        entry['bookCount'] += 1
        entry['titles'].append(b.title)
        entry['ratingSum'] += (b.rating or 0)

    # finalize avgRating per author
    authors = []
    for a in author_map.values():
        avg = round((a['ratingSum'] / a['bookCount']) if a['bookCount'] else 0, 2)
        authors.append({'name': a['name'], 'bookCount': a['bookCount'], 'titles': a['titles'], 'avgRating': avg})

    # overall average rating
    overall_avg = round((total_rating_sum / total_rating_count), 2) if total_rating_count else 0

    # most active author
    most_active = max(authors, key=lambda x: x['bookCount'])['name'] if authors else ''

    # Convert to sorted list by author name by default
    authors = sorted(authors, key=lambda x: x['name'] or '')

    return render_template('index.html', authors=authors, total_books=total_books, overall_avg=overall_avg, most_active=most_active)


@app.route('/author/<author>')
def author_books(author):
    # Show all books for a given author
    books = Book.query.filter_by(author=author).all()
    author_count = len(books)
    return render_template('author_books.html', author=author, books=books, author_count=author_count)


@app.route('/cover')
def cover():
    # Simple cover/landing page. Place an image at static/cover.jpg to show here.
    return render_template('cover.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    book = Book.query.get_or_404(id)
    
    if request.method == 'POST':
        book.title = request.form['title']
        book.author = request.form['author']
        book.rating = int(request.form['rating'])
        
        db.session.commit()
        return redirect(url_for('index'))
        
    return render_template('edit_book.html', book=book)

@app.route('/delete/<int:id>')
def delete(id):
    book_to_delete = Book.query.get_or_404(id)
    db.session.delete(book_to_delete)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        new_book = Book(
            title=request.form['title'],
            author=request.form['author'],
            rating=int(request.form['rating']),
        )
        db.session.add(new_book)
        db.session.commit()
        # Prefer explicit next from the form, else fall back to referrer or authors page
        next_url = request.form.get('next') or request.referrer or url_for('authors_page')
        # Validate it's a local path
        if not isinstance(next_url, str) or not next_url.startswith('/'):
            next_url = url_for('authors_page')
        # Append added=1 query param
        sep = '&' if '?' in next_url else '?'
        return redirect(next_url + sep + 'added=1')

    # GET: allow caller to pass ?next=/some/path so we can return there after save
    next_param = request.args.get('next') or request.referrer or url_for('authors_page')
    return render_template('add_book.html', next=next_param)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    # For local sqlite development only, create DB when running directly.
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite') and os.environ.get('FLASK_ENV') != 'production':
        with app.app_context():
            db.create_all()

    app.run(debug=debug, host='0.0.0.0', port=port)