# chatbot_helpers.py

import os
import re
import json
from typing import Optional, List

import pandas as pd
from openai import OpenAI

OPENAI_KEY = os.getenv("OPENAI_KEY", "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")
client = OpenAI(api_key=OPENAI_KEY)

# ==============================================================
#  SCHEMA TEXT FOR SQL GENERATION  (SIMPLE 3-VIEW BRAIN)
# ==============================================================

SCHEMA_TEXT = """
You are generating SQL for a Postgres database with these views:

View v_transactions_bi (
    txn_id          INTEGER,
    statement_id    INTEGER,
    user_id         INTEGER,
    statement_name  TEXT,
    statement_type  TEXT,   -- 'debit' or 'credit'
    section_name    TEXT,
    description     TEXT,
    vendor          TEXT,
    category        TEXT,
    amount_raw      TEXT,
    amount_num      NUMERIC,
    tx_kind         TEXT,   -- 'income' or 'expense'
    signed_amount   NUMERIC,
    amount          NUMERIC, -- ABS(spent or received)
    txn_date        DATE,
    month_start     DATE,
    year            INTEGER,
    month_number    INTEGER
);

View v_monthly_summary (
    user_id        INTEGER,
    month_start    DATE,
    year           INTEGER,
    month_number   INTEGER,
    total_income   NUMERIC,
    total_expenses NUMERIC,
    net_savings    NUMERIC
);

View v_account_summary (
     statement_id (integer)
     user_id (integer)
     statement_name (text)
     statement_type (text) -- 'credit' or 'debit'
     section_name (text)
     description (text)  -- e.g. 'Previous Balance', 'Payment Due Date',
                            -- 'Beginning balance on ...', 'Ending balance on ...'
     amount (text)       -- value as a string: money OR a date like '12/13/2024'
     
);


View v_statement_period
    (
    statement_id (integer)
    statement_type (text)
    statement_name (text)
    user_id (integer)
    period_start (date)
    period_end (date)
);

IMPORTANT NOTES:
- v_transactions_bi is the main "brain" for all individual transactions
  (income + expenses, both debit and credit card).
- tx_kind = 'expense' means money going out (spending).
- tx_kind = 'income' means money coming in (deposits, salary, refunds).
- statement_type is 'debit' or 'credit' and should be returned as txn_type.
- v_monthly_summary already has totals per month per user.
- v_account_summary contains statement-level rows like 'New Balance Total',
  'Payment Due Date', 'Total Credit Line', etc.

"""


# ==============================================================
#  GPT → SQL
# ==============================================================

def normalize_sql(sql: str) -> str:
    """
    Small cleanup to fix common LLM mistakes with column names.
    """
    replacements = {
        '"Description"': 'description',
        '"Vendor"': 'vendor',
        '"Category"': 'category',
    }
    fixed = sql
    for bad, good in replacements.items():
        fixed = fixed.replace(bad, good)
    return fixed


