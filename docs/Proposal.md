# Personal Financial and Investment Chatbot

**Prepared for**: UMBC Data Science Master’s Degree Capstone – Dr. Chaojie (Jay) Wang  

**Author**: Tejaswini Jammi 

- **GitHub Repository**: *https://github.com/Tejaswini2212/UMBC-DATA606-Capstone*
- **LinkedIn Profile**: *https://www.linkedin.com/in/tejaswinijammi*  

## 2. Background

Hypertension (high blood pressure) is a leading risk factor for cardiovascular disease and stroke.  
This project develops a machine-learning regression model to **predict systolic and diastolic blood pressure** using demographic, dietary, physical activity, smoking, and alcohol indicators derived from the U.S. **National Health and Nutrition Examination Survey (NHANES)**.

**Why it matters**  
- Enables early detection of elevated blood pressure risk.  
- Highlights modifiable lifestyle factors—such as sodium intake, exercise, smoking, and drinking—that can guide personal and public-health interventions.  
- Demonstrates an end-to-end data science workflow with real public health data.

**Research Questions**  
1. To what extent can demographic, diet, physical activity, smoking, and alcohol variables predict blood pressure?  
2. Which factors contribute most to systolic and diastolic blood pressure?


## 3. Data

#### Data Sources
NHANES survey cycles covering **August 2021 – August 2023**  
(publicly available at [https://www.cdc.gov/nchs/nhanes/](https://www.cdc.gov/nchs/nhanes/)):
#### Data Shape
- Rows: 7518 
- Columns: 17
- Approx file size (MB): 1.02

To build a single machine-learning-ready table, **combined several NHANES component datasets** by joining on the unique participant ID `SEQN`:

- **Examination**: BPX (Blood Pressure), BMX (Body Measures)
- **Demographics**: DEMO
- **Dietary**: DR1TOT (Day-1 nutrient intake)
- **Physical Activity**: PAQ
- **Smoking**: SMQ
- **Alcohol**: ALQ

This integration step ensured that each participant’s demographics, body measures, diet, activity level, smoking history, and alcohol consumption are available in **one dataset**.

#### Data Details

- **Time period covered**  
  August 2021 – August 2023 (NHANES survey cycles for those two years)

- **Observation unit**  
  Each row represents **one individual NHANES participant**, with all lifestyle, demographic, and health measurements merged into a single record.

- **Data dictionary (key columns)**  

| Column | Type | Definition / Units | Categories / Encoded Labels |
|--------|------|--------------------|------------------------------|
| `Participant_ID` | int | Unique NHANES participant ID | e.g., 130378 |
| `Systolic_BP` | float | Mean systolic blood pressure (mmHg) | – |
| `Diastolic_BP` | float | Mean diastolic blood pressure (mmHg) | – |
| `Age_Years` | int | Age of participant | e.g., 43 |
| `Gender` | category | Biological sex | 0 = Male, 1 = Female |
| `Race_Ethnicity` | category | Race/ethnicity group | 0 = Non-Hispanic White, 1 = Non-Hispanic Black, 2 = Mexican American, 3 = Other (Other Hispanic, Non-Hispanic Asian, Multiracial) |
| `BMI` | float | Body Mass Index (kg/m²) | e.g., 27.5 |
| `Weight_kg` | float | Body weight | e.g., 74.0 |
| `Height_cm` | float | Body height | e.g., 172.0 |
| `Sodium_mg` | float | Daily sodium intake | e.g., 3200 |
| `Potassium_mg` | float | Daily potassium intake | e.g., 2900 |
| `Calories_kcal` | float | Total daily calorie intake | e.g., 2100 |
| `Vigorous_Activity_Days` | int | Days/week of vigorous activity | 0–7 |
| `Moderate_Activity_Days` | int | Days/week of moderate activity | 0–7 |
| `Ever_Smoked_100_Cigs` | category | Ever smoked ≥100 cigarettes | 0 = No, 1 = Yes |
| `Current_Smoking_Status` | category | Current smoking frequency | 0 = Not at all, 1 = Some days, 2 = Every day |
| `Drinks_per_Week` | float | Estimated alcoholic drinks per week | e.g., 2.5 |
| `Had_12_Drinks_Lifetime` | category | Ever consumed ≥12 drinks in lifetime | 0 = No, 1 = Yes |

- **Target / Label variables for ML model**  
  - `Systolic_BP`  
  - `Diastolic_BP`

- **Feature / Predictor candidates**  
  - Demographics: `Age_Years`, `Gender`, `Race_Ethnicity`
  - Body measures: `BMI`, `Weight_kg`, `Height_cm`
  - Diet: `Sodium_mg`, `Potassium_mg`, `Calories_kcal`
  - Physical activity: `Vigorous_Activity_Days`, `Moderate_Activity_Days`
  - Lifestyle habits: `Ever_Smoked_100_Cigs`, `Current_Smoking_Status`, `Drinks_per_Week`
