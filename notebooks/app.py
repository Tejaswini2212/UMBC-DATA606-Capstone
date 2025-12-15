# app.py

import os
import json
import hashlib
import time

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from db_helpers import (
    engine,
    init_db,
    get_user_by_email,
    create_user,
    validate_credentials,
    get_statement_by_hash,
    create_statement_record,
    write_section_to_db,
)
from extraction_helpers import (
    extract_markdown_blob,
    call_llm_for_json,
    fallback_credit_account_summary,
    map_json_section_name,
    enrich_df,
    clean_amount_string,
)
from chatbot_helpers import generate_sql_from_question, explain_result_nl
from dashboard_page import run_dashboard_page
from styles import apply_custom_styles
from goals_page import run_goals_page

# ==============================================================  # AUTH UI
# ==============================================================

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


# ==============================================================  # CHAT PAGE
# ==============================================================

def run_chat_and_upload_page():
    """Chat-first interface with PDF upload and custom chat bubbles."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("You must be logged in.")
        return

    # Track the last processed file hash so we don't re-process on every rerun
    if "last_uploaded_sha" not in st.session_state:
        st.session_state.last_uploaded_sha = None

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

    # Format SQL result for display (nice columns + txn_type)
    def format_result_for_display(df: pd.DataFrame) -> pd.DataFrame | None:
        if df is None or df.empty:
            return df

        # ⭐ NEW: for single-value results, we DON'T want a table
        if df.shape == (1, 1):
            return None

        # 🔹 SPECIAL CASE: month-by-month summary from v_monthly_summary
        if "month_start" in df.columns and "total_expenses" in df.columns:
            out = df[["month_start", "total_expenses"]].copy()
            out.rename(
                columns={
                    "month_start": "Month",
                    "total_expenses": "Total spending",
                },
                inplace=True,
            )
            return out

        # 🔹 Default case: individual transactions
        if "txn_type" not in df.columns:
            if "statement_type" in df.columns:
                df["txn_type"] = df["statement_type"]
            elif "tx_kind" in df.columns:
                df["txn_type"] = df["tx_kind"]

        if "txn_type" in df.columns:
            df["txn_type"] = (
                df["txn_type"]
                .astype(str)
                .str.lower()
                .map(
                    {
                        "credit": "Credit card",
                        "debit": "Debit",
                        "expense": "Expense",
                        "income": "Income",
                    }
                )
                .fillna(df["txn_type"])
            )

        keep_cols = ["txn_date", "vendor", "category", "description", "amount", "txn_type"]
        display_cols = [c for c in keep_cols if c in df.columns]
        if not display_cols:
            return df

        out = df[display_cols].copy()

        rename_map = {
            "txn_date": "Date",
            "vendor": "Vendor",
            "category": "Category",
            "description": "Description",
            "amount": "Amount",
            "txn_type": "Type",
        }
        out.rename(
            columns={k: v for k, v in rename_map.items() if k in out.columns},
            inplace=True,
        )
        return out

    def answer_onboarding_question(question: str, has_data: bool) -> str | None:
        """Return a friendly answer for meta/help questions, or None if not matched."""
        q = question.lower().strip()

        if "how do i get started" in q:
            if has_data:
                return (
                    "You’re all set up already 🎉<br>"
                    "You’ve uploaded at least one statement, so you can ask things like:<br>"
                    "• <i>How much did I spend last month?</i><br>"
                    "• <i>Show my largest transactions.</i><br><br>"
                    "If you get a new PDF statement, just upload it above and I’ll add "
                    "those transactions to your history."
                )
            else:
                return (
                    "To get started, upload a PDF bank or credit-card statement using "
                    "the file uploader above.<br><br>"
                    "I will:<br>"
                    "• Extract the transactions from the statement<br>"
                    "• Store them securely in your Neon Postgres database under your account<br>"
                    "• Let you chat with your own data for summaries, vendors, and trends."
                )

        if "what types of statements can i upload" in q:
            return (
                "Right now I work best with:<br>"
                "• Bank / checking account statements (PDF)<br>"
                "• Credit card statements (PDF)<br><br>"
                "Each statement should be a normal monthly statement with tables of "
                "transactions. Multi-page PDFs are fine — I’ll scan all pages."
            )

        if "what can you do with my statements" in q:
            return (
                "Once you upload a statement, I can:<br>"
                "• Summarize your spending and savings by month<br>"
                "• Show largest transactions, recurring vendors, and category breakdowns<br>"
                "• Answer questions like <i>How much did I spend on Uber?</i> or "
                "<i>Show my grocery transactions in October.</i><br>"
                "• Power the dashboard on the <b>📊 Dashboard</b> tab using the same data."
            )

        if "is my data safe" in q:
            return (
                "Your data is stored in a Neon Postgres database tied to your account.<br>"
                "Each transaction row is tagged with your user ID so other users can’t "
                "see it.<br><br>"
                "Uploaded PDFs are processed, then only the structured transaction data "
                "is stored. This is a capstone / demo app, so you should still avoid "
                "using real bank accounts with large balances."
            )

        return None

    # ---------- Session state ----------
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_query" not in st.session_state:
        st.session_state.pending_query = None

    # Greeting
    bot_msg(
        "Hi Tejaswini 👋<br>"
        "You can ask things like:<br>"
        "• <i>How much did I spend on food last month?</i><br>"
        "• <i>What’s my biggest transaction this month?</i><br>"
        "• <i>Show my total savings this year.</i>"
    )

    # ---------- WAYS I CAN HELP chips ----------
    has_data = user_has_data(user_id)

    if has_data:
        suggestion_texts = [
            "Summarize my spending for the latest month you have.",
            "Show my spending by month over all the data you have.",
            "Show my largest transactions over the whole period.",
            "Show my recurring transactions or subscriptions.",
            "What time period of transactions do you have for me?",
        ]
    else:
        suggestion_texts = [
            "How do I get started?",
            "What types of statements can I upload?",
            "What can you do with my statements?",
            "Is my data safe?",
        ]

    st.markdown('<div class="suggestion-label">WAYS I CAN HELP</div>', unsafe_allow_html=True)
    st.markdown('<div class="suggestion-row">', unsafe_allow_html=True)

    sugg_cols = st.columns(min(3, len(suggestion_texts)))
    for idx, sugg in enumerate(suggestion_texts):
        col = sugg_cols[idx % len(sugg_cols)]
        if col.button(sugg, key=f"sugg_{idx}"):
            st.session_state.pending_query = sugg

    st.markdown("</div>", unsafe_allow_html=True)

    # ---------- CHAT PLACEHOLDER ----------
    chat_placeholder = st.container()

    # ---------- INPUT AREA ----------
    st.markdown('<div class="gpt-input-bar">', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "",
        type=["pdf"],
        label_visibility="collapsed",
        accept_multiple_files=False,
    )
    new_upload = False
    file_bytes = None
    sha256_hex = None

    if uploaded_file is not None:
        # Read bytes once and compute hash
        file_bytes = uploaded_file.read()
        sha256_hex = hashlib.sha256(file_bytes).hexdigest()

        # New upload only if hash changed
        if sha256_hex != st.session_state.last_uploaded_sha:
            new_upload = True
            st.session_state.last_uploaded_sha = sha256_hex

    msg_col, send_col = st.columns([10, 1.2])

    with msg_col:
        user_text = st.text_input(
            "",
            key="chat_input",
            placeholder="Ask about your spending, savings, or a specific vendor…",
            label_visibility="collapsed",
        )

    with send_col:
        send_clicked = st.button("➤", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)  # close gpt-input-bar

    # ---------- HANDLE CLICK / PROCESSING ----------
    pending = st.session_state.pending_query
    typed_text = user_text.strip()
    question_text = pending or typed_text

    # Use new_upload instead of (uploaded_file is not None)
    triggered = send_clicked or new_upload or (pending is not None)

    processing_message = ""
    result_df = None

    if triggered and (question_text or new_upload):
        st.session_state.pending_query = None

        # User display text
        display_text = question_text if question_text else ""
        # Only mention the PDF when it's a brand new upload
        if new_upload and uploaded_file is not None:
            if display_text:
                display_text += f"<br>📄 Uploaded statement: {uploaded_file.name}"
            else:
                display_text = f"📄 Uploaded statement: {uploaded_file.name}"

        st.session_state.messages.append({"role": "user", "content": display_text})

        # ---------- 1) PROCESS UPLOADED STATEMENT (if any) ----------
        if new_upload and file_bytes is not None and sha256_hex is not None:
            existing_stmt = get_statement_by_hash(sha256_hex, user_id)
            existing_stmt_id = None
            existing_row_count = 0

            if existing_stmt:
                existing_stmt_id = existing_stmt.id
                with engine.connect() as conn:
                    existing_row_count = conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM statement_rows
                            WHERE statement_id = :sid AND user_id = :uid
                            """
                        ),
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

                        sections_json = json_data.get("sections", {}) or {}
                        if not sections_json:
                            processing_message = (
                                "❌ I couldn't find any usable sections in that statement."
                            )
                        else:
                            saved_sections = []

                            for raw_key, section_obj in sections_json.items():
                                try:
                                    cols = section_obj.get("columns") or []
                                    rows = section_obj.get("rows") or []

                                    if not cols or not isinstance(rows, list):
                                        continue

                                    cleaned_rows = []
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
                                                    df["Description"]
                                                    .astype(str)
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

        # ---------- 2) RUN QUESTION → SQL → DB ----------
        answer_text = ""

        if question_text:
            onboarding_answer = answer_onboarding_question(question_text, has_data)
            if onboarding_answer is not None:
                answer_text = onboarding_answer
                sql = None
            else:
                try:
                    with st.spinner("Thinking and running your query..."):
                        # ⭐ NEW: build chat history of user questions for LLM
                        history_questions = [
                            msg["content"]
                            for msg in st.session_state.messages
                            if msg["role"] == "user"
                        ]
                        # include current question at the end
                        history_questions.append(question_text)
                        # keep only last ~6 questions for context
                        history_slice = history_questions[-6:]

                        sql = generate_sql_from_question(
                            question_text,
                            chat_history=history_slice,
                        )
                        print("\n\n--- LLM SQL OUTPUT ---\n", sql, "\n\n")
                except Exception as e:
                    answer_text = f"⚠️ I had an error while generating the SQL: {e}"
                    sql = None

            if not sql:
                if not answer_text:
                    answer_text = (
                        "I couldn't generate a safe SQL query for that question. "
                        "Try rephrasing it or ask something simpler."
                    )
            else:
                print("🔍 Generated SQL:\n", sql)
                try:
                    with engine.connect() as conn:
                        result = conn.execute(text(sql), {"user_id": user_id})
                        rows = result.fetchall()
                        cols = result.keys()
                except Exception as e:
                    answer_text = (
                        "❌ Error running SQL on the database:<br>"
                        f"<code>{str(e)}</code>"
                    )
                    result_df = None
                else:
                    if not rows:
                        answer_text = (
                            "I couldn't find any transactions in your statements that match "
                            "this question or date range. There may be no data for that period."
                        )
                        result_df = None
                    else:
                        raw_df = pd.DataFrame(rows, columns=cols)

                        # ⭐ NEW: let formatter decide whether to show a table
                        result_df = format_result_for_display(raw_df)

                        try:
                            # explain_result_nl now handles single-value vs categories, etc.
                            answer_text = explain_result_nl(question_text, raw_df)
                        except Exception as e:
                            print("Explain error:", e)
                            answer_text = (
                                "Here’s a summary of what I found based on your question."
                            )

        # ---------- 3) APPEND BOT MESSAGE + OPTIONAL TABLE ----------
        combined_parts = []
        if processing_message:
            combined_parts.append(processing_message)
        if answer_text:
            combined_parts.append(answer_text)
        combined_reply = "<br><br>".join(combined_parts) if combined_parts else ""

        if not combined_reply:
            combined_reply = (
                "I couldn't figure out an answer for that. "
                "Please try rephrasing it or ask about a different time period."
            )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": combined_reply,
            }
        )


    # ---------- RENDER CHAT HISTORY ----------
    with chat_placeholder:
        st.markdown('<div class="chat-history">', unsafe_allow_html=True)
        for msg in st.session_state.messages:
            if msg["role"] == "assistant":
                bot_msg(msg["content"])
            else:
                user_msg(msg["content"])
        st.markdown("</div>", unsafe_allow_html=True)



# ==============================================================  # MAIN APP
# ==============================================================

st.set_page_config(page_title="🏦 Finance Chatbot", page_icon="💰", layout="wide")
apply_custom_styles()

try:
    init_db()
except OperationalError as e:
    st.warning(
        "⚠️ I couldn't run the database initialization step.\n\n"
        "If your tables are already created in Neon, you can still try using the app.\n\n"
        f"Technical details: {e}"
    )

require_login()

st.title("🏦 Personal Finance Chatbot")

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
    run_dashboard_page(engine)


elif page == "🎯 Smart Financial Coach":
    run_goals_page()
