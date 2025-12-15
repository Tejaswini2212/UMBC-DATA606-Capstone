# goals_page.py

import datetime
import math
import json
import pandas as pd
import streamlit as st
from sqlalchemy import text

from db_helpers import engine
from styles import apply_custom_styles
from extraction_helpers import call_llm_for_json  # adjust if this lives elsewhere


# ---------- Utility: month difference ----------

def _months_between(start_date, end_date):
    """Rough month diff between two dates (>= 1)."""
    if start_date is None or end_date is None:
        return None
    if end_date <= start_date:
        return 1
    return max(1, (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month))


# ---------- Classify per-goal status ----------

def classify_goal_status(row):
    """
    Return (status_label, required_monthly, months_left) based on target vs plan.
    Logical status, independent of DB 'status' column.
    """
    today = datetime.date.today()

    target = float(row["target_amount"])
    current = float(row.get("current_amount") or 0)
    planned = float(row.get("planned_monthly") or 0)
    target_date = row["target_date"]

    # Already complete or overfunded
    if current >= target:
        return "Completed", 0.0, 0

    if pd.isna(target_date) or planned <= 0:
        return "No plan yet", None, None

    months_left = _months_between(today, target_date)
    remaining = max(0.0, target - current)
    required = remaining / months_left if months_left > 0 else remaining

    if required <= 0:
        return "Completed", 0.0, months_left

    ratio = planned / required

    if ratio >= 1.0:
        label = "On track"
    elif ratio >= 0.6:
        label = "Slightly behind"
    else:
        label = "Off track"

    return label, required, months_left


# ---------- Build snapshot for the LLM ----------

def build_goals_snapshot(user_id: int):
    """
    Pull user summary, top categories, and goals into a compact JSON snapshot
    for the LLM to turn into smart nudges.

    NEW: uses historical v_monthly_summary to estimate:
    - avg_income, avg_expenses, avg_net_savings
    and for each goal:
    - safe_monthly_from_history: how much they can realistically put into this goal
    - extra_needed_after_history: extra per month they'd need to find (via cuts)
    """
    with engine.connect() as conn:
        # last 3–6 months monthly summary (using 6 for smoother average)
        ms_df = pd.read_sql(
            text("""
                SELECT month_start,
                       total_income,
                       total_expenses,
                       (total_income - total_expenses) AS net_savings
                FROM v_monthly_summary
                WHERE user_id = :uid
                ORDER BY month_start DESC
                LIMIT 6
            """),
            conn,
            params={"uid": user_id},
        )

        # last full calendar month transactions
        tx_df = pd.read_sql(
            text("""
                SELECT txn_date::date AS txn_date,
                       category,
                       signed_amount
                FROM v_transactions_bi
                WHERE user_id = :uid
                  AND txn_date >= date_trunc('month', CURRENT_DATE) - interval '1 month'
                  AND txn_date <  date_trunc('month', CURRENT_DATE)
            """),
            conn,
            params={"uid": user_id},
        )

        goals_df = pd.read_sql(
            text("""
                SELECT *
                FROM goals
                WHERE user_id = :uid
                ORDER BY created_at
            """),
            conn,
            params={"uid": user_id},
        )

    summary = {}
    avg_net = None
    if not ms_df.empty:
        avg_income = float(ms_df["total_income"].mean())
        avg_expenses = float(ms_df["total_expenses"].mean())
        avg_net = float(ms_df["net_savings"].mean())
        summary = {
            "months_considered": int(len(ms_df)),
            "avg_income": avg_income,
            "avg_expenses": avg_expenses,
            "avg_net_savings": avg_net,
            "latest_month_start": ms_df["month_start"].max().strftime("%Y-%m-%d"),
        }

    # top categories from last full month (for potential cuts)
    top_categories = []
    if not tx_df.empty:
        exp_df = tx_df[tx_df["signed_amount"] < 0].copy()
        if not exp_df.empty:
            cat_group = (
                exp_df.groupby("category")["signed_amount"]
                .sum()
                .sort_values()
                .reset_index()
            )
            # top 5 strongest expense categories
            for _, row in cat_group.head(5).iterrows():
                top_categories.append(
                    {
                        "category": row["category"] or "Uncategorized",
                        "amount": float(-row["signed_amount"]),  # make positive
                    }
                )

    # goals list + safe/extra amounts
    goals_list = []
    if not goals_df.empty:
        for _, g in goals_df.iterrows():
            label, required, months_left = classify_goal_status(g)

            if avg_net is not None and required is not None:
                # Conservative rule: at most 70% of average net savings
                if avg_net <= 0:
                    safe = 0.0
                else:
                    safe = min(required, avg_net * 0.7)
                extra_needed = max(0.0, required - safe)
            else:
                safe = None
                extra_needed = None

            goals_list.append(
                {
                    "name": g["goal_name"],
                    "type": g["goal_type"],
                    "db_status": g["status"],
                    "priority": g.get("goal_priority") or "medium",
                    "target_amount": float(g["target_amount"]),
                    "current_amount": float(g.get("current_amount") or 0),
                    "planned_monthly": float(g.get("planned_monthly") or 0),
                    "target_date": g["target_date"].strftime("%Y-%m-%d")
                    if pd.notna(g["target_date"])
                    else None,
                    "status_label": label,
                    "required_monthly": float(required) if required is not None else None,
                    "months_left": int(months_left) if months_left is not None else None,
                    # NEW: history-aware fields
                    "safe_monthly_from_history": float(safe) if safe is not None else None,
                    "extra_needed_after_history": float(extra_needed) if extra_needed is not None else None,
                }
            )

    snapshot = {
        "summary": summary,
        "top_categories_last_month": top_categories,
        "goals": goals_list,
    }
    return snapshot


