# app.py
import streamlit as st
import requests, time, os, re, json, hashlib, math
import pandas as pd
from io import StringIO
from typing import Dict, List, Any
from openai import OpenAI
from sqlalchemy import create_engine, text
import streamlit.components.v1 as components

# ==============================================================  
# 1) CONFIG  
# ==============================================================  
DOCSTRANGE_KEY = os.getenv("DOCSTRANGE_KEY", "e526e8c1-b067-11f0-b83f-a62e6d220688")
OPENAI_KEY     = os.getenv("OPENAI_KEY",     "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")

BASE = "https://extraction-api.nanonets.com"
HEAD = {"Authorization": f"Bearer {DOCSTRANGE_KEY}"}
client = OpenAI(api_key=OPENAI_KEY)

MODEL = "gpt-4.1-mini"

# Neon DB (SQLAlchemy-compatible)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://neondb_owner:npg_WZCgK7qno1SO@ep-tiny-fire-ahu53e2e-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)
engine = create_engine(DATABASE_URL)

DEBIT_SECTIONS = [
    "Account Summary",
    "Deposits and other additions",
    "ATM and debit card subtractions",
    "Other subtractions",
]

CREDIT_SECTIONS = [
    "Account Summary",
    "Payment Information",
    "Account Summary/Payment Information",   # unified
    "Payments and Other Credits",
    "Purchases and Adjustments",
    "Fees",
    "Interest Charged",
]

SECTIONS_TO_ENRICH = {
    "Payments and Other Credits",
    "Purchases and Adjustments",
    "ATM and debit card subtractions",
    "Other subtractions",
}

SYSTEM_PROMPT = """
You are a precise financial statement parser.

You will receive the full markdown text of a BANK OF AMERICA statement
(converted from PDF) that may be either:
- a DEBIT (checking) statement, or
- a CREDIT CARD statement.

Your job:

1. First, decide if it is a DEBIT or CREDIT statement.
   - DEBIT clues: "Deposits and other additions", "ATM and debit card subtractions",
     "Other subtractions", "Adv SafeBalance Banking", "Bank deposit accounts".
   - CREDIT clues: "Account Summary/Payment Information", "Purchases and Adjustments",
     "Fees Charged", "Interest Charged", "Total Credit Line",
       "Payments and Other Credits".

2. Based on the type, extract ONLY these sections.

DEBIT STATEMENT → SECTIONS
--------------------------
Create these sections:

  a) account_summary
     - Columns: ["Description", "Amount"]

  b) deposits_and_other_additions
     - Columns: ["Date", "Description", "Amount"]

  c) atm_and_debit_card_subtractions
     - Columns: ["Date", "Description", "Amount"]

  d) other_subtractions
     - Columns: ["Date", "Description", "Amount"]

If there is only a total (no detail table) for a section, still create that
section with a single row: Date="", Description=that label, Amount=the total.

CREDIT STATEMENT → SECTIONS
---------------------------
Create these sections where applicable:

  a) account_summary
     - Columns: ["Description", "Amount"]
     - Include "Payment Due Date" as a row if present.

  b) payments_and_other_credits
     - Columns: ["Date", "Description", "Amount"]

  c) purchases_and_adjustments
     - Columns: ["Date", "Description", "Amount"]

  d) fees
     - Columns: ["Date", "Description", "Amount"]

  e) interest_charged
     - Columns: ["Date", "Description", "Amount"]

IMPORTANT RULES
---------------
- Do NOT invent transactions or amounts.
  Only use what is present in the statement text.

- Amounts should be numeric strings without "$" or commas, but keep the sign
  (e.g. "-73.68", "1600.00").

OUTPUT FORMAT (STRICT JSON)
---------------------------
Return a SINGLE valid JSON object with this structure:

{
  "statement_type": "debit" or "credit",
  "sections": {
    "<section_name>": {
      "columns": [...],
      "rows": [
        [...],
        ...
      ]
    },
    ...
  }
}

Where <section_name> is a short identifier such as:
  account_summary,
  deposits_and_other_additions,
  atm_and_debit_card_subtractions,
  other_subtractions,
  payments_and_other_credits,
  purchases_and_adjustments,
  fees,
  interest_charged.

Notes:
- If a section does not apply or you cannot find it, omit that key from "sections".
- The JSON must be valid and parseable.
- Do NOT wrap the JSON in Markdown or backticks.
- Do NOT include any extra explanation or text outside the JSON.
"""

# ==============================================================  
# 2) AUTH HELPERS (USERS TABLE)  
# ==============================================================  

def hash_password(password: str) -> str:
    """Simple SHA256 hash. (Good enough for project demo.)"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_user_by_email(email: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, password_hash FROM users WHERE email = :e"),
            {"e": email.strip().lower()},
        ).fetchone()
    return row


def create_user(email: str, password: str):
    email_norm = email.strip().lower()
    pwd_hash = hash_password(password)
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                INSERT INTO users (email, password_hash)
                VALUES (:email, :ph)
                RETURNING id, email, password_hash
            """),
            {"email": email_norm, "ph": pwd_hash},
        ).fetchone()
        conn.commit()
    return row


