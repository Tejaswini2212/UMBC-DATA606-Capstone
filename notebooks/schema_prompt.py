# schema_prompt.py

DB_SCHEMA = """
You are working with a Postgres database for a personal finance chatbot.

The MOST IMPORTANT table (use this by default for transaction-level questions) is:

Table v_tx_normalized (
    id            INTEGER,
    statement_id  INTEGER,
    user_id       INTEGER,
    statement_name   TEXT,
    statement_type   TEXT,
    section_name     TEXT,
    description      TEXT,
    vendor           TEXT,
    category         TEXT,
    amount_raw       TEXT,
    amount_num       NUMERIC,
    tx_kind          TEXT,
    signed_amount    NUMERIC,
    amount           NUMERIC,
    txn_date         DATE,
    month_start      TIMESTAMPTZ,
    year             NUMERIC,
    month_number     NUMERIC
);

Table v_monthly_summary (
    month         DATE,
    user_id       INTEGER,
    total_income  NUMERIC,
    total_expense NUMERIC,
    savings       NUMERIC
);

Table v_statement_summary (
    statement_id   INTEGER,
    statement_type TEXT,
    statement_name TEXT,
    period_start   DATE,
    period_end     DATE,
    total_income   NUMERIC,
    total_expense  NUMERIC,
    savings        NUMERIC,
    user_id        INTEGER
);

Table v_statement_period (
    statement_id   INTEGER,
    statement_type TEXT,
    statement_name TEXT,
    user_id        INTEGER,
    period_start   DATE,
    period_end     DATE
);

Table v_account_summary (
    id             INTEGER,
    statement_id   INTEGER,
    statement_name TEXT,
    statement_type TEXT,
    section_name   TEXT,
    description    TEXT,
    amount         TEXT,
    user_id        INTEGER
);

Table v_income / v_expenses / v_credit_income / v_credit_expenses / v_debit_income / v_debit_expenses all have:
(
    id             INTEGER,
    statement_id   INTEGER,
    statement_name TEXT,
    statement_type TEXT,
    section_name   TEXT,
    Date           TEXT,
    "Transaction Date" TEXT,
    "Posting Date" TEXT,
    description    TEXT,
    amount         NUMERIC,
    vendor         TEXT,
    category       TEXT,
    txn_date       DATE,
    user_id        INTEGER
);

Raw extracted rows:

Table statement_rows (
    id             INTEGER,
    "Date"         TEXT,
    "Transaction Date" TEXT,
    "Posting Date" TEXT,
    "Description"  TEXT,
    "Amount"       TEXT,
    "Vendor"       TEXT,
    "Category"     TEXT,
    statement_name TEXT,
    statement_type TEXT,
    section_name   TEXT,
    statement_id   INTEGER,
    user_id        INTEGER
);

GENERAL RULES FOR SQL:
1. ALWAYS filter by: user_id = %(user_id)s.
2. Use v_tx_normalized for ANY spending/income/transaction questions.
3. Use:
   - tx_kind = 'expense' for spending.
   - tx_kind = 'income' for income.
4. Use txn_date for ALL date filtering.
5. Use description, vendor, and category for text matching.
6. Do NOT invent columns. Only use the columns listed above.
7. Prefer lowercase column names: description, vendor, category, txn_date, amount, etc.
8. Avoid using the TEXT date fields ("Date", "Transaction Date", "Posting Date") unless absolutely necessary.
9. Return EXACTLY one SQL query. No comments, no backticks, no explanation.
"""
