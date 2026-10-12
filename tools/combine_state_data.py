import pandas as pd

# ==========================================
# 1. LOAD PROCESSED DATASETS
# ==========================================

dpiit_file = "data/processed/dpiit_startups_processed.csv"
funding_file = "data/processed/funding_by_state.csv"

dpiit = pd.read_csv(dpiit_file)
funding = pd.read_csv(funding_file)

# ==========================================
# 2. MERGE USING STATE/UT
# ==========================================

combined = pd.merge(
    dpiit,
    funding,
    on="State/UT",
    how="left"
)

# ==========================================
# 3. HANDLE STATES WITHOUT FUNDING DATA
# ==========================================

funding_columns = [
    "Funding_Records",
    "Unique_Startups",
    "Total_Funding_USD",
    "Average_Funding_USD",
    "Median_Funding_USD"
]

combined[funding_columns] = combined[funding_columns].fillna(0)

# ==========================================
# 4. CREATE FUNDING DATA AVAILABILITY FLAG
# ==========================================

combined["Funding_Data_Available"] = (
    combined["Funding_Records"] > 0
)

# ==========================================
# 5. SAVE COMBINED DATA
# ==========================================

output_file = "data/processed/state_decision_dataset.csv"

combined.to_csv(output_file, index=False)

# ==========================================
# 6. DISPLAY RESULTS
# ==========================================

print("\n========== COMBINED DATA ==========")
print(combined.to_string(index=False))

print("\n========== DATASET SHAPE ==========")
print(combined.shape)

print("\n========== FUNDING DATA AVAILABLE ==========")
print(
    combined["Funding_Data_Available"].value_counts()
)

print("\nSaved to:")
print(output_file)