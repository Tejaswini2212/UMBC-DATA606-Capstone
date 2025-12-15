# AI-Powered Personal Finance Chatbot

## 1. Title and Author

**Project Title:**  
AI-Powered Personal Finance Chatbot Using OCR and Large Language Models

**Prepared for:**  
UMBC Data Science Master Degree Capstone  
Dr Chaojie (Jay) Wang

**Author:**  
Tejaswini Jammi

**GitHub Repository:**  
https://github.com/TejaswiniJammi/Personal-Finance-Chatbot

**LinkedIn Profile:**  
https://www.linkedin.com/in/tejaswini-jammi

**PowerPoint Presentation:**  
(To be added)

**YouTube Video:**  
(To be added)

---

## 2. Background

This project builds an intelligent chatbot that helps users understand their personal finances by analyzing bank statements.

Bank statements are usually provided as unstructured PDF files, making it difficult for users to analyze spending patterns or track income. This project automates data extraction and enables users to interact with their financial data using natural language.

**Research Questions:**
- Can OCR and LLMs extract structured financial data from bank statements?
- Can users query their financial data using natural language?
- Can dashboards improve financial understanding?

---

## 3. Data

**Data Sources:**  
User-uploaded bank statement PDF files (debit and credit)

**Data Size:**  
Approximately 1–3 MB per PDF statement

**Data Shape:**  
1,000–5,000 rows per user  
15–20 columns per transaction

**Time Period:**  
Monthly bank statements (user-dependent)

**What Does Each Row Represent?**  
One financial transaction

**Data Dictionary (Key Columns):**

| Column Name | Data Type | Description |
|------------|-----------|-------------|
| transaction_date | Date | Date of transaction |
| description | Text | Transaction description |
| amount | Float | Transaction amount |
| category | Categorical | Expense or income category |
| vendor | Text | Merchant or person |
| account_type | Categorical | Debit or Credit |

**Target Variable:**  
Transaction category

**Feature Variables:**  
Amount, description, vendor, date, account type

---

## 4. Exploratory Data Analysis (EDA)

EDA was performed using Jupyter Notebook.

Key steps:
- Summary statistics of income and expenses
- Monthly spending trends
- Category-wise expense analysis
- Vendor-based spending analysis

Data cleaning included:
- Removing duplicate transactions
- Standardizing date formats
- Normalizing currency values
- Cleaning transaction descriptions

Text data was preprocessed using normalization and tokenization.  
The final dataset follows tidy data principles, with one row per transaction and one column per attribute.

---

## 5. Model Training

This project uses pre-trained **Large Language Models (LLMs)** instead of traditional supervised machine learning models.

**Models Used:**
- LLMs for extracting structured data, inferring categories, and translating natural language queries to SQL

**Training Approach:**
- Prompt-based inference
- No train/test split required
- Rule-based validation of outputs

**Python Packages:**
- pandas  
- SQLAlchemy  
- spaCy  
- Streamlit  
- Plotly Express  

**Development Environment:**
- Local laptop
- Jupyter Notebook
- GitHub
- Neon PostgreSQL

**Model Evaluation:**
- Accuracy of extracted transactions
- Correctness of generated SQL queries
- Quality of chatbot responses

---

## 6. Application of the Trained Models

A web application was developed using **Streamlit** to allow users to interact with their financial data.

**Application Workflow:**  
User → Streamlit App → OCR → LLM Processing → PostgreSQL → Chatbot & Dashboards

**Key Features:**
- PDF upload
- Automated data extraction
- Natural language chatbot
- Spending and income summaries
- Interactive dashboards

---

## 7. Conclusion

This project demonstrates how OCR and LLMs can be combined to build a personal finance chatbot that enables users to understand their financial behavior through conversational interaction.

**Limitations:**
- OCR accuracy depends on statement quality
- Limited support for different bank formats

**Lessons Learned:**
- Data cleaning is essential
- Prompt design strongly affects results
- Combining AI with rule-based logic improves reliability

**Future Work:**
- Budget recommendations
- Investment insights
- Support for additional banks

---

## 8. References

- OpenAI Documentation  
- Streamlit Documentation  
- PostgreSQL Documentation  
- UMBC DATA606 Course Materials  
