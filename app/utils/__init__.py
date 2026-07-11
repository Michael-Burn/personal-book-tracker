"""Generic helpers shared across routes and services."""

from utils.ratings import has_rating
from utils.dates import since_date
from utils.redirects import safe_next_url

__all__ = ['has_rating', 'since_date', 'safe_next_url']
