import psycopg

conn = psycopg.connect("postgresql://trading:password@localhost:5432/trading_bot")
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
tables = cursor.fetchall()

print("Current tables in the database:")
for table in tables:
    print(f"- {table[0]}")

# Check for specific Phase 2 tables
phase2_tables = [
    "market_events",
    "fo_options_eod",
    "cm_spot_eod",
    "greeks_snapshot",
    "ws_ticks",
    "download_checkpoint",
    "v_daily_oi_summary",
    "v_tick_1min_ohlcv",
]

print("\nChecking for Phase 2 tables:")
all_present = True
for table in phase2_tables:
    cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}');")
    exists = cursor.fetchone()[0]
    status = "✓ Present" if exists else "✗ Missing"
    print(f"- {table}: {status}")
    if not exists:
        all_present = False

if all_present:
    print("\n✅ All Phase 2 tables are present!")
else:
    print("\n⚠️  Some Phase 2 tables are missing.")

conn.close()
