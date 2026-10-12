import pandas as pd
import requests

indicators = {
    "NY.GDP.MKTP.CD": "GDP_USD",
    "NY.GDP.MKTP.KD.ZG": "GDP_Growth_Percent",
    "SP.POP.TOTL": "Population",
    "IT.NET.USER.ZS": "Internet_Users_Percent"
}

all_data = []

for indicator_code, indicator_name in indicators.items():

    url = (
        f"https://api.worldbank.org/v2/country/IND/"
        f"indicator/{indicator_code}"
        f"?format=json&date=2020:2024&per_page=100"
    )

    response = requests.get(url, timeout=30)

    print(f"Getting {indicator_name}...")

    if response.status_code != 200:
        print("Error:", response.status_code)
        continue

    result = response.json()

    if not isinstance(result, list) or len(result) < 2:
        print("No data returned for:", indicator_name)
        continue

    for item in result[1]:
        all_data.append({
            "Country": item["country"]["value"],
            "Year": int(item["date"]),
            "Indicator": indicator_name,
            "Value": item["value"]
        })


df = pd.DataFrame(all_data)

df = df.pivot(
    index=["Country", "Year"],
    columns="Indicator",
    values="Value"
).reset_index()

df.columns.name = None

output_file = "data/processed/worldbank_india_market.csv"

df.to_csv(output_file, index=False)

print("\n========== WORLD BANK DATA ==========")
print(df)

print("\n========== SHAPE ==========")
print(df.shape)

print("\nSaved to:")
print(output_file)