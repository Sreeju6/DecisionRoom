import pandas as pd

file_path = "data/raw/indian_startup_funding_2020_2025_sample.csv"

df = pd.read_csv(file_path)

print("\n========== UNIQUE VALUES ==========")

print("\nUnique Startups:")
print(df["Startup"].nunique())

print("\nUnique Industries:")
print(df["Industry"].nunique())

print("\nUnique SubVerticals:")
print(df["SubVertical"].nunique())

print("\nUnique Cities:")
print(df["City"].nunique())

print("\nUnique Investment Types:")
print(df["InvestmentType"].nunique())


print("\n========== INVESTMENT TYPES ==========")
print(df["InvestmentType"].value_counts())


print("\n========== INDUSTRIES ==========")
print(df["Industry"].value_counts())


print("\n========== TOP CITIES ==========")
print(df["City"].value_counts().head(15))


print("\n========== INVESTMENT AMOUNT ==========")
print("Minimum:", df["InvestmentAmount_USD"].min())
print("Maximum:", df["InvestmentAmount_USD"].max())
print("Mean:", df["InvestmentAmount_USD"].mean())
print("Median:", df["InvestmentAmount_USD"].median())


print("\n========== ZERO/NEGATIVE INVESTMENTS ==========")
print(
    (df["InvestmentAmount_USD"] <= 0).sum()
)


print("\n========== DATE RANGE ==========")
df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)

print("Earliest:", df["Date"].min())
print("Latest:", df["Date"].max())


print("\n========== TOP STARTUPS BY NUMBER OF FUNDING RECORDS ==========")
print(df["Startup"].value_counts().head(15))


print("\n========== SAMPLE RECORDS ==========")
print(df.sample(10, random_state=42))