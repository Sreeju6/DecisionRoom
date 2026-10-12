import requests


URL = "https://www.missionstartupkarnataka.org/"
OUTPUT = "documents/government/Karnataka_startup_policy.txt"


headers = {
    "User-Agent": "Mozilla/5.0"
}


response = requests.get(
    URL,
    headers=headers,
    timeout=30
)

print("HTTP status:", response.status_code)

if response.status_code != 200:
    print("Failed to download Karnataka source.")
    exit()

html = response.text

print("Downloaded characters:", len(html))


# Remove HTML tags
from bs4 import BeautifulSoup

soup = BeautifulSoup(
    html,
    "html.parser"
)

text = soup.get_text(
    "\n",
    strip=True
)


with open(
    OUTPUT,
    "w",
    encoding="utf-8"
) as f:
    f.write(text)


print("Extracted characters:", len(text))

print("\nRestored:")
print(OUTPUT)