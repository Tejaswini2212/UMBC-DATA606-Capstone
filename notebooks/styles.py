import streamlit as st

def apply_custom_styles():
    st.markdown(
        """
        <style>
        /* ============================================================
           SCROLLABLE MESSAGE AREA (ONLY THIS SCROLLS)
        ============================================================ */
        .chat-history {
            max-height: 450px;
            overflow-y: auto;
            padding-right: 10px;
            margin-bottom: 0.75rem; /* space above input row */
            border-radius: 16px;
            background: #020617;
            border: 1px solid #111827;
            padding: 10px 8px 6px 4px;
        }

        .chat-history::-webkit-scrollbar {
            width: 6px;
        }
        .chat-history::-webkit-scrollbar-thumb {
            background: #1f2937;
            border-radius: 999px;
        }

        /* ============================================================
           GLOBAL THEME
        ============================================================ */
        body, .main, .stApp {
            background: radial-gradient(circle at top, #0b1f3a 0, #020617 55%, #000000 100%);
        }

        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 1.5rem;
            max-width: 1200px;
        }

        h1 {
            font-size: 2.1rem !important;
            letter-spacing: 0.03em;
        }

        /* ============================================================
           CHAT CARD
        ============================================================ */
        .app-card {
            background-color: rgba(15,23,42,0.96);
            border-radius: 22px;
            padding: 18px 20px 16px 20px;
            border: 1px solid #1e293b;
            box-shadow: 0 18px 40px rgba(0,0,0,0.55);
            max-width: 1100px;
            margin: 0.8rem auto 1.5rem auto;
        }

        /* (chat-box left here in case used elsewhere, but NOT scrollable) */
        .chat-box {
            border-radius: 16px;
            padding: 10px 8px 6px 4px;
            background: #020617;
            border: 1px solid #111827;
            margin-top: 0.5rem;
            margin-bottom: 0.9rem;
        }

        /* ============================================================
           CHAT BUBBLES
        ============================================================ */
        .chat-bot,
        .chat-user {
            padding: 9px 13px;
            border-radius: 16px;
            margin-bottom: 0.45rem;
            font-size: 0.9rem;
            line-height: 1.45;
            max-width: 80%;
        }

        .chat-bot {
            background: #020617;
            border: 1px solid #1f2937;
            color: #e5e7eb;
        }

        .chat-user {
            margin-left: auto;
            background: linear-gradient(135deg, #2563eb, #38bdf8);
            color: #ecfeff;
            border-radius: 18px 18px 4px 18px;
        }

        /* (extra msg-* classes if you want them later) */
        .msg-user {
            background-color: rgba(37, 99, 235, 0.12);
            border-radius: 14px;
            padding: 8px 10px;
            margin-bottom: 6px;
            border: 1px solid rgba(59, 130, 246, 0.35);
            font-size: 0.92rem;
        }
        .msg-bot {
            background-color: rgba(15, 23, 42, 0.8);
            border-radius: 14px;
            padding: 8px 10px;
            margin-bottom: 6px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            font-size: 0.92rem;
        }

        .msg-label {
            font-size: 0.75rem;
            opacity: 0.8;
            margin-bottom: 2px;
        }

        /* ============================================================
           TOP BAR
        ============================================================ */
        .top-bar-title {
            font-size: 0.95rem;
            font-weight: 600;
            color: #e5e7eb;
        }
        .top-bar-sub {
            font-size: 0.8rem;
            color: #9ca3af;
        }

        /* ============================================================
           SUGGESTION CHIPS
        ============================================================ */
        .suggestion-label {
            font-size: 0.78rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #6b7280;
            margin: 0.1rem auto 0.25rem auto;
            max-width: 1100px;
        }

        .suggestion-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin: 0 auto 0.6rem auto;
            max-width: 1100px;
        }

        .suggestion-row button {
            border-radius: 999px !important;
            border: 1px solid #3b82f6 !important;
            padding: 0.25rem 0.9rem !important;
            font-size: 0.82rem !important;
            background: #020617 !important;
        }

        /* ============================================================
           GPT-STYLE INPUT BAR (NON-SCROLLING)
        ============================================================ */
        .gpt-input-bar {
            background: #111827;
            padding: 8px 14px;
            border-radius: 999px;
            border: 1px solid #1f2937;
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 0.6rem;
        }

        /* File uploader inside input bar */
        .gpt-input-bar .stFileUploader {
            padding: 0 !important;
            margin: 0 !important;
        }

        .gpt-input-bar .stFileUploader > div > div {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
        }

        .gpt-input-bar .stFileUploader span,
        .gpt-input-bar .stFileUploader small {
            display: none !important;
        }

        .gpt-input-bar .stFileUploader button {
            border-radius: 14px !important;
            padding: 4px 10px !important;
            font-size: 0.78rem !important;
            background: #1f2937 !important;
            border: 1px solid #374151 !important;
            color: #e5e7eb !important;
        }

        /* Text input inside bar */
        .gpt-input-bar .stTextInput > div > div {
            background: transparent !important;
            border: none !important;
        }

        .gpt-input-bar input {
            background: transparent !important;
            color: #e5e7eb !important;
            font-size: 1rem !important;
            padding-left: 4px;
        }

        .gpt-input-bar input::placeholder {
            color: #6b7280 !important;
        }

        /* Send button inside bar */
        .gpt-input-bar button {
            background: #2563eb !important;
            color: white !important;
            border-radius: 50% !important;
            height: 38px !important;
            width: 38px !important;
            border: none !important;
            font-size: 1.1rem !important;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: #020617;
        }
        section[data-testid="stSidebar"] * {
            color: #e5e7eb !important;
        }

        .stExpander {
            border-radius: 14px !important;
            border: 1px solid #1e293b !important;
            background-color: #020617 !important;
            margin-bottom: 0.6rem !important;
        }

        /* Make the default text input nice (fallback) */
        .stTextInput > div > div > input {
            border-radius: 999px;
            padding: 8px 12px;
            font-size: 0.95rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
