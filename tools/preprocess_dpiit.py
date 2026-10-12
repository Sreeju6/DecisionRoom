import pandas as pd

# ==========================================
# 1. LOAD RAW DPIIT DATA
# ==========================================

input_file = "data/raw/dpiit_startups_2020_2024.csv"

df = pd.read_csv(input_file)

print("Original shape:", df.shape)

# ==========================================
# 2. REMOVE UNNECESSARY SERIAL NUMBER
# ==========================================

df = df.drop(columns=["Sl. No."])

# ==========================================
# 3. HANDLE MISSING VALUES
# ==========================================

year_columns = ["2020", "2021", "2022", "2023", "2024"]

df[year_columns] = df[year_columns].fillna(0)

# ==========================================
# 4. CONVERT YEAR COLUMNS TO INTEGER
# ==========================================

df[year_columns] = df[year_columns].astype(int)

# ==========================================
# 5. CREATE TOTAL STARTUPS (2020-2024)
# ==========================================

df["Total_Startups_2020_2024"] = df[year_columns].sum(axis=1)

# ==========================================
# 6. CALCULATE GROWTH
# ==========================================

df["Startup_Growth_2020_2024"] = (
    df["2024"] - df["2020"]
)

# ==========================================
# 7. CALCULATE GROWTH PERCENTAGE
# ==========================================

df["Growth_Percentage"] = 0.0

mask = df["2020"] > 0

df.loc[mask, "Growth_Percentage"] = (
    (df.loc[mask, "2024"] - df.loc[mask, "2020"])
    / df.loc[mask, "2020"]
) * 100

# ==========================================
# 8. SAVE PROCESSED DATA
# ==========================================

output_file = "data/processed/dpiit_startups_processed.csv"

df.to_csv(output_file, index=False)

# ==========================================
# 9. DISPLAY RESULTS
# ==========================================

print("\n========== PROCESSED DATA ==========")
print(df.head())

print("\n========== DATASET SHAPE ==========")
print(df.shape)

print("\n========== MISSING VALUES ==========")
print(df.isnull().sum())

print("\n========== PROCESSED COLUMNS ==========")
print(df.columns.tolist())

print("\nProcessed file saved to:")
print(output_file)