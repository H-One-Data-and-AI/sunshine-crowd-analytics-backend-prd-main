#Import OS
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Single SQLite DB file
DB_PATH = os.path.join(BASE_DIR, "crowd_data.db")

# CSV sources
LOCATION_CSV = os.path.join(BASE_DIR, "Scored_main_df_adjusted.csv")   # -> table: location
CARGILLS_CSV = os.path.join(BASE_DIR, "cargills_with_hex.csv")         # -> table: cargills
COMPETITOR_CSV = os.path.join(BASE_DIR, "competitors_with_hex.csv")    # -> table: competitor

# NEW sources required for (re)scoring
MAIN_ADJUSTED_CSV = os.path.join(BASE_DIR, "main_df_adjusted.csv")     # -> table: main_df_adjusted
COMPETITORS_RAW_CSV = os.path.join(BASE_DIR, "competitors.csv")        # -> table: competitors_data

# Pagination defaults (used by /data endpoints)
DEFAULT_LIMIT = 500
MAX_LIMIT = 5000
