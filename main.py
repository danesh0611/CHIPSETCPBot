import discord
from discord.ext import commands, tasks
import os
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import json
import requests
import uuid
import io

# ================== CONFIG ==================

TOKEN = os.getenv("TOKEN")

SHEET_ID = "1qPoJ0uBdVCQZMZYWRS6Bt60YjJnYUkD4OePSTRMiSrI"
DRIVE_FOLDER_ID = "1_5_PPNN9YLOOC00Z-Wg1uhmDKfcglN5G"

SHEETS_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
DRIVE_SCOPE = ["https://www.googleapis.com/auth/drive"]

# ================== GOOGLE SHEETS ==================

sheets_creds = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(os.getenv("GOOGLE_CREDS")),
    SHEETS_SCOPE
)

sheet_client = gspread.authorize(sheets_creds)
sheet = sheet_client.open_by_key(SHEET_ID)

# ================== GOOGLE DRIVE ==================

drive_creds = ServiceAccountCredentials.from_json_keyfile_dict(
    json.loads(os.getenv("DRIVE_CREDS")),
    DRIVE_SCOPE
)

drive_service = build("drive", "v3", credentials=drive_creds)

# ================== BOT SETUP ==================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

registered_users = set()  # discord usernames only
submissions_today = {}    # memory counter only (resets on restart)

# ================== HELPERS ==================

def is_valid_date(name):
    try:
        datetime.datetime.strptime(name, "%Y-%m-%d")
        return True
    except:
        return False

def load_registered_users():
    try:
        ws = sheet.worksheet("Registered_Users")
    except:
        ws = sheet.add_worksheet("Registered_Users", rows=200, cols=1)
        ws.append_row(["Discord Username"])
        return

    for row in ws.col_values(1)[1:]:
        registered_users.add(row)

def get_today_sheet():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        ws = sheet.worksheet(today)
    except:
        ws = sheet.add_worksheet(today, rows=300, cols=4)
        ws.append_row(["Date", "Username", "Screenshot", "Problem"])
    return ws

def upload_to_drive(discord_url):
    r = requests.get(discord_url)
    r.raise_for_status()

    ext = discord_url.split('.')[-1].split('?')[0]
    if ext not in ["png", "jpg", "jpeg", "gif", "webp"]:
        ext = "png"

    filename = f"{uuid.uuid4()}.{ext}"

    media = MediaIoBaseUpload(
        io.BytesIO(r.content),
        mimetype=f"image/{ext}",
        resumable=False
    )

    file = drive_service.files().create(
        body={"name": filename, "parents": [DRIVE_FOLDER_ID]},
        media_body=media,
        fields="id"
    ).execute()

    drive_service.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"}
    ).execute()

    return f"https://drive.google.com/uc?id={file['id']}"

# ================== EVENTS ==================

@bot.event
async def on_ready():
    load_registered_users()
    daily_reminder.start()
    print(f"✅ Bot online: {bot.user}")

# ================== COMMANDS ==================

@bot.command()
async def register(ctx):
    if ctx.guild:
        return await ctx.reply("DM me to register 🙂")

    uname = ctx.author.name
    if uname in registered_users:
        return await ctx.reply("Already registered 🤝")

    registered_users.add(uname)
    ws = sheet.worksheet("Registered_Users")
    ws.append_row([uname])

    await ctx.reply("✅ Registered successfully!")

@bot.command()
async def submit(ctx, *, problem="No Name"):
    if ctx.guild:
        return await ctx.reply("Submit in DM only 🙂")

    uname = ctx.author.name
    if uname not in registered_users:
        return await ctx.reply("❌ Please /register first")

    if not ctx.message.attachments:
        return await ctx.reply("⚠️ Attach screenshot")

    await ctx.reply("📤 Uploading image…")

    img_url = upload_to_drive(ctx.message.attachments[0].url)

    ws = get_today_sheet()
    ws.append_row([
        str(datetime.date.today()),
        uname,
        img_url,
        problem
    ])

    submissions_today[uname] = submissions_today.get(uname, 0) + 1

    await ctx.reply(f"🔥 Submission #{submissions_today[uname]} saved!")

@bot.command()
async def status(ctx):
    if ctx.guild:
        return await ctx.reply("DM me 🙂")

    count = submissions_today.get(ctx.author.name, 0)
    if count:
        await ctx.reply(f"✔ You submitted {count} today")
    else:
        await ctx.reply("❌ No submissions yet")

@bot.command()
async def notcompleted(ctx):
    if not ctx.guild or not ctx.author.guild_permissions.administrator:
        return await ctx.reply("Admin only")

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        ws = sheet.worksheet(today)
    except:
        return await ctx.reply("No submissions today")

    submitted = set(ws.col_values(2)[1:])
    pending = [u for u in registered_users if u not in submitted]

    if not pending:
        return await ctx.reply("🎉 Everyone submitted!")

    msg = "\n".join(f"• {u}" for u in pending)
    await ctx.reply(f"❌ Not submitted today:\n\n{msg}")

@bot.command()
async def summarize(ctx):
    if not ctx.guild or not ctx.author.guild_permissions.administrator:
        return await ctx.reply("Admin only")

    today = datetime.datetime.now()
    title = f"Summary-{today.strftime('%B')}-{today.year}"

    try:
        sheet.worksheet(title)
        return await ctx.reply("Summary already exists")
    except:
        sws = sheet.add_worksheet(title, rows=200, cols=4)
        sws.append_row(["Username", "Days Submitted", "Total Days", "Consistency %"])

    day_sheets = [ws for ws in sheet.worksheets() if is_valid_date(ws.title)]
    total_days = len(day_sheets)

    for user in registered_users:
        days = sum(1 for ws in day_sheets if user in ws.col_values(2))
        percent = (days / total_days * 100) if total_days else 0
        sws.append_row([user, days, total_days, f"{percent:.1f}%"])

    await ctx.reply("📊 Summary generated")

# ================== REMINDER ==================

@tasks.loop(time=datetime.time(hour=22, minute=0))
async def daily_reminder():
    for uname in registered_users:
        if uname not in submissions_today:
            user = discord.utils.get(bot.users, name=uname)
            if user:
                try:
                    await user.send("⏰ Reminder: submit today’s CP")
                except:
                    pass
    submissions_today.clear()

# ================== RUN ==================

bot.run(TOKEN)
