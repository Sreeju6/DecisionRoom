import pandas as pd

# ==========================================
# 1. LOAD PROCESSED FUNDING DATA
# ==========================================

input_file = "data/processed/startup_funding_processed.csv"

df = pd.read_csv(input_file)

print("Original funding records:", len(df))

# ==========================================
# 2. CITY → STATE MAPPING
# ==========================================

city_to_state = {
    "Delhi": "Delhi",
    "Kolkata": "West Bengal",
    "Pune": "Maharashtra",
    "Chennai": "Tamil Nadu",
    "Ahmedabad": "Gujarat",
    "Gurugram": "Haryana",
    "Bengaluru": "Karnataka",
    "Mumbai": "Maharashtra",
    "Noida": "Uttar Pradesh",
    "Hyderabad": "Telangana"
}

# ==========================================
# 3. CREATE STATE COLUMN
# ==========================================

df["State/UT"] = df["City"].map(city_to_state)

# Check whether every city was mapped
print("\n========== UNMAPPED CITIES ==========")
print(df[df["State/UT"].isna()]["City"].unique())

# ==========================================
# 4. AGGREGATE FUNDING BY STATE
# ==========================================

state_funding = (
    df.groupby("State/UT")
    .agg(
        Funding_Records=("Startup", "count"),
        Unique_Startups=("Startup", "nunique"),
        Total_Funding_USD=("InvestmentAmount_USD", "sum"),
        Average_Funding_USD=("InvestmentAmount_USD", "mean"),
        Median_Funding_USD=("InvestmentAmount_USD", "median")
    )
    .reset_index()
)

# ==========================================
# 5. ROUND FUNDING VALUES
# ==========================================

state_funding["Average_Funding_USD"] = (
    state_funding["Average_Funding_USD"].round(2)
)

state_funding["Median_Funding_USD"] = (
    state_funding["Median_Funding_USD"].round(2)
)

# ==========================================
# 6. SORT BY TOTAL FUNDING
# ==========================================

state_funding = state_funding.sort_values(
    "Total_Funding_USD",
    ascending=False
)

# ==========================================
# 7. SAVE STATE-LEVEL FUNDING DATA
# ==========================================

output_file = "data/processed/funding_by_state.csv"

state_funding.to_csv(
    output_file,
    index=False
)

# ==========================================
# 8. DISPLAY RESULTS
# ==========================================

print("\n========== FUNDING BY STATE ==========")
print(state_funding.to_string(index=False))

print("\n========== DATASET SHAPE ==========")
print(state_funding.shape)

print("\nSaved to:")
print(output_file)