def validate_credentials(email: str, password: str):
    row = get_user_by_email(email)
    if not row:
        return None
    if hash_password(password) != row.password_hash:
        return None
    return row  # has id, email, password_hash


def require_login():
    """Show login/register UI until user is authenticated."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return

    st.title("🔐 Login")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

        if submitted:
            user = validate_credentials(email, password)
            if user:
                st.session_state.authenticated = True
                st.session_state.user_id = user.id
                st.session_state.user_email = user.email
                st.rerun()
            else:
                st.error("Invalid email or password")

    with tab_register:
        with st.form("register_form"):
            new_email = st.text_input("Email", key="reg_email")
            pwd1 = st.text_input("Password", type="password", key="reg_pwd1")
            pwd2 = st.text_input("Confirm Password", type="password", key="reg_pwd2")
            submitted_reg = st.form_submit_button("Create account")

        if submitted_reg:
            if not new_email or not pwd1:
                st.error("Email and password are required.")
            elif pwd1 != pwd2:
                st.error("Passwords do not match.")
            elif get_user_by_email(new_email):
                st.error("An account with this email already exists.")
            else:
                user = create_user(new_email, pwd1)
                st.session_state.authenticated = True
                st.session_state.user_id = user.id
                st.session_state.user_email = user.email
                st.success("Account created. You are now logged in.")
                st.rerun()

    # Prevent rest of app from running
    st.stop()


def init_db():
    with engine.connect() as conn:
        # 1) USERS TABLE
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            );
        """))

        # 2) STATEMENTS TABLE (create if missing)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS statements (
                id SERIAL PRIMARY KEY,
                sha256 TEXT NOT NULL,
                original_filename TEXT,
                statement_type TEXT,
                uploaded_at TIMESTAMPTZ DEFAULT now(),
                user_id INTEGER REFERENCES users(id)
            );
        """))

        # If statements already existed from old version, add user_id
        conn.execute(text("""
            ALTER TABLE statements
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
        """))

        # 3) STATEMENT_ROWS TABLE (create if missing)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS statement_rows (
                id SERIAL PRIMARY KEY,
                "Date" TEXT,
                "Transaction Date" TEXT,
                "Posting Date" TEXT,
                "Description" TEXT,
                "Amount" TEXT,
                "Vendor" TEXT,
                "Category" TEXT,
                statement_name TEXT,
                statement_type TEXT,
                section_name TEXT,
                statement_id INTEGER REFERENCES statements(id),
                user_id INTEGER REFERENCES users(id)
            );
        """))

        # If statement_rows already existed from old version, add user_id
        conn.execute(text("""
            ALTER TABLE statement_rows
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
        """))

        # 4) Drop old unique constraint on sha256 if it exists
        conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'statements_sha256_key'
                ) THEN
                    ALTER TABLE statements DROP CONSTRAINT statements_sha256_key;
                END IF;
            END$$;
        """))

        # 5) New unique index per user + sha256
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_statements_user_sha
            ON statements(user_id, sha256);
        """))

        conn.commit()


# Initialize DB (tables + constraints)
init_db()

# ==============================================================  
# 3) COMMON UTILITIES  
# ==============================================================  

def extract_markdown_blob(file_bytes: bytes, filename: str) -> str:
    files = {"file": (filename, file_bytes, "application/pdf")}
    data = {"output_type": "markdown"}
    res = requests.post(f"{BASE}/extract", headers=HEAD, files=files, data=data)
    res.raise_for_status()
    record_id = res.json().get("record_id")
    if not record_id:
        raise RuntimeError("No record_id returned from Docstrange.")
    for _ in range(20):
        time.sleep(3)
        r = requests.get(f"{BASE}/files/{record_id}", headers=HEAD)
        r.raise_for_status()
        payload = r.json()
        status = payload.get("processing_status") or payload.get("status")
        if status == "completed":
            content = payload.get("content", "")
            if not content.strip():
                raise RuntimeError("Extraction completed, but content is empty.")
            return content
        if status == "failed":
            raise RuntimeError("Docstrange extraction failed.")
    raise TimeoutError("Extraction timed out.")


def clean_amount_string(x: str) -> str:
    s = str(x).strip().replace("$", "").replace(",", "")
    if re.fullmatch(r"\(.*\)", s):
        s = "-" + s.strip("()")
    s = re.sub(r"^\+?\s*", "", s)
    return s


def _clean_raw_amount_or_text(s: str) -> str:
    s = s.strip()
    s = s.replace("$", "").replace(",", "")
    if re.fullmatch(r"\(.*\)", s):
        s = "-" + s.strip("()")
    return s


