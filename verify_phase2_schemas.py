import psycopg2

# List of Phase 2 tables we expect to exist
expected_tables = [
    "market_events",
    "fo_options_eod",
    "cm_spot_eod",
    "greeks_snapshot",
    "ws_ticks",
    "download_checkpoint",
    "v_daily_oi_summary",
    "v_tick_1min_ohlcv",
    "v_atm_strikes",
]


def verify_tables():
    try:
        # Connect to the database
        conn = psycopg2.connect(
            host="localhost", database="trading_bot", user="trading", password="password", port=5432
        )

        cursor = conn.cursor()

        print("Checking for Phase 2 tables...")
        print("=" * 50)

        all_present = True

        # Check each expected table
        for table in expected_tables:
            # Check table existence
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table}'
                );
            """)
            table_exists = cursor.fetchone()[0]

            # Check if it's a TimescaleDB hypertable (for non-view tables)
            is_hypertable = False
            if table not in ["v_daily_oi_summary", "v_tick_1min_ohlcv", "v_atm_strikes"]:
                cursor.execute(f"""
                    SELECT EXISTS (
                        SELECT FROM timescaledb_information.hypertables
                        WHERE hypertable_name = '{table}'
                    );
                """)
                is_hypertable = cursor.fetchone()[0]

            # Check if it's a continuous aggregate (for views)
            is_continuous_aggregate = False
            if table in ["v_daily_oi_summary", "v_tick_1min_ohlcv"]:
                cursor.execute(f"""
                    SELECT EXISTS (
                        SELECT FROM timescaledb_information.continuous_aggregates
                        WHERE view_name = '{table}'
                    );
                """)
                is_continuous_aggregate = cursor.fetchone()[0]

            # Check if it's a regular view
            is_view = False
            if table == "v_atm_strikes":
                cursor.execute(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.views
                        WHERE table_name = '{table}'
                    );
                """)
                is_view = cursor.fetchone()[0]

            # Determine status
            status_parts = []
            if table_exists:
                status_parts.append("✓ Present")
            else:
                status_parts.append("✗ Missing")
                all_present = False

            if table in ["v_daily_oi_summary", "v_tick_1min_ohlcv"]:
                if is_continuous_aggregate:
                    status_parts.append("✓ Continuous Aggregate")
                else:
                    status_parts.append("✗ Not Continuous Aggregate")
            elif table == "v_atm_strikes":
                if is_view:
                    status_parts.append("✓ View")
                else:
                    status_parts.append("✗ Not View")
            else:
                if is_hypertable:
                    status_parts.append("✓ Hypertable")
                else:
                    status_parts.append("✗ Not Hypertable")

            print(f"{table}: {', '.join(status_parts)}")

        print("=" * 50)
        if all_present:
            print("✅ SUCCESS: All Phase 2 schemas are installed correctly!")
        else:
            print("⚠️  WARNING: Some Phase 2 schemas are missing or not configured properly.")

        # Summary of existing tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        regular_tables = cursor.fetchall()

        cursor.execute("""
            SELECT view_name
            FROM information_schema.views
            WHERE table_schema = 'public'
            ORDER BY view_name
        """)
        views = cursor.fetchall()

        print("\nExisting Regular Tables:")
        for table in regular_tables:
            print(f"- {table[0]}")

        print("\nExisting Views:")
        for view in views:
            print(f"- {view[0]}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ ERROR: Could not connect to database: {e}")
        print("Check if Docker is running and the database is accessible.")
        print("Command to run: docker ps")


if __name__ == "__main__":
    verify_tables()
