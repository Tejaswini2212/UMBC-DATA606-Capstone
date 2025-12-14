# AI-Powered Personal Finance & Investment Chatbot
### A Data-Driven Financial Intelligence System Using OCR, LLMs, and Interactive Dashboards

**Prepared for:**  
UMBC Data Science Master’s Degree Capstone  
Dr. Chaojie (Jay) Wang  

**Author:**  
Tejaswini Jammi  

**GitHub Repository:**  
https://github.com/TejaswiniJammi/Personal-Finance-Chatbot](https://github.com/Tejaswini2212/UMBC-DATA606-Capstone  

**LinkedIn Profile:**  
https://www.linkedin.com/in/tejaswini-jammi  

**PowerPoint Presentation:**  
*(Add link here)*  

**YouTube Demo Video:**  
*(Add link here)*  

---

## 1. Background

Personal finance management is a critical yet challenging task for many individuals. Bank statements are typically delivered as unstructured PDF documents that are difficult for users to analyze beyond basic balances and monthly totals. Users often struggle to understand spending patterns, identify savings opportunities, and plan financial goals effectively.

This project presents an **AI-powered personal finance chatbot** that automatically extracts structured financial data from bank statements and allows users to interact with their financial history using natural language queries.

### Why It Matters
- Banking apps provide limited analytical insights
- Manual budgeting is time-consuming and error-prone
- Financial tools lack personalization
- Conversational AI enables intuitive data access

### Research Questions
1. Can OCR and LLMs reliably extract structured data from unstructured bank statements?
2. Can natural language queries be translated into accurate SQL queries?
3. Do interactive dashboards improve financial awareness?
4. Can AI-driven insights support better financial decisions?

---

## 2. Data

### Data Sources
- User-uploaded Bank of America debit and credit card PDF statements
- OCR + LLM-based extraction pipeline

### Data Size
- PDF statements: ~1–3 MB per file
- Database size scales with user uploads

### Data Shape
- Rows: ~1,000–5,000 transactions per user
- Columns: ~15–20 attributes

### Time Period
- Monthly statements
- Supports multi-year history

### Unit of Observation
- Each row represents a single financial transaction

### Data Dictionary (Key Columns)

| Column Name | Data Type | Definition | Example Values |
|------------|----------|------------|----------------|
| transaction_date | Date | Date of transaction | 2024-06-15 |
| description | Text | Statement description | Amazon Purchase |
| amount | Float | Transaction amount | -45.32 |
| transaction_type | Category | Income or Expense | Income, Expense |
| category | Category | Spending category | Rent, Groceries |
| vendor | Text | Merchant or person | Amazon, Zelle |
| account_type | Category | Account used | Debit, Credit |
| month | Category | Transaction month | June |
| year | Integer | Transaction year | 2024 |

### Target Variable
- `category` (for classification and insights)

### Feature Variables
- Amount
- Vendor
- Description
- Date
- Account type
- Transaction type

---

## 3. Exploratory Data Analysis (EDA)

EDA was conducted using **Jupyter Notebook** with **Pandas, NumPy, and Plotly Express**.

### Key Analysis
- Monthly income vs expense trends
- Category-wise spending distribution
- Top vendors by total spending
- Debit vs credit usage patterns

### Data Cleaning
- Removed duplicate transactions
- Standardized date formats
- Normalized currency values
- Cleaned vendor names
- Filled missing categories using LLM inference

### Data Transformation
- Pivoted monthly summaries
- Created SQL views:
  - `v_expenses`
  - `v_income`
  - `v_monthly_summary`
  - `v_account_summary`

### Text Preprocessing
- Lowercasing
- Tokenization
- Stopword removal
- Keyword-based vendor extraction

### Tidy Data Principles
- One row per transaction
- One column per attribute
- No redundant fields

---

## 4. Model Training

### Models Used
- Large Language Models (LLMs) for:
  - PDF section extraction
  - Vendor and category classification
  - Natural language to SQL translation

### Training Strategy
- Prompt-based inference
- Rule-based validation and fallbacks
- No traditional supervised model training

### Python Packages
- pandas
- SQLAlchemy
- Streamlit
- Plotly Express
- spaCy
- OpenAI API

### Development Environment
- Local machine
- GitHub
- Neon PostgreSQL (cloud-hosted)

### Evaluation Metrics
- Extraction accuracy
- SQL correctness
- Response relevance
- End-to-end system reliability

---

## 5. Application of the Trained Models

A web-based application was built using **Streamlit** to allow users to interact with the system.

### System Architecture