def fallback_credit_account_summary(md_text: str) -> pd.DataFrame:
    rows = []

    def grab(label: str, pattern: str, is_amount: bool = True):
        m = re.search(pattern, md_text, flags=re.IGNORECASE)
        if not m:
            return
        val = m.group(1).strip()
        if is_amount:
            val = _clean_raw_amount_or_text(val)
        rows.append({"Description": label, "Amount": val})

    grab(
        "Payment Due Date",
        r"Payment\s+Due\s+Date\s*[:\-]?\s*([0-9/]{4,10}|[A-Za-z]+\s+\d{1,2},\s*\d{4})",
        is_amount=False,
    )
    grab(
        "New Balance Total",
        r"New\s+Balance\s*Total\s*[:\-]?\s*\$?\s*([0-9,.\(\)]+)",
        is_amount=True,
    )
    grab(
        "Minimum Payment Due",
        r"Minimum\s+Payment\s+Due\s*[:\-]?\s*\$?\s*([0-9,.\(\)]+)",
        is_amount=True,
    )
    grab(
        "Total Credit Line",
        r"Total\s+Credit\s+Line\s*[:\-]?\s*\$?\s*([0-9,.\(\)]+)",
        is_amount=True,
    )
    grab(
        "Total Credit Available",
        r"Total\s+Credit\s+Available\s*[:\-]?\s*\$?\s*([0-9,.\(\)]+)",
        is_amount=True,
    )

    if not rows:
        return pd.DataFrame(columns=["Description", "Amount"])

    df_fb = pd.DataFrame(rows, columns=["Description", "Amount"])
    return df_fb


def call_llm_for_json(md_text: str) -> Dict[str, Any]:
    user_prompt = f"""
Here is the full statement markdown:

{md_text}

Decide if it is DEBIT or CREDIT and return ONLY the JSON object as specified.
"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print("Raw LLM output (truncated):")
        print(content[:1000])
        raise RuntimeError(f"Failed to parse LLM JSON: {e}")

    return data


def map_json_section_name(section_key: str, statement_type: str) -> str:
    key = section_key.strip().lower()
    if statement_type == "debit":
        mapping = {
            "account_summary": "Account Summary",
            "deposits_and_other_additions": "Deposits and other additions",
            "atm_and_debit_card_subtractions": "ATM and debit card subtractions",
            "other_subtractions": "Other subtractions",
        }
    else:  # credit
        mapping = {
            "account_summary": "Account Summary/Payment Information",
            "payments_and_other_credits": "Payments and Other Credits",
            "purchases_and_adjustments": "Purchases and Adjustments",
            "fees": "Fees",
            "interest_charged": "Interest Charged",
        }
    return mapping.get(key, section_key)

# ==============================================================  
# 4) ENRICHMENT  
# ==============================================================  

def llm_vendor_category(descriptions: List[str]) -> List[Dict[str, str]]:
    if not descriptions:
        return []

    system = (
        "You are a financial transaction labeler. "
        "For each transaction description, extract two fields:\n"
        "vendor   = short, clean brand/merchant name (no store numbers, city/state, or codes).\n"
        "category = concise, human-friendly label describing the expense type "
        "(e.g., Groceries, Restaurant, Rideshare, Utilities, Online Purchase, "
        "Cinema, Entertainment, Clothing, Donation, Membership, Travel, Other, etc.).\n"
        "\n"
        "Guidelines:\n"
        "- Only use 'Donation' if the text clearly indicates a charitable or religious purpose.\n"
        "- If the purpose is unclear or the vendor is unknown, use category 'Other'.\n"
        "- Keep answers short and natural. No explanations.\n"
        "Return ONLY a JSON array of objects: [{\"vendor\": ..., \"category\": ...}], "
        "same order and length as the input list."
    )

    user = "Descriptions:\n" + "\n".join(f"- {d}" for d in descriptions)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",  "content": user},
            ],
        )
        txt = re.sub(
            r"^```json|```$",
            "",
            resp.choices[0].message.content.strip(),
            flags=re.MULTILINE,
        ).strip()
        arr = json.loads(txt)
        if isinstance(arr, list) and len(arr) == len(descriptions):
            return [
                {
                    "vendor":   str(o.get("vendor", "")).strip(),
                    "category": str(o.get("category", "")).strip(),
                }
                for o in arr
            ]
    except Exception:
        pass

    return [{"vendor": "", "category": "Other"} for _ in descriptions]


def enrich_df(section_name: str, df: pd.DataFrame) -> pd.DataFrame:
    if section_name not in SECTIONS_TO_ENRICH or "Description" not in df.columns:
        return df

    ren = {}
    for c in df.columns:
        lc = c.lower()
        if lc == "date":
            ren[c] = "Date"
        elif lc == "transaction date":
            ren[c] = "Transaction Date"
        elif lc == "posting date":
            ren[c] = "Posting Date"
        elif lc == "description":
            ren[c] = "Description"
        elif lc == "amount":
            ren[c] = "Amount"
    if ren:
        df = df.rename(columns=ren)

    if "Amount" in df.columns:
        df["Amount"] = df["Amount"].map(clean_amount_string)

    descs = df["Description"].astype(str).fillna("").tolist()
    results: List[Dict[str, str]] = []
    BATCH = 40
    for i in range(0, len(descs), BATCH):
        results.extend(llm_vendor_category(descs[i:i+BATCH]))

    vendors = [r.get("vendor", "") for r in results]
    cats    = [r.get("category", "Other") for r in results]

    if "Vendor" in df.columns:
        df.drop(columns=["Vendor"], inplace=True)
    if "Category" in df.columns:
        df.drop(columns=["Category"], inplace=True)

    df.insert(len(df.columns), "Vendor", vendors)
    df.insert(len(df.columns), "Category", cats)
    return df

# ==============================================================  
# 5) DB HELPERS (NOW PER USER)  
# ==============================================================  

def get_statement_by_hash(sha256_hex: str, user_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, sha256, original_filename, statement_type, user_id "
                "FROM statements WHERE sha256 = :sha AND user_id = :uid"
            ),
            {"sha": sha256_hex, "uid": user_id},
        ).fetchone()
    return row


def create_statement_record(
    sha256_hex: str,
    filename: str,
    statement_type: str,
    user_id: int,
):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO statements (sha256, original_filename, statement_type, user_id)
                VALUES (:sha, :filename, :stype, :uid)
                ON CONFLICT (user_id, sha256)
                DO UPDATE SET statement_type = EXCLUDED.statement_type,
                              original_filename = EXCLUDED.original_filename
                RETURNING id, sha256, original_filename, statement_type, user_id
                """
            ),
            {
                "sha": sha256_hex,
                "filename": filename,
                "stype": statement_type,
                "uid": user_id,
            },
        ).fetchone()
        conn.commit()
    return row


