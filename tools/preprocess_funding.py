import pandas as pd

# ==========================================
# 1. LOAD RAW FUNDING DATA
# ==========================================

input_file = "data/raw/indian_startup_funding_2020_2025_sample.csv"

df = pd.read_csv(input_file)

print("Original shape:", df.shape)

# ==========================================
# 2. CLEAN COLUMN NAMES
# ==========================================

df.columns = df.columns.str.strip()

# ==========================================
# 3. CONVERT DATE
# ==========================================

df["Date"] = pd.to_datetime(
    df["Date"],
    dayfirst=True,
    errors="coerce"
)

# ==========================================
# 4. CREATE YEAR COLUMN
# ==========================================

df["Year"] = df["Date"].dt.year

# ==========================================
# 5. CLEAN TEXT COLUMNS
# ==========================================

text_columns = [
    "Startup",
    "Industry",
    "SubVertical",
    "City",
    "Investors",
    "InvestmentType"
]

for column in text_columns:
    df[column] = df[column].astype(str).str.strip()

# ==========================================
# 6. CHECK INVESTMENT AMOUNT
# ==========================================

df["InvestmentAmount_USD"] = pd.to_numeric(
    df["InvestmentAmount_USD"],
    errors="coerce"
)

# ==========================================
# 7. REMOVE INVALID RECORDS
# ==========================================

df = df.dropna(
    subset=[
        "Startup",
        "Industry",
        "City",
        "InvestmentAmount_USD",
        "Date"
    ]
)

df = df[df["InvestmentAmount_USD"] > 0]

# ==========================================
# 8. REMOVE DUPLICATES
# ==========================================

df = df.drop_duplicates()

# ==========================================
# 9. CREATE FUNDING CATEGORY
# ==========================================

def categorize_funding(amount):
    if amount < 100000:
        return "Below 100K"
    elif amount < 1000000:
        return "100K-1M"
    elif amount < 10000000:
        return "1M-10M"
    else:
        return "Above 10M"


df["Funding_Category"] = df["InvestmentAmount_USD"].apply(
    categorize_funding
)

# ==========================================
# 10. SAVE PROCESSED DATA
# ==========================================

output_file = "data/processed/startup_funding_processed.csv"

df.to_csv(output_file, index=False)

# ==========================================
# 11. DISPLAY RESULTS
# ==========================================

print("\n========== PROCESSED DATA ==========")
print(df.head())

print("\n========== DATASET SHAPE ==========")
print(df.shape)

print("\n========== DATA TYPES ==========")
print(df.dtypes)

print("\n========== MISSING VALUES ==========")
print(df.isnull().sum())

print("\n========== YEAR DISTRIBUTION ==========")
print(df["Year"].value_counts().sort_index())

print("\n========== FUNDING CATEGORY ==========")
print(df["Funding_Category"].value_counts())

print("\nProcessed file saved to:")
print(output_file)