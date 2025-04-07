import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
from role_config import ROLE_GROUP, LOG_CHANNEL_ID
import json
# import datetime
from datetime import datetime, UTC
from keep_alive import keep_alive

keep_alive()

ROLE_DATA_FILE = "role_data.json"

def load_role_data():
    try:
        with open(ROLE_DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_role_data(data):
    with open(ROLE_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True  # Needed for member updates
intents.guilds = True

bot = commands.Bot(command_prefix="!rlrnk", intents=intents)

@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="You bozo's pick up more than one 'Rank Role' 😒")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f"Bot is online as {bot.user}")

@bot.event
async def on_member_update(before, after):
    if before.roles == after.roles:
        return  # No role change
    
    allowed_roles = set(ROLE_GROUP)
    user_roles = set(after.roles)
    matching_roles = [role for role in user_roles if role.id in allowed_roles]

    if len(matching_roles) <= 1:
        return  # No conflict

    # Find the most recently added role
    new_roles = [role for role in after.roles if role not in before.roles and role.id in allowed_roles]
    if not new_roles:
        return
    
    newest_role = new_roles[0]
    roles_to_remove = [role for role in matching_roles if role != newest_role]

    # Attempt to remove older roles
    try:
        await after.remove_roles(*roles_to_remove, reason="Only one role from group allowed")
    except discord.Forbidden:
        print(f"❌ Cannot remove roles from {after.display_name} — missing permissions.")
        return
    except discord.HTTPException as e:
        print(f"❌ HTTP error while removing roles: {e}")
        return

    # Send DM to user
    try:
        embed_dm = discord.Embed(
            title="Your Rank Roles were re-assigned",
            description="You can only have one Rank Role.",
            color=discord.Color.orange(),
            timestamp=datetime.now(UTC)
        )
        embed_dm.add_field(
            name="Removed Role",
            value=", ".join(r.name for r in roles_to_remove),
            inline=False
        )
        embed_dm.add_field(
            name="New Role",
            value=newest_role.name,
            inline=False
        )
        await after.send(embed=embed_dm)
    except discord.Forbidden:
        print(f"❌ Could not DM {after.display_name}")

    # Send log to channel
    try:
        log_channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        if isinstance(log_channel, discord.TextChannel):
            embed_log = discord.Embed(
                title="Rank Role Changelog",
                color=discord.Color.blue(),
                timestamp=datetime.now(UTC)
            )
            embed_log.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed_log.add_field(
                name="Removed Role",
                value=", ".join(f"<@&{r.id}>" for r in roles_to_remove),
                inline=False
            )
            embed_log.add_field(
                name="Kept Role",
                value=f"<@&{newest_role.id}>",
                inline=False
            )
            await log_channel.send(embed=embed_log)
        else:
            print("⚠️ Log channel is not a text channel")
    except Exception as e:
        print(f"❌ Failed to log to channel: {e}")

    # Save to JSON
    role_data = load_role_data()
    role_data[str(after.id)] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "removed_roles": [r.id for r in roles_to_remove],
        "new_role": newest_role.id
    }
    save_role_data(role_data)
bot.run(TOKEN)