# ---------- LLM: generate smart nudges ----------

def generate_smart_nudges_llm(snapshot: dict):
    """
    Use the LLM (call_llm_for_json) to turn snapshot into human-friendly nudges.

    Snapshot now includes:
    - summary.avg_net_savings  → "you usually save about $X/month"
    - per-goal.safe_monthly_from_history → "you can safely put ~$Y/month into this goal"
    - per-goal.extra_needed_after_history → "you still need about $Z/month; suggest small cuts"
    """
    # If there is almost no data, just return a static hint
    if not snapshot.get("goals") and not snapshot.get("summary"):
        return [
            {
                "title": "Add your first goal",
                "body": "Create a goal like an emergency fund or a Florida trip. Once you upload statements, "
                        "I'll look at your spending and suggest how much you can safely save each month.",
                "tags": ["getting_started"],
            }
        ]

    schema = {
        "type": "object",
        "properties": {
            "nudges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "body"],
                },
            }
        },
        "required": ["nudges"],
    }

    system_prompt = (
        "You are a friendly personal finance assistant. You see a compact JSON snapshot of the user's "
        "recent income, expenses, savings, and goals. Your job is to generate short, supportive nudges that "
        "help them move toward their goals. Do NOT be judgmental. Keep everything practical and specific. "
        "Avoid generic advice like 'spend less' or 'save more'."
    )

    user_prompt = (
        "Here is the user's financial snapshot in JSON format:\n\n"
        f"{json.dumps(snapshot, indent=2)}\n\n"
        "Key fields:\n"
        "- summary.avg_income / summary.avg_expenses / summary.avg_net_savings: "
        "their typical monthly pattern based on recent months.\n"
        "- For each goal:\n"
        "  - required_monthly: amount needed per month to hit the target date.\n"
        "  - safe_monthly_from_history: what they can realistically allocate from their usual savings.\n"
        "  - extra_needed_after_history: extra per month they would still need (implies trimming expenses).\n"
        "- top_categories_last_month: the largest recent spending categories (good candidates for small cuts).\n\n"
        "Generate 3 to 5 short, helpful nudges. Each nudge should be 1–2 sentences, very concrete, and actionable.\n"
        "- Explicitly mention how much they usually save per month when relevant.\n"
        "- For at least one main goal, say something like: "
        "'You usually save about $X/month; putting $Y/month into <goal> leaves $Z/month for everything else.'\n"
        "- If extra_needed_after_history is positive, suggest cutting SMALL amounts from 2–3 of the biggest categories, "
        "using round numbers (e.g. $15–$40) and reassuring them that essentials like rent/groceries are untouched.\n"
        "- Prioritize: safety/emergency goals and high-priority or time-sensitive goals, then one fun goal.\n"
        "- Do not repeat the same idea; vary the focus (one about savings capacity, one about trimming certain categories, "
        "one about adjusting timeline or monthly plan, etc.).\n"
        "Return JSON with a single key 'nudges', an array of objects with 'title', 'body', and optional 'tags'."
    )

    try:
        result = call_llm_for_json(system_prompt, user_prompt, schema)
        nudges = result.get("nudges", [])
    except Exception:
        # fallback to a safe default if LLM call fails
        nudges = [
            {
                "title": "Review your goals",
                "body": "Check which goals matter most right now and make sure each one has a monthly amount and a realistic target date.",
                "tags": ["fallback"],
            }
        ]
    return nudges


