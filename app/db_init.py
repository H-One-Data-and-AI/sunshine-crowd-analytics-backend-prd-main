import sqlite3
import pandas as pd
from settings import (
    DB_PATH,
    LOCATION_CSV,
    CARGILLS_CSV,
    COMPETITOR_CSV,
    MAIN_ADJUSTED_CSV,
    COMPETITORS_RAW_CSV,
)
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)


def create_users_table(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            hashed_password TEXT NOT NULL
        )
    """)

    # Check if the default admin exists
    cursor.execute("SELECT email FROM users WHERE email = 'admin@gmail.com'")
    if cursor.fetchone() is None:
        # Create default admin user
        default_admin_email = "admin@gmail.com"
        default_admin_password = "admin123"  # You should change this
        hashed_password = get_password_hash(default_admin_password)

        cursor.execute(
            "INSERT INTO users (email, role, hashed_password) VALUES (?, ?, ?)",
            (default_admin_email, "admin", hashed_password)
        )
        print("=====================================================")
        print("✅ Default admin user created.")
        print(f"   Email: {default_admin_email}")
        print(f"   Password: {default_admin_password}")
        print("=====================================================")

    conn.commit()
    print("✅ Users table checked/created.")

def create_table_from_csv(csv_path, table_name, conn):
    df = pd.read_csv(csv_path)

    # Special handling for the 'cargills' table to add the 'User' column
    if table_name == 'cargills':
        # Check if the 'User' column doesn't already exist in the CSV
        if 'User' not in df.columns:
            # Add the 'User' column and initialize all existing rows with None.
            # This will be stored as NULL in the database.
            print(f"Adding 'User' column to '{table_name}' and setting initial values to NULL.")
            df['User'] = None

    # 🔥 Convert pd.NA / NaN → None (safe for SQLite)
    df = df.where(pd.notnull(df), None)

    # This will now create the 'cargills' table WITH the 'User' column
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    print(f"✅ Created table: {table_name} ({len(df)} rows)")

    # Indexes for fast filtering and joins (add only if column exists)
    idx_cols = ["Province", "District", "DS", "hex_id", "User"] # Added User to index list
    for col in idx_cols:
        if col in df.columns:
            print(f"Creating index for column: {col} in table: {table_name}")
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_{col} ON "{table_name}"("{col}");')

    conn.commit()

def init_db():
    conn = sqlite3.connect(DB_PATH)

    create_users_table(conn)

    # 1) Existing 3 tables
    create_table_from_csv(LOCATION_CSV, "location", conn)
    create_table_from_csv(CARGILLS_CSV, "cargills", conn)
    create_table_from_csv(COMPETITOR_CSV, "competitor", conn)

    # 2) NEW: base data for re-scoring
    create_table_from_csv(MAIN_ADJUSTED_CSV, "main_df_adjusted", conn)
    create_table_from_csv(COMPETITORS_RAW_CSV, "competitors_data", conn)

    conn.close()
    print("🎯 All 5 tables created in one database!")

if __name__ == "__main__":
    init_db()