def write_section_to_db(
    section_name: str,
    df: pd.DataFrame,
    base_name: str,
    statement_type: str,
    statement_id: int,
    user_id: int,
):
    df2 = df.copy()

    for col in [
        "Date", "Transaction Date", "Posting Date",
        "Description", "Amount", "Vendor", "Category"
    ]:
        if col not in df2.columns:
            df2[col] = None

    df2["statement_name"] = base_name
    df2["statement_type"] = statement_type
    df2["section_name"]   = section_name
    df2["statement_id"]   = statement_id
    df2["user_id"]        = user_id

    df2.to_sql("statement_rows", engine, if_exists="append", index=False)

# ==============================================================  
# 6) CHATBOT SQL STUFF  
# ==============================================================  

SCHEMA_TEXT = """
You can ONLY use these Postgres tables and views:

TABLE statements(
    id                integer primary key,
    sha256            text,
    original_filename text,
    statement_type    text,          -- 'credit' or 'debit'
    uploaded_at       timestamptz,
    user_id           integer
);

TABLE statement_rows(
    id                 integer primary key,
    "Date"             text,
    "Transaction Date" text,
    "Posting Date"     text,
    "Description"      text,
    "Amount"           text,          -- signed numeric string
    "Vendor"           text,
    "Category"         text,
    statement_name     text,
    statement_type     text,          -- 'credit' or 'debit'
    section_name       text,
    statement_id       integer,
    user_id            integer
);

VIEW v_expenses(
    id,
    statement_id,
    statement_name,
    statement_type,
    section_name,
    "Date",
    "Transaction Date",
    "Posting Date",
    description,
    amount,        -- numeric, typically negative for expenses
    vendor,
    category,
    txn_date,      -- date
    user_id
);

VIEW v_income(
    id,
    statement_id,
    statement_name,
    statement_type,
    section_name,
    "Date",
    "Transaction Date",
    "Posting Date",
    description,
    amount,        -- numeric, positive for income
    vendor,
    category,
    txn_date,      -- date
    user_id
);

VIEW v_account_summary(
    id,
    statement_id,
    statement_name,
    statement_type,
    section_name,
    "Description",
    amount,        -- numeric
    user_id
);

VIEW v_statement_summary(
    statement_id,
    statement_type,
    statement_name,
    period_start,   -- date
    period_end,     -- date
    total_income,   -- numeric
    total_expense,  -- numeric
    savings,        -- numeric
    user_id
);

VIEW v_monthly_summary(
    month,          -- date (first day of month)
    user_id,
    total_income,   -- numeric
    total_expense,  -- numeric
    savings         -- numeric
);

SEMANTICS / HOW TO USE:
- v_expenses  = one row per expense/outflow transaction (spend).
- v_income    = one row per income/inflow transaction.
- v_monthly_summary = aggregated totals per calendar month.
- v_statement_summary = aggregated totals per statement period.
- v_account_summary  = raw statement “Account Summary” lines.

IMPORTANT RULES:
- Every query MUST filter on user_id = :user_id on the main table or view.
- NEVER select or return the user_id column; just use it in WHERE.
- Use only the columns defined above. Do NOT invent new columns like 'signed_amount',
  'amount_num', 'month_start', 'txn_month', etc.
- For expense / spending questions, prefer v_expenses.
- For income / deposits questions, prefer v_income.
- For monthly totals or “latest month you have”, prefer v_monthly_summary.
- For “statement period” questions, prefer v_statement_summary.
- For overall coverage / time range, you may use MIN/MAX of txn_date across v_expenses and v_income,
  or use the month column in v_monthly_summary.
"""


