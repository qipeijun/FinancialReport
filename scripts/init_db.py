import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from scripts.rss_finance_analyzer import RSSAnalyzer

db_path = project_root / "data" / "news_data.db"
cache_path = project_root / "data" / "http_cache.json"

# Ensure data dir exists
db_path.parent.mkdir(parents=True, exist_ok=True)

# Remove existing file if it exists (to ensure fresh start)
if db_path.exists():
    db_path.unlink()

# Initialize database
analyzer = RSSAnalyzer(db_path, cache_path)
analyzer._init_database()
print(f"New database initialized successfully at {db_path}")
