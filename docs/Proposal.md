# WealthTrack : Intelligent Expense & Investment Assistant

**Prepared for**: UMBC Data Science Master’s Degree Capstone – Dr. Chaojie (Jay) Wang  

**Author**: Tejaswini Jammi 

- **GitHub Repository**: *https://github.com/Tejaswini2212/UMBC-DATA606-Capstone*
- **LinkedIn Profile**: *https://www.linkedin.com/in/tejaswinijammi*  

## 2. Background
Personal finance management has become increasingly challenging in today’s digital world. People often struggle to keep track of their spending across multiple accounts, which leads to overspending and poor saving habits. While banks provide statements, they are not user-friendly for day-to-day financial decision-making. At the same time, many individuals hesitate to invest due to a lack of awareness about safe and suitable options.

**💵What is this about**
- This project is about creating a financial chatbot that helps users manage money more effectively. It can read bank statements (CSV/PDF), categorize expenses, track savings, and suggest suitable investment options based on user risk levels. Using conversational AI, it provides an easy way for users to ask questions about their finances and receive personalized, actionable advice.

**Why it matters**  
- Managing personal finances is often confusing and time-consuming. Many people struggle with tracking expenses, saving consistently, and choosing safe investments. A chatbot that simplifies these tasks makes financial management more accessible, personalized, and effective, acting as a virtual advisor without the need for expert knowledge.

**Research Questions**  
1.How can expenses be automatically categorized from raw bank transaction data?</br>
2.What methods can be used to analyze spending and identify savings potential?</br>
3.How can the chatbot provide personalized, risk-aware investment recommendations? </br>


## 3. Data

#### Data Sources
**Personal Finance Dataset (Bank Transactions)**
Source: Kaggle [personal_transactions.csv][https://www.kaggle.com/datasets/uom220338n/personal-finance-dataset?select=personal_transactions.csv]

**Financial Market Data (Investment APIs)**
Sources: Yahoo Finance (yfinance)
Provides stock, ETF, and crypto market data (prices, returns, risk metrics).
Free to use: for data retrieval.

#### Data Size & Shape
Personal Finance Dataset:
Size: ~100 KB
Rows: ~1,200 transactions
Columns: 6

Financial API Dataset:
Size per API call: <1 MB
Rows: Number of instruments queried (~10–50)
Columns: 5–10

**Time Period**
Bank transactions: 2018 (monthly transactions)
Financial API: Real-time 

**Data Dictionary**
Personal Finance Dataset
| Column Name      | Data Type   | Definition / Units                  | Potential Values / Categories                                                |
| ---------------- | ----------- | ----------------------------------- | ---------------------------------------------------------------------------- |
| Date             | DateTime    | Transaction date                    | YYYY-MM-DD HH\:MM\:SS                                                        |
| Description      | String      | Merchant or transaction description | Amazon, Netflix, Gas Company, etc.                                           |
| Amount           | Float       | Transaction value                   | Positive for credit, negative for debit                                      |
| Transaction Type | Categorical | Type of transaction                 | debit, credit                                                                |
| Category         | Categorical | Expense category                    | Shopping, Restaurants, Utilities, Paycheck, Mortgage & Rent, Groceries, etc. |
| Account Name     | Categorical | Account used for the transaction    | Platinum Card, Silver Card, Checking, etc.                                   |

Target / Label: Category (expense classification)
Features / Predictors: Description, Amount, Transaction Type, Account Name

**Financial API Dataset**
| Column Name     | Data Type   | Definition / Units                | Potential Values / Categories    |
| --------------- | ----------- | --------------------------------- | -------------------------------- |
| Ticker          | String      | Symbol of the instrument          | SPY, VTI, BTC-USD                |
| Name            | String      | Name of the instrument            | S\&P 500 ETF, Bitcoin            |
| Market Price    | Float       | Current market price              | e.g., 555.20                     |
| 1Y Return       | Float       | One-year historical return (%)    | e.g., 12.5                       |
| Volatility/Risk | Float       | Standard deviation or risk metric | e.g., 0.15                       |
| Category        | Categorical | Investment type (risk-based)      | Low Risk, Medium Risk, High Risk |

Features / Predictors: Market Price, 1Y Return, Volatility/Risk, Category

#### Approach for this Project
1.Expense Tracking → Parse user transactions and calculate current savings.</br>
2.Investment Scoring → Filter and rank affordable investments based on risk and expected return.</br>
3.Recommendation Display → Show top investment options and savings summary via Streamlit.