def generate_sql_from_question(
    question: str,
    chat_history: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Use GPT to turn a natural language question into a single safe SELECT query.

    MODIFICATIONS:
    - `chat_history` lets the model treat this as a follow-up question.
      Pass in the last few user questions so it can reuse the same
      month / period / category when user says things like
      "what about food?", "go deeper into groceries", etc.
    - Also teaches the model about category drill-down ("Top categories"
      → "go deeper into Food" → detailed transactions).
    """

    # Build a short conversation context string for the model
    if chat_history:
        history_text = "\n".join(f"- {q}" for q in chat_history)
        history_block = (
            "Recent conversation (from oldest to newest):\n"
            f"{history_text}\n\n"
            "The final question in this list is the CURRENT question you must answer.\n"
            "Use earlier questions only for context when the latest one is vague\n"
            "or says things like 'that month', 'those categories', 'go deeper',\n"
            "'only groceries', etc.\n"
        )
    else:
        history_block = (
            "There is no previous conversation. Treat this as an independent question.\n"
        )

    system = (
        "You are a Postgres SQL generator for a personal finance chatbot.\n"
        "You receive a natural language question about a user's past transactions "
        "and must respond with exactly ONE SQL SELECT statement.\n\n"
        "CONSTRAINTS:\n"
        "- NEVER modify data. Do not use INSERT, UPDATE, DELETE, DROP, ALTER,\n"
        "  TRUNCATE, CREATE, GRANT, or REVOKE.\n"
        "- Only use the views in the schema.\n"
        "- Always filter by user_id = :user_id in the WHERE clause for any\n"
        "  user-specific query.\n"
        "- Do NOT wrap the SQL in markdown code fences. Return ONLY raw SQL.\n"
        "- Column names are case-sensitive when quoted.\n\n"
        f"{SCHEMA_TEXT}\n"
        "GLOBAL RULES:\n"
        "- For spending questions, use v_transactions_bi with tx_kind = 'expense'.\n"
        "- For income questions, use v_transactions_bi with tx_kind = 'income'.\n"
        "- For savings / month-level totals, use v_monthly_summary.\n"
        "- For statement balances / due dates / credit limits, use v_account_summary.\n"
        "- Prefer using txn_date, month_start, year, month_number for dates.\n"
        "- Never format dates with TO_CHAR in the SELECT list; return raw date columns.\n"
        "- For transaction lists, return these columns when available:\n"
        "  txn_date, vendor, category, description, amount, statement_type AS txn_type.\n"
        "- Do NOT return technical columns like amount_raw, signed_amount, section_name.\n\n"
        "VENDOR / NAME / ZELLE RULE (VERY IMPORTANT):\n"
        "- When the question includes a person, vendor, merchant, or keyword such as\n"
        "  'Amazon', 'Uber', 'Zelle', 'IMAN', 'Nikhil', 'Rent', 'Temple', etc.,\n"
        "  you MUST search in BOTH vendor AND description using case-insensitive\n"
        "  partial matching:\n"
        "    (vendor ILIKE '%keyword%' OR description ILIKE '%keyword%')\n"
        "- If the question mentions 'Zelle', additionally require\n"
        "    description ILIKE '%zelle%'.\n"
        "This is mandatory because many names appear only in description.\n\n"
        "QUESTION PATTERNS AND HOW TO ANSWER:\n"
        "\n"
        "1) LARGEST TRANSACTIONS (\"largest\", \"biggest purchases\", \"top transactions\"):\n"
        "   - Use v_transactions_bi with tx_kind = 'expense'.\n"
        "   - Order by amount DESC and LIMIT 5 or 10.\n"
        "   - Example template:\n"
        "     SELECT txn_date, vendor, category, description, amount,\n"
        "            statement_type AS txn_type\n"
        "     FROM v_transactions_bi\n"
        "     WHERE user_id = :user_id\n"
        "       AND tx_kind = 'expense'\n"
        "     ORDER BY amount DESC\n"
        "     LIMIT 5;\n\n"
        "2) MONTH-BY-MONTH SPENDING OVER ALL DATA (\"spending by month\", \"each month\"):\n"
        "   - Use v_monthly_summary.\n"
        "   - Return month_start, year, month_number, total_expenses (and optionally\n"
        "     total_income, net_savings).\n"
        "   - Example template:\n"
        "     SELECT month_start, year, month_number,\n"
        "            total_expenses, total_income, net_savings\n"
        "     FROM v_monthly_summary\n"
        "     WHERE user_id = :user_id\n"
        "     ORDER BY month_start;\n\n"
        "3) LATEST MONTH SPENDING SUMMARY (\"latest month\", \"last month you have\",\n"
        "   \"summarize my spending for the latest month\"):\n"
        "   - Step 1: Get the most recent month_start for this user from\n"
        "     v_monthly_summary.\n"
        "   - Step 2: Return all expense transactions from v_transactions_bi for that\n"
        "     month (so the app can summarise categories, biggest transactions, etc.).\n"
        "   - Use a CTE:\n"
        "     WITH latest_month AS (\n"
        "         SELECT MAX(month_start) AS month_start\n"
        "         FROM v_monthly_summary\n"
        "         WHERE user_id = :user_id\n"
        "     )\n"
        "     SELECT t.txn_date, t.vendor, t.category, t.description, t.amount,\n"
        "            t.statement_type AS txn_type\n"
        "     FROM v_transactions_bi t\n"
        "     JOIN latest_month m\n"
        "       ON t.user_id = :user_id\n"
        "      AND date_trunc('month', t.txn_date)::date = m.month_start\n"
        "     WHERE t.tx_kind = 'expense'\n"
        "     ORDER BY t.txn_date;\n\n"
        "4) SPECIFIC MONTH SPENDING (\"in October 2025\", \"in Jan 2024\"):\n"
        "   - If user specifies a month + year, use v_transactions_bi and filter by\n"
        "     txn_date range for that month and tx_kind = 'expense'.\n"
        "   - Example (October 2025):\n"
        "     SELECT txn_date, vendor, category, description, amount,\n"
        "            statement_type AS txn_type\n"
        "     FROM v_transactions_bi\n"
        "     WHERE user_id = :user_id\n"
        "       AND tx_kind = 'expense'\n"
        "       AND txn_date >= DATE '2025-10-01'\n"
        "       AND txn_date <  DATE '2025-11-01'\n"
        "     ORDER BY txn_date;\n\n"
        "5) INCOME / DEPOSITS (\"income\", \"deposits\", \"salary\", \"how much did I receive\"):\n"
        "   - Use v_transactions_bi with tx_kind = 'income'.\n"
        "   - For totals by month, you may use v_monthly_summary.total_income.\n\n"
        "6) SAVINGS (\"how much did I save\", \"net savings\", \"savings rate\"):\n"
        "   - Use v_monthly_summary.\n"
        "   - Return month_start, year, month_number, total_income, total_expenses,\n"
        "     net_savings.\n\n"
        "7) VENDOR / PERSON QUESTIONS (\"How much did I spend on Amazon?\",\n"
        "   \"How many Zelle payments from IMAN?\", \"Show my Uber rides\"):\n"
        "   - Use v_transactions_bi.\n"
        "   - Filter by (vendor ILIKE '%keyword%' OR description ILIKE '%keyword%').\n"
        "   - If the question clearly refers to incoming payments (\"from IMAN\"), use\n"
        "     tx_kind = 'income'. If it refers to payments you made (\"to IMAN\"), use\n"
        "     tx_kind = 'expense'. If unclear, include both kinds.\n"
        "   - For \"how many\" questions, use COUNT(*). For \"how much\" questions, use\n"
        "     SUM(amount) and optionally COUNT(*).\n\n"
        "8) COVERAGE / DATE RANGE INFO (\"what period\", \"from when to when\"):\n"
        "   - Use v_transactions_bi with MIN(txn_date), MAX(txn_date), COUNT(*).\n\n"
        "9) STATEMENT BALANCE / DUE DATE / CREDIT LINE (credit-card-ish questions):\n"
        "   - Use v_account_summary.\n"
        "   - For latest credit statement, find MAX(statement_id) for user_id where\n"
        "     statement_type = 'credit'. Then select rows for descriptions such as\n"
        "     'New Balance Total', 'Payment Due Date', 'Total Credit Line',\n"
        "     'Total Credit Available', etc.\n\n"
        "10) TRANSACTIONS vs SUMMARY BY CATEGORY:\n"
        "   - If the question mentions the word 'transactions' together with 'category'\n"
        "     (e.g. 'show transactions by category', 'list transactions by category'),\n"
        "     DO NOT aggregate. Return one row per transaction with category included,\n"
        "     ordered by category then date.\n\n"
        "   - If the question is about 'spending by category', 'breakdown by category',\n"
        "     or 'how much per category', then return a grouped summary using:\n"
        "     SELECT category, SUM(amount) AS total_spent ... grouped by category.\n\n"
        "11) TOP SPENDING CATEGORIES & CATEGORY DRILLDOWN (VERY IMPORTANT):\n"
        "   - For questions like 'top spending categories', 'biggest categories',\n"
        "     'top 5 categories', you MUST return aggregated spend per category:\n"
        "       SELECT category, SUM(amount) AS total_spent\n"
        "       FROM v_transactions_bi\n"
        "       WHERE user_id = :user_id AND tx_kind = 'expense'\n"
        "       GROUP BY category\n"
        "       ORDER BY total_spent DESC\n"
        "       LIMIT 5;\n"
        "\n"
        "   - For FOLLOW-UP questions like 'go deeper into Food', 'show details for\n"
        "     Shopping', 'break down Groceries', treat them as CATEGORY DRILLDOWN:\n"
        "       * Reuse the SAME date range / month / filters as the immediately\n"
        "         previous question in the conversation when possible.\n"
        "       * Return INDIVIDUAL TRANSACTIONS for that category using v_transactions_bi.\n"
        "       * Example template:\n"
        "         SELECT txn_date, vendor, category, description, amount,\n"
        "                statement_type AS txn_type\n"
        "         FROM v_transactions_bi\n"
        "         WHERE user_id = :user_id\n"
        "           AND tx_kind = 'expense'\n"
        "           AND LOWER(category) = LOWER('Food & Dining')\n"
        "         ORDER BY txn_date;\n"
        "\n"
        "   - If the follow-up is even more specific (e.g., 'only Amazon inside\n"
        "     Shopping'), then filter by BOTH category and vendor/description.\n"
        "     Apply the vendor rule described earlier.\n"
        "\n"
        "REMINDERS:\n"
        "- ONLY return a single SQL statement.\n"
        "- ALWAYS include user_id = :user_id in WHERE clauses for user data.\n"
        "- Use LIMIT for lists when the user asks for 'largest' or 'top' items.\n"
        "- Do not pretty-print or format numbers or dates in SQL; just return raw\n"
        "  numeric/date columns and let the application format them.\n"
            "EXAMPLES:\n"
        "1) User: \"What is my payment due date?\" (latest statement)\n"
        "   SQL:\n"
        "   SELECT a.amount\n"
        "   FROM v_account_summary a\n"
        "   JOIN v_statement_period p\n"
        "     ON a.statement_id = p.statement_id\n"
        "   WHERE a.user_id = :user_id\n"
        "     AND a.description ILIKE 'Payment Due Date%'\n"
        "   ORDER BY p.period_end DESC\n"
        "   LIMIT 1;\n"
        "\n"
        "2) User: \"What is my minimum payment due?\" (latest statement)\n"
        "   SQL:\n"
        "   SELECT a.amount\n"
        "   FROM v_account_summary a\n"
        "   JOIN v_statement_period p\n"
        "     ON a.statement_id = p.statement_id\n"
        "   WHERE a.user_id = :user_id\n"
        "     AND a.description ILIKE 'Total Minimum Payment%'\n"
        "   ORDER BY p.period_end DESC\n"
        "   LIMIT 1;\n"
        "\n"
        "3) User: \"What is my beginning and ending balance?\" (latest statement)\n"
        "   SQL:\n"
        "   SELECT a.description, a.amount\n"
        "   FROM v_account_summary a\n"
        "   JOIN v_statement_period p\n"
        "     ON a.statement_id = p.statement_id\n"
        "   WHERE a.user_id = :user_id\n"
        "     AND a.description ILIKE ANY (ARRAY[\n"
        "         'Beginning balance%',\n"
        "         'Ending balance%'\n"
        "     ])\n"
        "   ORDER BY p.period_end DESC, a.description;\n"
        "\n"
        "4) User: \"What is my beginning and ending balance for my October 2025 statement?\"\n"
        "   SQL:\n"
        "   SELECT a.description, a.amount\n"
        "   FROM v_account_summary a\n"
        "   JOIN v_statement_period p\n"
        "     ON a.statement_id = p.statement_id\n"
        "   WHERE a.user_id = :user_id\n"
        "     AND a.description ILIKE ANY (ARRAY[\n"
        "         'Beginning balance%',\n"
        "         'Ending balance%'\n"
        "     ])\n"
        "     AND p.period_end >= DATE '2025-10-01'\n"
        "     AND p.period_end <  DATE '2025-11-01'\n"
        "   ORDER BY p.period_end DESC, a.description;\n"
        "\n"
        "5) User: \"Show all transactions from October 1 to October 31 2025.\"\n"
        "   SQL:\n"
        "   SELECT txn_date, description, vendor, category, signed_amount\n"
        "   FROM v_transactions_bi\n"
        "   WHERE user_id = :user_id\n"
        "     AND txn_date >= DATE '2025-10-01'\n"
        "     AND txn_date <  DATE '2025-11-01'\n"
        "   ORDER BY txn_date, txn_id;\n"
        "\n"
        "6) User: \"Show all transactions from Nov 11 to Nov 27.\"\n"
        "   SQL:\n"
        "   SELECT txn_date, description, vendor, category, signed_amount\n"
        "   FROM v_transactions_bi\n"
        "   WHERE user_id = :user_id\n"
        "     AND txn_date >= DATE '2025-11-11'\n"
        "     AND txn_date <  DATE '2025-11-28'\n"
        "   ORDER BY txn_date, txn_id;\n"
    )

    user = (
        history_block
        + "\n"
        + "User question (the latest one in the conversation):\n"
        f"{question}\n\n"
        "Return exactly ONE valid SQL SELECT statement that follows the rules."
    )

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    sql = resp.choices[0].message.content.strip()

    # Strip ```sql fences if present
    sql = re.sub(
        r"^```sql|^```|```$",
        "",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    ).strip()

    # Remove comments/blank lines
    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        if line.strip() == "":
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()

    if not cleaned:
        return None
    low = cleaned.lower()

    # Must start with SELECT or WITH (for CTEs)
    stripped = low.lstrip()
    if not (stripped.startswith("select") or stripped.startswith("with")):
        return None

    # Must include user_id filter somewhere
    if "user_id" not in low:
        return None

    # Ban dangerous verbs
    banned = [
        " insert ", " update ", " delete ", " drop ",
        " alter ", " truncate ", " create ", " grant ", " revoke ",
    ]
    if any(b in f" {low} " for b in banned):
        return None

    # Only allow a single statement
    parts = [p for p in cleaned.split(";") if p.strip()]
    if len(parts) > 1:
        return None

    # Fix common column-name mistakes
    cleaned = normalize_sql(cleaned)

    return cleaned


# ==============================================================
#  NATURAL LANGUAGE EXPLANATION (STYLE B)
# ==============================================================

def explain_result_nl(question: str, df: pd.DataFrame) -> str:
    """
    Turn raw SQL results into a structured, friendly financial summary.

    Changes:
    - If result is a single value (1 row x 1 col), answer in natural language
      instead of "count: 4".
    - Only treat a result as "top spending categories" if it *looks* aggregated
      (category + a numeric total with very few columns).
    - Otherwise fall back to the LLM explainer.
    """

    # No data case – don't call the model
    if df is None or df.empty:
        return (
            "I couldn’t find any matching data for that question in the "
            "statements you’ve uploaded so far."
        )

    lower_q = question.lower().strip()

    # 1️⃣ SINGLE VALUE → plain sentence, no table, no JSON
    if df.shape == (1, 1):
        col = df.columns[0]
        val = df.iloc[0, 0]

        # Handle "how many / count" style questions
        if "how many" in lower_q or "count" in lower_q or "number of" in lower_q:
            if "zelle" in lower_q:
                return f"You received {val} Zelle payments in the period covered by your statements."
            elif "transaction" in lower_q or "transactions" in lower_q:
                return f"I found {val} matching transactions for that question."
            else:
                return f"The answer to your question is {val} items."

        # Handle "how much / total" style questions
        if "how much" in lower_q or "total" in lower_q or "sum" in lower_q:
            if "zelle" in lower_q:
                return f"You received a total of {val} in Zelle payments."
            return f"Your total for this question is {val}."

        # Generic fallback
        return f"{col}: {val}"

    # 2️⃣ TOP SPENDING CATEGORIES → only when it *looks* aggregated
    cols_lower = [c.lower() for c in df.columns]

    if "category" in cols_lower and len(df.columns) <= 3:
        # Only treat as category summary if there are very few columns
        # (e.g., category + total), otherwise it's probably raw transactions.
        numeric_col = None
        for name in ["total_spent", "total", "sum", "amount", "amount_num", "signed_amount"]:
            if name in cols_lower:
                numeric_col = df.columns[cols_lower.index(name)]
                break

        if numeric_col is not None and "txn_date" not in cols_lower:
            cat_col = df.columns[cols_lower.index("category")]
            lines = ["Top spending categories:"]
            for idx, (_, row) in enumerate(df.iterrows(), start=1):
                cat = row[cat_col]
                amt = row[numeric_col]
                lines.append(f"{idx}. {cat} – {amt}")
            lines.append(
                "\nYou can ask things like:\n"
                "- \"Go deeper into Food\"\n"
                "- \"Show details for Shopping\"\n"
                "- \"Only Amazon inside Shopping\""
            )
            return "\n".join(lines)

    # 3️⃣ For everything else, use the LLM to describe the table nicely
    sample = df.head(30).copy()
    sample_rows = sample.to_dict(orient="records")

    system = """
You are the Finance Insights Assistant inside a personal finance chatbot.

You receive:
- The user’s natural-language questions.
- (Optionally) A brief summary of the SQL result or a sample of the rows.

Your job:
- Explain the answer in clear, friendly plain English.
- Offer helpful follow-up options.
- Do NOT show SQL, JSON, or Python objects.

GENERAL RULES
-------------
- Use short paragraphs and bullet points.
- Start with a brief summary (e.g., “I found 4 matching transactions, all from Zelle.”).
- You may then show a compact table-style description in text
  (dates, merchant, amount), but keep it concise.
- End with a couple of follow-up suggestions (e.g., “Do you want to see only this month?”).
-If many rows have placeholder values like "Unknown" vendor or "Uncategorised"
  category, do NOT highlight that as an insight. You can ignore those placeholders
  or just say that all transactions share the same category/vendor, without
  calling out the specific words "Unknown" or "Uncategorised"

TONE
----
- Neutral, non-judgmental, and supportive about spending.
- If data is missing or unclear, say so honestly and suggest what the user can try next.
"""

    payload = {
        "question": question,
        "rows": sample_rows,
    }

    user = json.dumps(payload, ensure_ascii=False, default=str)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()

