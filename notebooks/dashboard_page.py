# dashboard_page.py
import hashlib
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

# Optional autorefresh (won't crash if not installed)
try:
    from streamlit_autorefresh import st_autorefresh  # pip install streamlit-autorefresh
    HAS_AUTOREFRESH = True
except Exception:
    HAS_AUTOREFRESH = False


# --- Color palette (stable per category; avoids "everything is blue") ---
PLOTLY_PALETTE = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
    "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2",
    "#7F7F7F", "#BCBD22", "#17BECF"
]
TX_KIND_COLORS = {"income": "#00CC96", "expense": "#EF553B"}  # green / red


def category_color_map(categories):
    """Deterministic mapping: same category => same color every run."""
    cats = [c for c in categories if pd.notna(c)]
    cats = sorted(set(map(str, cats)))
    cmap = {}
    for c in cats:
        h = int(hashlib.md5(c.encode("utf-8")).hexdigest(), 16)
        cmap[c] = PLOTLY_PALETTE[h % len(PLOTLY_PALETTE)]
    return cmap


def _polish_fig(fig, height=360):
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=18, r=18, t=35, b=18),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    fig.update_xaxes(showgrid=True, zeroline=False)
    fig.update_yaxes(showgrid=True, zeroline=False)
    return fig


def _get_date_bounds(engine, user_id):
    q = """
    SELECT
      MIN(txn_date::date) AS min_date,
      MAX(txn_date::date) AS max_date
    FROM v_transactions_bi
    WHERE user_id = :user_id
    """
    b = pd.read_sql(text(q), engine, params={"user_id": user_id})
    if b.empty or b.loc[0, "min_date"] is None:
        return None, None
    return (
        pd.to_datetime(b.loc[0, "min_date"]).date(),
        pd.to_datetime(b.loc[0, "max_date"]).date(),
    )


def _load_txns(engine, user_id, start_date, end_date, acct="All", tx_kind="All"):
    q = """
    SELECT
      txn_id,
      txn_date::date AS txn_date,
      month_start::date AS month_start,
      year,
      month_number,
      description,
      vendor,
      category,
      tx_kind,
      amount,
      signed_amount,
      statement_type
    FROM v_transactions_bi
    WHERE user_id = :user_id
      AND txn_date::date BETWEEN :start_date AND :end_date
    """
    params = {
        "user_id": user_id,
        "start_date": pd.Timestamp(start_date).date(),
        "end_date": pd.Timestamp(end_date).date(),
    }

    if acct != "All":
        q += " AND statement_type = :acct"
        params["acct"] = acct

    if tx_kind != "All":
        q += " AND tx_kind = :tx_kind"
        params["tx_kind"] = tx_kind

    q += " ORDER BY txn_date DESC"
    return pd.read_sql(text(q), engine, params=params)


def _format_money(x):
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return x


