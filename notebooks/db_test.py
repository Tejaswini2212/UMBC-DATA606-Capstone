# db_test.py
from sqlalchemy import text
from db_helpers import engine

def main():
    with engine.connect() as conn:
        # Simple test – just see if query runs at all
        result = conn.execute(text("SELECT NOW()"))
        print("DB time:", result.scalar_one())

        # Optional: check if any data exists in statement_rows
        rows = conn.execute(text("SELECT COUNT(*) FROM statement_rows")).scalar_one()
        print("Rows in statement_rows:", rows)

if __name__ == "__main__":
    main()