# ---------- Main Goals Page ----------

def run_goals_page():
    apply_custom_styles()

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("You must be logged in.")
        return

    st.markdown("### 🎯 Goals & Savings Planner")

    # ----- Load goals for snapshot + UI -----
    with engine.connect() as conn:
        goals_df = pd.read_sql(
            text("SELECT * FROM goals WHERE user_id = :uid ORDER BY created_at"),
            conn,
            params={"uid": user_id},
        )

    # Build snapshot once (used by both columns)
    snapshot = build_goals_snapshot(user_id)
    summary = snapshot.get("summary") or {}
    avg_net = summary.get("avg_net_savings")
    months_considered = summary.get("months_considered")

    # Pre-compute total required across goals (for info message)
    total_required_all_goals = 0.0
    for g in snapshot.get("goals", []):
        if g.get("status_label") not in ["Completed", "No plan yet"]:
            req = g.get("required_monthly")
            if req is not None:
                total_required_all_goals += req

    # ---------- Top row: Snapshot + Smart Nudges ----------
    col_left, col_right = st.columns([2, 3])

    # LEFT: overall snapshot
    with col_left:
        st.markdown("#### 📌 Your Goals Snapshot")

        if goals_df.empty:
            st.info("You don't have any goals yet. Add your first goal below.")
            total_target = 0
            total_current = 0
            overall_progress = 0
            status_counts = {"On track": 0, "Slightly behind": 0, "Off track": 0}
        else:
            total_target = float(goals_df["target_amount"].sum())
            total_current = float(goals_df["current_amount"].fillna(0).sum())
            overall_progress = total_current / total_target if total_target > 0 else 0

            status_counts = {"On track": 0, "Slightly behind": 0, "Off track": 0}
            for _, g in goals_df.iterrows():
                label, _, _ = classify_goal_status(g)
                if label in status_counts:
                    status_counts[label] += 1

            st.metric("Total goal target", f"${total_target:,.0f}")
            st.metric("Total saved so far", f"${total_current:,.0f}")
            st.progress(
                overall_progress,
                text=f"{overall_progress*100:,.0f}% of active goals funded",
            )

            st.caption(
                f"On track: {status_counts['On track']} • "
                f"Slightly behind: {status_counts['Slightly behind']} • "
                f"Off track: {status_counts['Off track']}"
            )

        # NEW: show typical savings vs what goals need
        if avg_net is not None and months_considered:
            if avg_net >= 0:
                st.caption(
                    f"Based on the last {months_considered} months, you're typically able to save "
                    f"about ${avg_net:,.0f} per month (income minus expenses)."
                )
            else:
                st.caption(
                    f"Over the last {months_considered} months, you've been overspending by roughly "
                    f"${abs(avg_net):,.0f} per month on average."
                )

        if avg_net is not None and total_required_all_goals > 0:
            st.caption(
                f"Your active goals together need about ${total_required_all_goals:,.0f} per month. "
                f"Compare that with your typical savings figure above to see if your plan feels realistic."
            )

    # RIGHT: LLM smart nudges
    with col_right:
        st.markdown("#### ⭐ Smart Suggestions for You")

        nudges = generate_smart_nudges_llm(snapshot)

        for n in nudges:
            title = n.get("title", "Suggestion")
            body = n.get("body", "")
            st.markdown(f"**• {title}**  \n{body}")

    st.markdown("---")

    # ---------- Add a new goal ----------
    with st.expander("➕ Add a new goal", expanded=goals_df.empty):
        with st.form("new_goal_form"):
            goal_name = st.text_input(
                "Goal name",
                placeholder="Emergency fund, Florida trip, Credit card payoff",
            )
            goal_type = st.selectbox(
                "Goal type",
                ["safety", "debt", "fun", "big_life"],
                format_func=lambda x: {
                    "safety": "Safety (emergency fund, rent buffer)",
                    "debt": "Debt / clean-up",
                    "fun": "Fun / lifestyle",
                    "big_life": "Big life goal",
                }[x],
            )
            target_amount = st.number_input("Target amount ($)", min_value=0.0, step=50.0)
            planned_monthly = st.number_input(
                "Planned monthly saving ($)", min_value=0.0, step=10.0
            )
            target_date = st.date_input(
                "Target date (optional)",
                value=datetime.date.today() + datetime.timedelta(days=180),
            )
            priority = st.selectbox("Priority", ["high", "medium", "low"], index=1)
            notes = st.text_area("Notes (optional)", height=60)
            submitted = st.form_submit_button("Create goal")

        if submitted:
            if not goal_name or target_amount <= 0:
                st.warning("Please enter a goal name and a positive target amount.")
            else:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO goals (
                                user_id, goal_name, goal_type, goal_priority,
                                target_amount, planned_monthly, target_date, notes
                            )
                            VALUES (
                                :uid, :name, :type, :priority,
                                :target_amount, :planned_monthly, :target_date, :notes
                            )
                        """),
                        {
                            "uid": user_id,
                            "name": goal_name,
                            "type": goal_type,
                            "priority": priority,
                            "target_amount": target_amount,
                            "planned_monthly": planned_monthly if planned_monthly > 0 else None,
                            "target_date": target_date,
                            "notes": notes or None,
                        },
                    )
                st.success("Goal created! Refresh the page to see it in your list.")

    # ---------- Show per-goal cards ----------
    st.markdown("#### 🧾 Your goals")

    if goals_df.empty:
        st.info("No goals yet. Once you add a goal, it will show up here with progress and status.")
        return

    for _, g in goals_df.iterrows():
        goal_id = int(g["id"])
        name = g["goal_name"]
        status = g["status"]
        label, required, months_left = classify_goal_status(g)

        current = float(g.get("current_amount") or 0)
        target = float(g["target_amount"])
        planned = float(g.get("planned_monthly") or 0)
        progress = current / target if target > 0 else 0

        box = st.container(border=True)
        with box:
            st.markdown(
                f"**{name}**  \n"
                f"_Type: {g['goal_type']} • Priority: {g.get('goal_priority','medium')} • Status: {status}_"
            )

            st.progress(progress, text=f"${current:,.0f} / ${target:,.0f}")

            col1, col2, col3 = st.columns(3)
            with col1:
                if pd.notna(g["target_date"]):
                    st.caption(f"Target date: {g['target_date']:%b %d, %Y}")
                else:
                    st.caption("Target date: not set")

            with col2:
                if label in ["On track", "Slightly behind", "Off track"]:
                    if required is not None and months_left is not None:
                        st.caption(
                            f"{label} • Needs about ${required:,.0f}/month over ~{months_left} months"
                        )
                    else:
                        st.caption(label)
                else:
                    st.caption(label)

            with col3:
                st.caption(f"Planned monthly: ${planned:,.0f}")

            # Inline update form for current_amount, planned_monthly, status
            with st.form(f"update_goal_{goal_id}"):
                uc1, uc2, uc3, uc4 = st.columns([1, 1, 1, 1])
                with uc1:
                    new_current = st.number_input(
                        "Current saved ($)",
                        min_value=0.0,
                        value=current,
                        step=50.0,
                        key=f"current_{goal_id}",
                    )
                with uc2:
                    new_planned = st.number_input(
                        "Monthly plan ($)",
                        min_value=0.0,
                        value=planned,
                        step=10.0,
                        key=f"planned_{goal_id}",
                    )
                with uc3:
                    new_status = st.selectbox(
                        "Status",
                        ["active", "paused", "completed"],
                        index=["active", "paused", "completed"].index(status),
                        key=f"status_{goal_id}",
                    )
                with uc4:
                    submit_update = st.form_submit_button("Save")

                if submit_update:
                    with engine.begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE goals
                                SET current_amount = :current_amount,
                                    planned_monthly = :planned_monthly,
                                    status = :status
                                WHERE id = :goal_id
                                  AND user_id = :uid
                            """),
                            {
                                "current_amount": new_current,
                                "planned_monthly": new_planned if new_planned > 0 else None,
                                "status": new_status,
                                "goal_id": goal_id,
                                "uid": user_id,
                            },
                        )
                    st.success("Goal updated. Refresh to see new status.")
