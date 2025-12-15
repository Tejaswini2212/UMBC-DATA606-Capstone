# extraction_helpers.py

import os
import re
import time
import json
from typing import Dict, Any, List

import pandas as pd
import requests
from openai import OpenAI

# ==============================================================
# CONFIG / CONSTANTS
# ==============================================================

DOCSTRANGE_KEY = os.getenv("DOCSTRANGE_KEY", "e526e8c1-b067-11f0-b83f-a62e6d220688")
OPENAI_KEY = os.getenv("OPENAI_KEY", "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")  # override via env in prod

BASE = "https://extraction-api.nanonets.com"
HEAD = {"Authorization": f"Bearer {DOCSTRANGE_KEY}"}

client = OpenAI(api_key=OPENAI_KEY)
MODEL = "gpt-4o-mini"

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
# DOCSTRANGE MARKDOWN EXTRACTION
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


# ==============================================================
# AMOUNT CLEANING / FALLBACK SUMMARY
# ==============================================================

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


# ==============================================================
# LLM: STATEMENT JSON PARSER
# ==============================================================

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
# LLM: VENDOR / CATEGORY ENRICHMENT
# ==============================================================

def llm_vendor_category(descriptions: List[str]) -> List[Dict[str, str]]:
    if not descriptions:
        return []

    system = """
You are a financial transaction labeler.

For each transaction DESCRIPTION you must extract two fields:

- vendor   = short, clean person/merchant name (no store numbers, city/state, or codes).
- category = concise, human-friendly label describing the expense type
             (e.g., Groceries, Restaurants & Cafes, Shopping, Rent, Utilities,
             Transport, Subscriptions, Entertainment, Travel, Transfer, Fees & Charges,
             Income, Refunds, Zelle - Incoming, Zelle - Outgoing, Other).

VERY IMPORTANT RULES FOR ZELLE PAYMENTS
--------------------------------------
1. Only use the DESCRIPTION text to identify the Zelle sender/receiver.

2. If the description clearly indicates the money came FROM a person/business:
   Examples:
     - "Zelle payment from NIKHIL AKULA for Rent; Conf# 12345"
     - "Zelle FROM IMAN MOUSSA"
   Then:
     - vendor   = the person or business name after "from"
                 (e.g., "NIKHIL AKULA", "IMAN MOUSSA")
     - category = "Zelle"

3. If the description clearly indicates the money was sent TO a person/business:
   Examples:
     - "Zelle payment to Amrutha Akka Conf# 98765"
     - "Zelle TO JOHN DOE"
   Then:
     - vendor   = the person or business name after "to"
                 (e.g., "Amrutha Akka", "JOHN DOE")
     - category = "Zelle"

4. When extracting the vendor for Zelle:
   - Remove phrases like:
       "Zelle payment from", "Zelle payment to",
       "Zelle FROM", "Zelle TO",
       words like "for", "Conf#", "confirmation",
       and any numbers or codes.
   - Keep only the clean human/business name.
   - Trim extra symbols and whitespace.

5. If the description mentions Zelle but does NOT clearly show "from X" or "to X":
   - vendor   = "Zelle"
   - category = "Zelle"

6. Do NOT use generic phrases like "Zelle payment" as the vendor.
   The vendor should always be:
       - the sender/receiver person name (preferred), OR
       - "Zelle" if the name cannot be extracted.


NON-ZELLE RULES
---------------
7. For non-Zelle descriptions:
   - Infer the vendor from the main merchant/brand name in the text.
     Examples:
       "STARBUCKS 1234 BALTIMORE MD"   → vendor = "Starbucks"
       "AMAZON MARKETPLACE PMTS"       → vendor = "Amazon"
       "SAFEWAY #1234 BALTIMORE"       → vendor = "Safeway"
   - Choose a simple, human-friendly category such as:
     Groceries, Restaurants & Cafes, Shopping, Rent, Utilities, Transport,
     Subscriptions, Entertainment, Travel, Income, Refunds, Fees & Charges, Other.

8. If you truly cannot understand the purpose:
   - vendor   = a short cleaned-up name if possible, otherwise "".
   - category = "Other".

OUTPUT FORMAT (STRICT)
----------------------
You will receive a list of DESCRIPTION strings.

Return ONLY a JSON array of the same length, where each element is:

  { "vendor": "...", "category": "..." }

The order of the array must match the order of the input descriptions exactly.
Do NOT include any explanations, comments, or extra fields.
"""

    user = "Descriptions:\n" + "\n".join(f"- {d}" for d in descriptions)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
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
                    "vendor": str(o.get("vendor", "")).strip(),
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
        results.extend(llm_vendor_category(descs[i:i + BATCH]))

    vendors = [r.get("vendor", "") for r in results]
    cats = [r.get("category", "Other") for r in results]

    if "Vendor" in df.columns:
        df.drop(columns=["Vendor"], inplace=True)
    if "Category" in df.columns:
        df.drop(columns=["Category"], inplace=True)

    df.insert(len(df.columns), "Vendor", vendors)
    df.insert(len(df.columns), "Category", cats)
    return df
