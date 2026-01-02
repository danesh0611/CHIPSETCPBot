import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "service_account.json", SCOPE
)
client = gspread.authorize(creds)

# 🔴 SAME spreadsheet (form responses + daily sheets)
sheet = client.open("YOUR_SPREADSHEET_NAME")

form_ws = sheet.worksheet("Form_Responses")

rows = form_ws.get_all_records()

def get_day_sheet(date_str):
    try:
        return sheet.worksheet(date_str)
    except:
        ws = sheet.add_worksheet(date_str, rows=300, cols=4)
        ws.append_row(["Date", "Username", "Screenshot", "Problem"])
        return ws

for row in rows:
    name = row["NAME"]
    problem = row["PROBLEM NAME"]
    date = row["DATE OF SUBMISSION"]
    screenshot = row["SCREENSHOT"]

    if not date:
        continue

    day_ws = get_day_sheet(date)

    # 🔒 DUPLICATE CHECK
    existing = day_ws.get_all_values()
    already_exists = any(
        r[1] == name and r[3] == problem
        for r in existing[1:]
    )

    if already_exists:
        continue

    day_ws.append_row([
        date,
        name,
        screenshot,
        problem
    ])

print("✅ Form data synced to daily sheets")
