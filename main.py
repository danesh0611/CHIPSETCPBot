import discord
from discord.ext import commands, tasks
import os
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------- Google Sheets Setup ----------
SHEET_ID = "1qPoJ0uBdVCQZMZYWRS6Bt60YjJnYUkD4OePSTRMiSrI"  # your sheet ID

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)

# Monthly sheet reference
monthly_sheet = sheet.sheet1  # first sheet

# ---------- Discord Bot Setup ----------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

registered_users = set()
submissions_today = set()

def get_today_sheet():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        return sheet.worksheet(today)
    except:
        return sheet.add_worksheet(title=today, rows=200, cols=5)

@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user}")
    update_monthly_stats.start()
    daily_reminder.start()

@bot.command()
async def register(ctx):
    user = ctx.author.name
    registered_users.add(user)
    await ctx.reply(f"Registered: {user}")

@bot.command()
async def submit(ctx, *, problem_name="No Name"):
    if not ctx.message.attachments:
        return await ctx.reply("Attach screenshot also!")

    att = ctx.message.attachments[0].url
    user = ctx.author.name
    submissions_today.add(user)

    today_ws = get_today_sheet()
    today_ws.append_row([str(datetime.datetime.now().date()), user, att, problem_name])

    await ctx.reply(f"Submission saved: {user} - {problem_name}")

@bot.command()
async def status(ctx):
    user = ctx.author.name
    if user in submissions_today:
        await ctx.reply("You submitted today! 💪🔥")
    else:
        await ctx.reply("You haven't submitted yet 😬")

@bot.command()
async def report(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.reply("Admin only ❌")

    pending = registered_users - submissions_today
    submitted = submissions_today

    await ctx.send(
        f"📌 **Daily Report**\n\n"
        f"✔ Submitted: {len(submitted)} — {submitted}\n"
        f"❌ Pending: {len(pending)} — {pending}"
    )

# ---------- Scheduled Tasks ----------
@tasks.loop(time=datetime.time(hour=22, minute=0)) # 10 PM IST
async def daily_reminder():
    channel = discord.utils.get(bot.get_all_channels(), name="cp-submissions")
    if channel:
        pending = registered_users - submissions_today
        if pending:
            await channel.send(f"Reminder 🚨 Pending Members: {pending}")
    submissions_today.clear()

@tasks.loop(hours=24)
async def update_monthly_stats():
    for idx, user in enumerate(registered_users, start=2):
        total_days = datetime.datetime.now().day
        submitted_count = monthly_sheet.cell(idx, 2).value
        monthly_sheet.update_acell(f"A{idx}", user)
        monthly_sheet.update_acell(f"B{idx}", total_days)
        monthly_sheet.update_acell(f"C{idx}", len(submissions_today))
        monthly_sheet.update_acell(f"D{idx}", f"{int((len(submissions_today)/total_days)*100)}%")

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