def generate_sql_from_question(question: str) -> str | None:
    """
    Use GPT to turn a natural language question into a single safe SELECT query.
    """

    system = (
        "You are a Postgres SQL generator for a personal finance app.\n"
        "You receive a natural language question about the user's past transactions and must respond with exactly ONE SQL SELECT query.\n"
        "You are NOT allowed to modify data. Do not use INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.\n"
        "Use only the tables and views listed in the schema below.\n"
        "Return ONLY the SQL, no backticks, no explanation, no comments.\n\n"
        f"{SCHEMA_TEXT}\n\n"
        "HOW TO CHOOSE VIEWS / PATTERNS:\n"
        "1) COVERAGE / TIME RANGE QUESTIONS -> use MIN/MAX txn_date from v_expenses + v_income.\n"
        "2) MONTHLY SUMMARY / LATEST MONTH -> use v_monthly_summary.\n"
        "3) SPENDING / CATEGORY / VENDOR -> use v_expenses.\n"
        "4) INCOME -> use v_income.\n"
        "5) STATEMENT-LEVEL -> use v_statement_summary.\n"
        "6) LARGEST TRANSACTIONS -> use v_expenses ORDER BY ABS(amount) DESC.\n"
        "7) RECURRING TRANSACTIONS -> group v_expenses by vendor with COUNT>=3.\n"
        "Always include user_id = :user_id in WHERE.\n"
    )

    user = f"""
User question:
{question}

Requirements:
- Return exactly ONE valid SELECT statement.
- Do not include comments or any text outside the SQL.
- Do not wrap the SQL in markdown fences.
"""

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",  "content": user},
        ],
    )

    sql = resp.choices[0].message.content.strip()

    # Strip ```sql fences if present
    sql = re.sub(r"^```sql|^```|```$", "", sql, flags=re.IGNORECASE | re.MULTILINE).strip()

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

    # Must start with SELECT
    if not low.lstrip().startswith("select"):
        return None

    # Must include user_id filter somewhere
    if "user_id" not in low:
        return None

    # Ban dangerous verbs
    banned = [
        " insert ", " update ", " delete ", " drop ", " alter ",
        " truncate ", " create ", " grant ", " revoke "
    ]
    if any(b in f" {low} " for b in banned):
        return None

    # Only allow a single statement
    parts = [p for p in cleaned.split(";") if p.strip()]
    if len(parts) > 1:
        return None

    return cleaned