def run_dashboard_page(engine):
    st.subheader("📊 Financial Dashboard")

    # --- Dashboard-only CSS (UPDATED: bigger KPIs, smaller slicers, more center space) ---
    st.markdown(
        """
        <style>
        /* Use space better */
        .block-container { padding-top: 0.8rem; padding-left: 1.2rem; padding-right: 1.2rem; }
        section.main > div { gap: 0.6rem; }

        /* Smaller slicers / inputs */
        label { font-size: 0.82rem !important; opacity: 0.9; }
        div[data-baseweb="select"] > div {
          border-radius: 12px;
          min-height: 36px !important;
          padding-top: 0px !important;
          padding-bottom: 0px !important;
          font-size: 0.85rem !important;
        }
        div[data-testid="stSlider"] { padding-top: 0.2rem; padding-bottom: 0.2rem; }

        /* KPI cards bigger + full values */
        div[data-testid="stMetric"]{
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.14);
          padding: 18px 18px;
          border-radius: 16px;
          min-height: 110px;
        }
        div[data-testid="stMetricLabel"] p{
          font-size: 0.95rem !important;
          opacity: 0.9;
          margin-bottom: 2px !important;
        }
        div[data-testid="stMetricValue"]{
          font-size: 2.2rem !important;
          line-height: 1.1 !important;
          overflow: visible !important;
          text-overflow: unset !important;
          white-space: normal !important;  /* wraps if needed */
        }
        div[data-testid="stMetricDelta"]{
          font-size: 0.9rem !important;
        }

        .dash-panel {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.10);
          padding: 12px;
          border-radius: 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error("Please login first.")
        return

    # ---------------------------
    # Refresh controls
    # ---------------------------
    topL, topR = st.columns([1, 2])
    with topL:
        if st.button("Refresh now"):
            st.rerun()
    with topR:
        if HAS_AUTOREFRESH:
            auto = st.toggle("Auto-refresh", value=True)
            if auto:
                st_autorefresh(interval=30_000, key="dash_refresh")
        else:
            st.caption("    ")

    # ---------------------------
    # Layout: filters left, dashboard right (UPDATED: more space to charts)
    # ---------------------------
    filters_col, main_col = st.columns([0.70, 2.30], gap="large")

    # ===== LEFT: filters =====
    with filters_col:
        st.markdown('<div class="dash-panel">', unsafe_allow_html=True)
        st.markdown("#### Filters")

        min_d, max_d = _get_date_bounds(engine, user_id)
        if not min_d:
            st.info("No transactions available yet.")
            st.stop()

        default_start = max(min_d, (pd.Timestamp(max_d) - pd.Timedelta(days=30)).date())
        default_end = max_d

        start_d, end_d = st.slider(
            "Transactions Date Range",
            min_value=min_d,
            max_value=max_d,
            value=(default_start, default_end),
            format="MMM D, YYYY",
        )
        start_date = pd.Timestamp(start_d)
        end_date = pd.Timestamp(end_d)

        st.caption(
            f"Showing: **{pd.Timestamp(start_d).strftime('%b %d, %Y')} → "
            f"{pd.Timestamp(end_d).strftime('%b %d, %Y')}**"
        )

        st.markdown("---")
        acct = st.selectbox("Account type", ["All", "debit", "credit"], index=0)
        kind = st.selectbox("Transaction type", ["All", "income", "expense"], index=0)
        st.markdown('</div>', unsafe_allow_html=True)

    # ===== RIGHT: dashboard =====
    with main_col:
        df = _load_txns(engine, user_id, start_date, end_date, acct, kind)
        if df.empty:
            st.info("No transactions found for the selected filters.")
            return

        # Clean formats
        df["month_start"] = pd.to_datetime(df["month_start"]).dt.to_period("M").dt.to_timestamp()
        df["txn_date"] = pd.to_datetime(df["txn_date"])
        df["month_label"] = df["month_start"].dt.strftime("%b %Y")

        cat_colors = category_color_map(df["category"].astype(str).tolist())

        # Optional filters (UPDATED: smaller + doesn't steal width)
        f1, f2, spacer = st.columns([1, 1, 2], gap="large")
        with f1:
            cat_opt = ["All"] + sorted(df["category"].dropna().astype(str).unique().tolist())
            cat_sel = st.selectbox("Category (optional)", cat_opt, index=0)
        with f2:
            ven_opt = ["All"] + sorted(df["vendor"].dropna().astype(str).unique().tolist())
            ven_sel = st.selectbox("Vendor (optional)", ven_opt, index=0)

        if cat_sel != "All":
            df = df[df["category"].astype(str) == cat_sel]
        if ven_sel != "All":
            df = df[df["vendor"].astype(str) == ven_sel]
        if df.empty:
            st.info("No transactions after applying Category/Vendor filters.")
            return

        # KPI row (UPDATED: 2x2 layout so values show fully)
        income = df.loc[df["tx_kind"] == "income", "amount"].sum()
        expense = df.loc[df["tx_kind"] == "expense", "amount"].sum()
        net = income - expense
        savings_rate = (net / income * 100) if income > 0 else 0

        r1c1, r1c2 = st.columns(2, gap="large")
        r2c1, r2c2 = st.columns(2, gap="large")

        r1c1.metric("Income", f"${income:,.2f}")
        r1c2.metric("Spent", f"${expense:,.2f}")
        r2c1.metric("Left (Income - Spent)", f"${net:,.2f}")
        r2c2.metric("Savings rate", f"{savings_rate:.1f}%")

        exp = df[df["tx_kind"] == "expense"].copy()

        # ------------------------------------------------------------
        # Tabs
        # ------------------------------------------------------------
        tab_overview, tab_changes, tab_income, tab_tables = st.tabs(
            ["📌 Overview", "📈 Changes", "💰 Income vs Expense", "🧾 Tables"]
        )

        # ===========================
        # TAB: OVERVIEW
        # ===========================
        with tab_overview:
            st.markdown("### Is my spending getting worse or better?")
            if exp.empty:
                st.info("No spending (expense) data in this date range.")
            else:
                m_exp = (
                    exp.groupby("month_start", as_index=False)["amount"]
                       .sum()
                       .sort_values("month_start")
                )
                m_exp["month_label"] = pd.to_datetime(m_exp["month_start"]).dt.strftime("%b %Y")

                fig_exp_trend = px.area(m_exp, x="month_label", y="amount")
                fig_exp_trend.update_layout(title="")
                fig_exp_trend.update_yaxes(tickprefix="$", separatethousands=True, title="Spent ($)")
                fig_exp_trend.update_xaxes(title="Month")
                st.plotly_chart(_polish_fig(fig_exp_trend, 460), use_container_width=True)

            c1, c2 = st.columns([1, 1], gap="large")

            with c1:
                st.markdown("### Where is my money going?")
                if exp.empty:
                    st.info("No expense data.")
                else:
                    cat_sum = (
                        exp.groupby("category", as_index=False)["amount"]
                           .sum()
                           .sort_values("amount", ascending=False)
                    )
                    fig_cat = px.pie(cat_sum, names="category", values="amount", hole=0.55)
                    fig_cat.update_traces(marker=dict(
                        colors=[cat_colors.get(str(c), "#999999") for c in cat_sum["category"]]
                    ))
                    fig_cat.update_layout(title="")
                    st.plotly_chart(_polish_fig(fig_cat, 380), use_container_width=True)

            with c2:
                st.markdown("### Who am I spending the most with?")
                if exp.empty:
                    st.info("No expense data.")
                else:
                    topv = (
                        exp.groupby("vendor", as_index=False)["amount"]
                           .sum()
                           .sort_values("amount", ascending=False)
                           .head(10)
                    ).sort_values("amount")

                    fig_vendor = px.bar(topv, x="amount", y="vendor", orientation="h")
                    fig_vendor.update_layout(title="")
                    fig_vendor.update_xaxes(tickprefix="$", separatethousands=True, title="Spent ($)")
                    fig_vendor.update_yaxes(title="")
                    st.plotly_chart(_polish_fig(fig_vendor, 420), use_container_width=True)

        # ===========================
        # TAB: CHANGES
        # ===========================
        with tab_changes:
            cA, cB = st.columns([1.35, 1], gap="large")

            with cA:
                st.markdown("### What changed compared to last month?")
                if exp.empty:
                    st.info("No expense data.")
                else:
                    months = sorted(exp["month_start"].dropna().unique())
                    if len(months) < 2:
                        st.info("Need at least 2 months of data to show month-to-month change.")
                    else:
                        prev_m, curr_m = months[-2], months[-1]
                        prev = exp[exp["month_start"] == prev_m].groupby("category")["amount"].sum()
                        curr = exp[exp["month_start"] == curr_m].groupby("category")["amount"].sum()

                        delta = (curr - prev).fillna(0).reset_index()
                        delta.columns = ["category", "change"]
                        delta["abs_change"] = delta["change"].abs()
                        delta = delta.sort_values("abs_change", ascending=False).head(12).sort_values("change")

                        fig_mom = px.bar(delta, x="change", y="category", orientation="h")
                        fig_mom.update_layout(title="")
                        fig_mom.update_traces(
                            marker=dict(color=["#EF553B" if v > 0 else "#00CC96" for v in delta["change"]])
                        )
                        fig_mom.update_xaxes(
                            title="Change in spending ($) — Red = spent more, Green = spent less",
                            tickprefix="$",
                            separatethousands=True,
                        )
                        fig_mom.update_yaxes(title="")
                        st.caption(
                            f"Comparing **{pd.Timestamp(curr_m).strftime('%b %Y')}** vs **{pd.Timestamp(prev_m).strftime('%b %Y')}**"
                        )
                        st.plotly_chart(_polish_fig(fig_mom, 500), use_container_width=True)

            with cB:
                st.markdown("### Which category is increasing?")
                if exp.empty:
                    st.info("No expense data.")
                else:
                    top5 = (
                        exp.groupby("category")["amount"].sum()
                           .sort_values(ascending=False).head(5).index.astype(str).tolist()
                    )
                    exp_top = exp[exp["category"].astype(str).isin(top5)].copy()
                    cat_month = (
                        exp_top.groupby(["month_start", "category"], as_index=False)["amount"]
                              .sum()
                              .sort_values("month_start")
                    )
                    cat_month["month_label"] = pd.to_datetime(cat_month["month_start"]).dt.strftime("%b %Y")

                    fig_cat_trend = px.line(cat_month, x="month_label", y="amount", color="category")
                    fig_cat_trend.update_layout(title="")
                    fig_cat_trend.update_yaxes(tickprefix="$", separatethousands=True, title="Spent ($)")
                    fig_cat_trend.update_xaxes(title="Month")
                    fig_cat_trend.for_each_trace(
                        lambda t: t.update(line=dict(color=cat_colors.get(str(t.name), t.line.color)))
                    )
                    st.plotly_chart(_polish_fig(fig_cat_trend, 500), use_container_width=True)

        # ===========================
        # TAB: INCOME VS EXPENSE
        # ===========================
        with tab_income:
            c1, c2 = st.columns([1.35, 1], gap="large")

            month_kind = (
                df.groupby(["month_start", "tx_kind"], as_index=False)["amount"]
                  .sum()
                  .sort_values("month_start")
            )
            month_kind["month_label"] = pd.to_datetime(month_kind["month_start"]).dt.strftime("%b %Y")

            with c1:
                st.markdown("### Am I spending more than I earn?")
                fig_inc_exp = px.line(month_kind, x="month_label", y="amount", color="tx_kind", markers=True)
                fig_inc_exp.for_each_trace(
                    lambda t: t.update(line=dict(color=TX_KIND_COLORS.get(t.name, t.line.color)))
                )
                fig_inc_exp.update_layout(title="")
                fig_inc_exp.update_yaxes(tickprefix="$", separatethousands=True, title="Amount ($)")
                fig_inc_exp.update_xaxes(title="Month")
                st.plotly_chart(_polish_fig(fig_inc_exp, 460), use_container_width=True)

            with c2:
                st.markdown("### Expense-to-Income ratio (lower is better)")
                pivot = month_kind.pivot(index="month_start", columns="tx_kind", values="amount").fillna(0)
                if "income" in pivot.columns:
                    pivot["ratio"] = pivot.get("expense", 0) / pivot["income"].replace(0, pd.NA)
                    ratio_df = pivot.reset_index()[["month_start", "ratio"]].dropna()
                    ratio_df["month_label"] = pd.to_datetime(ratio_df["month_start"]).dt.strftime("%b %Y")

                    if ratio_df.empty:
                        st.info("Not enough income data to compute the ratio.")
                    else:
                        fig_ratio = px.bar(ratio_df, x="month_label", y="ratio")
                        fig_ratio.update_layout(title="")
                        fig_ratio.update_yaxes(tickformat=".0%", title="Expense / Income")
                        fig_ratio.update_xaxes(title="Month")
                        st.plotly_chart(_polish_fig(fig_ratio, 460), use_container_width=True)
                else:
                    st.info("Income not present in this range, cannot compute ratio.")

        # ===========================
        # TAB: TABLES
        # ===========================
        with tab_tables:
            t1, t2 = st.columns([1, 1], gap="large")

            with t1:
                st.markdown("### Biggest single purchases (Top 10)")
                if exp.empty:
                    st.info("No expense data available.")
                else:
                    biggest = exp.sort_values("amount", ascending=False).head(10).copy()
                    out = biggest[["txn_date", "vendor", "category", "amount", "description"]].copy()
                    out["txn_date"] = out["txn_date"].dt.strftime("%b %d, %Y")
                    out["amount"] = out["amount"].map(_format_money)
                    st.dataframe(out.reset_index(drop=True), use_container_width=True)

            with t2:
                st.markdown("### Recent transactions")
                recent = df.sort_values("txn_date", ascending=False).head(20).copy()
                out2 = recent[["txn_date", "vendor", "category", "tx_kind", "amount", "description"]].copy()
                out2["txn_date"] = out2["txn_date"].dt.strftime("%b %d, %Y")
                out2["amount"] = out2["amount"].map(_format_money)
                st.dataframe(out2.reset_index(drop=True), use_container_width=True)
