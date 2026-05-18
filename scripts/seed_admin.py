#!/usr/bin/env python3
"""
One-time seed script: creates the 'Admin' user and reassigns all
orphaned books (user_id IS NULL) to that user.

Run from the project root with the app's virtual environment active:
    python scripts/seed_admin.py
"""
import sys
import os
import secrets

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, User, Book
from werkzeug.security import generate_password_hash


def seed():
    with app.app_context():
        admin = User.query.filter_by(username='Admin').first()

        if admin:
            print(f'Admin user already exists (id={admin.id}). Skipping creation.')
        else:
            password = secrets.token_urlsafe(16)
            admin = User(
                username='Admin',
                password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
                is_admin=True,
            )
            db.session.add(admin)
            db.session.flush()  # get admin.id before commit
            print('=' * 60)
            print('Admin user created.')
            print(f'  Username : Admin')
            print(f'  Password : {password}')
            print('SAVE THIS PASSWORD — it will not be shown again.')
            print('=' * 60)

        # Reassign all orphaned books to Admin
        orphaned = Book.query.filter_by(user_id=None).all()
        if orphaned:
            for book in orphaned:
                book.user_id = admin.id
            db.session.commit()
            print(f'Assigned {len(orphaned)} orphaned book(s) to Admin.')
        else:
            db.session.commit()
            print('No orphaned books found.')


if __name__ == '__main__':
    seed()