def explain_result_nl(question: str, df: pd.DataFrame) -> str:
    """
    Turn raw result into a short explanation with GPT.
    """
    sample_rows = df.head(20).to_dict(orient="records")
    system = (
        "You are a helpful personal finance assistant. "
        "Given the user's question and a small result table, "
        "explain the answer in 1–3 short sentences. Be clear and concise."
    )
    user = json.dumps(
        {"question": question, "rows": sample_rows},
        ensure_ascii=False,
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()

# ==============================================================  
# 7) CHAT PAGE (NEW UI: CUSTOM BUBBLES + UPLOAD IN INPUT BAR)  
# ==============================================================  

def run_chat_and_upload_page():
    """Chat-first interface with PDF upload inside the input bar + custom chat bubbles."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("You must be logged in.")
        return

    # Helpers for chat rendering
    def bot_msg(text: str):
        st.markdown(f'<div class="chat-bot">{text}</div>', unsafe_allow_html=True)

    def user_msg(text: str):
        st.markdown(f'<div class="chat-user">{text}</div>', unsafe_allow_html=True)

    def user_has_data(uid: int) -> bool:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM statement_rows WHERE user_id = :uid"),
                {"uid": uid},
            ).scalar()
        return count > 0

    # Top bar
    st.markdown(
        """
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.6rem;">
            <div class="top-bar-title">
                💬 Spending & Savings Assistant
            </div>
            <div class="top-bar-sub">
                Ask about past transactions or upload a new statement.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Session state for chat messages + pending suggestion
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_query" not in st.session_state:
        st.session_state.pending_query = None

    # If first time, add greeting
    if not st.session_state.messages:
        st.session_state.messages.append({
            "role": "assistant",
            "content": (
                "Hi Tejaswini 👋<br>"
                "You can ask things like:<br>"
                "• <i>How much did I spend on food last month?</i><br>"
                "• <i>What’s my biggest transaction this month?</i><br>"
                "• <i>Show my total savings this year.</i>"
            )
        })

    # Card container
    st.markdown('<div class="app-card">', unsafe_allow_html=True)

    # ---------- Quick suggestion chips (WAYS I CAN HELP) ----------
    has_data = user_has_data(user_id)

    if has_data:
        suggestion_texts = [
            "Summarize my spending for the latest month you have.",
            "Show my spending by month over all the data you have.",
            "Show my largest transactions over the whole period.",
            "Show my recurring transactions or subscriptions.",
            "What time period of transactions do you have for me?"
        ]
    else:
        suggestion_texts = [
            "How do I get started?",
            "What types of statements can I upload?",
            "What can you do with my statements?",
            "Is my data safe?"
        ]

    st.markdown('<div class="suggestion-label">WAYS I CAN HELP</div>', unsafe_allow_html=True)
    st.markdown('<div class="suggestion-row">', unsafe_allow_html=True)

    # layout: buttons in rows of 3
    sugg_cols = st.columns(min(3, len(suggestion_texts)))
    for idx, sugg in enumerate(suggestion_texts):
        col = sugg_cols[idx % len(sugg_cols)]
        if col.button(sugg, key=f"sugg_{idx}"):
            st.session_state.pending_query = sugg
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- CHAT HISTORY AREA ----------
    st.markdown('<div class="chat-box">', unsafe_allow_html=True)
    for msg in st.session_state.messages:
        if msg["role"] == "assistant":
            bot_msg(msg["content"])
        else:
            user_msg(msg["content"])
    st.markdown('</div>', unsafe_allow_html=True)

    # ---------- BOTTOM INPUT BAR (UPLOAD + TEXT + SEND) ----------
    st.markdown('<div class="chat-input-wrapper">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([0.7, 6, 1.2])

    with c1:
        uploaded_file = st.file_uploader(
            " ",
            type=["pdf"],
            key="chat_pdf_upload",
            label_visibility="collapsed",
        )

    with c2:
        user_text = st.text_input(
            "Type your question",
            value=st.session_state.pending_query or "",
            placeholder="Ask about your spending, savings, or a specific vendor…",
            label_visibility="collapsed"
        )

    with c3:
        send_clicked = st.button("Send", use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # Clear pending query now that it's copied into the input
    st.session_state.pending_query = None

    # ---------- HANDLE EVENTS ----------
    triggered = send_clicked or (uploaded_file is not None)

    if triggered and (user_text or uploaded_file):
        # Build user message for display
        display_text = user_text.strip() if user_text else ""
        if uploaded_file is not None:
            if display_text:
                display_text += f"<br>📄 Attached: {uploaded_file.name}"
            else:
                display_text = f"📄 Uploaded statement: {uploaded_file.name}"

        # Append user message to history
        st.session_state.messages.append({"role": "user", "content": display_text})

        # Process uploaded statement if present
        processing_message = ""
        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            sha256_hex = hashlib.sha256(file_bytes).hexdigest()

            existing_stmt = get_statement_by_hash(sha256_hex, user_id)
            existing_stmt_id = None
            existing_row_count = 0

            if existing_stmt:
                existing_stmt_id = existing_stmt.id
                with engine.connect() as conn:
                    existing_row_count = conn.execute(
                        text("""
                            SELECT COUNT(*)
                            FROM statement_rows
                            WHERE statement_id = :sid AND user_id = :uid
                        """),
                        {"sid": existing_stmt_id, "uid": user_id},
                    ).scalar()

            if existing_stmt and existing_row_count > 0:
                processing_message = (
                    "✅ I already have that statement on file — you can ask about those "
                    "transactions anytime."
                )
            else:
                with st.spinner("Processing your statement…"):
                    try:
                        md_text = extract_markdown_blob(file_bytes, uploaded_file.name)
                        json_data = call_llm_for_json(md_text)

                        auto_type = (json_data.get("statement_type") or "debit").lower()
                        if auto_type not in ("debit", "credit"):
                            auto_type = "debit"
                        stype = auto_type

                        base_name = os.path.splitext(os.path.basename(uploaded_file.name))[0]

                        stmt_row = create_statement_record(
                            sha256_hex=sha256_hex,
                            filename=uploaded_file.name,
                            statement_type=stype,
                            user_id=user_id,
                        )
                        statement_id = stmt_row.id

                        sections_json: Dict[str, Any] = json_data.get("sections", {}) or {}
                        if not sections_json:
                            processing_message = (
                                "❌ I couldn't find any usable sections in that statement."
                            )
                        else:
                            saved_sections: List[str] = []

                            for raw_key, section_obj in sections_json.items():
                                try:
                                    cols = section_obj.get("columns") or []
                                    rows = section_obj.get("rows") or []

                                    if not cols or not isinstance(rows, list):
                                        continue

                                    cleaned_rows: List[List[Any]] = []
                                    for r in rows:
                                        if not isinstance(r, list):
                                            continue
                                        if len(r) < len(cols):
                                            r = r + [""] * (len(cols) - len(r))
                                        elif len(r) > len(cols):
                                            r = r[:len(cols)]
                                        cleaned_rows.append(r)

                                    if not cleaned_rows:
                                        continue

                                    df = pd.DataFrame(cleaned_rows, columns=cols)

                                    # Normalize common columns
                                    ren = {}
                                    for c in df.columns:
                                        lc = c.strip().lower()
                                        if lc == "date":
                                            ren[c] = "Date"
                                        elif lc == "transaction date":
                                            ren[c] = "Transaction Date"
                                        elif lc == "posting date":
                                            ren[c] = "Posting Date"
                                        elif lc == "description":
                                            ren[c] = "Description"
                                        elif lc == "amount":
                                            ren[c] = "Amount"
                                    if ren:
                                        df = df.rename(columns=ren)

                                    if "Amount" in df.columns:
                                        df["Amount"] = df["Amount"].map(clean_amount_string)

                                    canonical_name = map_json_section_name(raw_key, stype)

                                    # Credit: ensure summary lines exist
                                    if (
                                        stype == "credit"
                                        and canonical_name == "Account Summary/Payment Information"
                                        and "Description" in df.columns
                                    ):
                                        has_pdd = df["Description"].astype(str).str.contains(
                                            "Payment Due Date", case=False, na=False
                                        ).any()

                                        if not has_pdd:
                                            fb_df = fallback_credit_account_summary(md_text)
                                            if not fb_df.empty:
                                                existing_desc = set(
                                                    df["Description"].astype(str)
                                                    .str.strip()
                                                    .str.lower()
                                                )
                                                fb_df = fb_df[
                                                    ~fb_df["Description"]
                                                    .astype(str)
                                                    .str.strip()
                                                    .str.lower()
                                                    .isin(existing_desc)
                                                ]
                                                if not fb_df.empty:
                                                    df = pd.concat([df, fb_df], ignore_index=True)

                                    # Enrich & write to DB
                                    df = enrich_df(canonical_name, df)

                                    write_section_to_db(
                                        section_name=canonical_name,
                                        df=df,
                                        base_name=base_name,
                                        statement_type=stype,
                                        statement_id=statement_id,
                                        user_id=user_id,
                                    )

                                    saved_sections.append(canonical_name)

                                except Exception as ex:
                                    print(f"Could not process section '{raw_key}': {ex}")

                            if saved_sections:
                                processing_message = (
                                    "✅ Statement processed successfully. "
                                    "You can now ask things like:<br>"
                                    "• \"How much did I spend in that statement period?\"<br>"
                                    "• \"What were my top 5 vendors there?\""
                                )
                            else:
                                processing_message = (
                                    "❌ No sections were successfully stored from this statement."
                                )

                    except Exception as e:
                        print("Upload processing error:", e)
                        processing_message = (
                            "❌ Something went wrong while processing your statement."
                        )

        # If user also asked a question, run SQL Q&A
        answer_text = ""
        result_df = None

        if user_text:
            with st.spinner("Thinking and running your query..."):
                sql = generate_sql_from_question(user_text)

            if not sql:
                answer_text = (
                    "I couldn't generate a safe SQL query for that question. "
                    "Try rephrasing it or ask something simpler."
                )
            else:
                try:
                    with engine.connect() as conn:
                        result = conn.execute(text(sql), {"user_id": user_id})
                        rows = result.fetchall()
                        cols = result.keys()
                except Exception as e:
                    answer_text = f"❌ Error running SQL: {e}"
                else:
                    if not rows:
                        answer_text = "No data returned for this question."
                    else:
                        result_df = pd.DataFrame(rows, columns=cols)
                        try:
                            answer_text = explain_result_nl(user_text, result_df)
                        except Exception:
                            answer_text = "Here are the results I found for your question."

        # Combine processing message + answer_text into one assistant bubble
        combined_reply_parts = []
        if processing_message:
            combined_reply_parts.append(processing_message)
        if answer_text:
            combined_reply_parts.append(answer_text)
        combined_reply = "<br><br>".join(combined_reply_parts) if combined_reply_parts else ""

        if combined_reply:
            st.session_state.messages.append(
                {"role": "assistant", "content": combined_reply}
            )

        # Show DataFrame inline under the last assistant message (if any)
        if result_df is not None and not result_df.empty:
            # We still show raw table below bubbles
            st.markdown('<div class="chat-bot">Raw results:</div>', unsafe_allow_html=True)
            st.dataframe(result_df, use_container_width=True)

        # Rerun to refresh UI
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # close app-card

# ==============================================================  
# 8) GLOBAL STYLES + MAIN APP  
# ==============================================================  

def apply_custom_styles():
    st.markdown(
        """
        <style>
        /* Overall dark blue background */
        body, .main, .stApp {
            background: radial-gradient(circle at top, #0b1f3a 0, #020617 55%, #000000 100%);
        }

        /* Narrower content */
        .main {
            padding-left: 2.5rem;
            padding-right: 2.5rem;
            padding-top: 1.2rem;
        }

        /* Card container for chat + other pages */
        .app-card {
            background-color: rgba(15,23,42,0.92);
            border-radius: 22px;
            padding: 18px 20px 10px 20px;
            border: 1px solid #1e293b;
            box-shadow: 0 14px 40px rgba(0,0,0,0.6);
        }

        /* Chat area box */
        .chat-box {
            border-radius: 16px;
            padding: 8px 4px 8px 0px;
            max-height: 520px;
            overflow-y: auto;
            margin-top: 0.4rem;
            margin-bottom: 0.4rem;
        }

        /* Chat bubbles */
        .chat-bot {
            background: #0f172a;
            padding: 10px 14px;
            border-radius: 14px;
            max-width: 80%;
            margin-bottom: 8px;
            font-size: 0.95rem;
            color: #e5e7eb;
        }
        .chat-user {
            background: #22c55e;
            padding: 10px 14px;
            border-radius: 14px;
            max-width: 80%;
            margin-bottom: 8px;
            margin-left: auto;
            text-align: right;
            font-size: 0.95rem;
            color: #022c22;
        }

        /* ---------- ChatGPT-style bottom input bar ---------- */
        .chat-input-wrapper {
            border: 1px solid #1f2933;
            border-radius: 999px;
            padding: 8px 12px;
            background: #050816;
            margin-top: 0.8rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        /* Compress the file uploader column */
        .chat-input-wrapper [data-testid="stFileUploader"] {
            max-width: 44px !important;
            min-width: 44px !important;
        }

        /* Turn the Streamlit dropzone into a small round icon */
        .chat-input-wrapper [data-testid="stFileUploadDropzone"] {
            width: 40px !important;
            height: 40px !important;
            padding: 0 !important;
            margin: 0 !important;
            border-radius: 50% !important;
            border: 1px solid #4b5563 !important;
            background: #020617 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }

        /* Hide ALL children inside the dropzone */
        .chat-input-wrapper [data-testid="stFileUploadDropzone"] * {
            display: none !important;
        }

        /* Show only a 📎 icon */
        .chat-input-wrapper [data-testid="stFileUploadDropzone"]::before {
            content: "📎";
            font-size: 18px;
            color: #e5e7eb;
            display: block !important;
        }

        /* Text input styling inside bar */
        .stTextInput div[data-baseweb="input"] > div {
            background: transparent;
            color: #e5e7eb;
        }
        .stTextInput input {
            border: none !important;
            box-shadow: none !important;
        }

        /* Suggestion chips */
        .suggestion-label {
            font-size: 0.75rem;
            letter-spacing: 0.08em;
            color: #9ca3af;
            text-transform: uppercase;
            margin-top: 0.75rem;
            margin-bottom: 0.15rem;
        }
        .suggestion-row button {
            border-radius: 999px !important;
            border: 1px solid #3b82f6 !important;
            padding: 0.3rem 0.9rem !important;
            font-size: 0.82rem !important;
        }

        /* Top bar */
        .top-bar-title {
            font-size: 0.95rem;
            font-weight: 600;
            color: #e5e7eb;
        }
        .top-bar-sub {
            font-size: 0.8rem;
            color: #9ca3af;
        }

        /* Expander (if you use it anywhere else) */
        .stExpander {
            border-radius: 14px !important;
            border: 1px solid #1e293b !important;
            background-color: #020617 !important;
            margin-bottom: 0.6rem !important;
        }

        /* Sidebar tweaks */
        section[data-testid="stSidebar"] {
            background-color: #020617 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="🏦 Finance Chatbot", page_icon="💰", layout="wide")
apply_custom_styles() 

# 🔐 Require login first
require_login()

# Top-level layout: keep it subtle; main hero is the chat card
st.sidebar.title("Navigation")
current_user = st.session_state.get("user_email", "Unknown user")
st.sidebar.write(f"Logged in as: **{current_user}**")

if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.rerun()

page = st.sidebar.radio(
    "Go to:",
    ["💬 Chat + Upload", "📊 Dashboard", "🎯 Smart Financial Coach"]
)

if page == "💬 Chat + Upload":
    run_chat_and_upload_page()

elif page == "📊 Dashboard":
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.subheader("📊 Financial Dashboard (Power BI)")
    POWERBI_URL = "https://app.powerbi.com/view?r=eyJrIjoiYmVkZDk4OGQtZjBiNy00M2M1LTg5NzYtZGZiYzAzZGY4Yzc5IiwidCI6IjhjMWUzMmJlLWY0NzgtNDAzYi05NWFmLTVlNjRkN2EwNDk1ZSIsImMiOjF9"
    st.markdown(
        "This dashboard is built on top of the same Neon database "
        "that powers your chatbot. Refresh in Power BI to see new statements."
    )
    components.iframe(POWERBI_URL, height=800, scrolling=True)
    st.markdown('</div>', unsafe_allow_html=True)

elif page == "🎯 Smart Financial Coach":
    st.markdown('<div class="app-card">', unsafe_allow_html=True)
    st.subheader("🎯 Smart Financial Coach")
    st.write("Coming soon – personalized tips based on your spending and savings.")
    st.markdown('</div>', unsafe_allow_html=True)
