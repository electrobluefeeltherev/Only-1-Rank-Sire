import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
from role_config import ROLE_GROUP, LOG_CHANNEL_ID, LFG_TO_RANK
import json
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
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!rlrnk", intents=intents)

@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="Rank Roles of AIRLF")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print(f"Bot is online as {bot.user}")

@bot.event
async def on_member_update(before, after):
    if before.roles == after.roles:
        return

    # ----- LFG ROLE CHECK -----
    user_role_ids = [r.id for r in after.roles]
    current_rank_role = next((r for r in after.roles if r.id in ROLE_GROUP), None)

    lfg_roles = [r for r in after.roles if r.id in LFG_TO_RANK]
    valid_lfg_roles = []

    for lfg_role in lfg_roles:
        required_ranks = LFG_TO_RANK[lfg_role.id]
        if any(rank in user_role_ids for rank in required_ranks):
            valid_lfg_roles.append(lfg_role)

    if len(valid_lfg_roles) > 1:
        # If user somehow got multiple valid LFG roles, keep the newest one
        new_lfg_role = next((r for r in after.roles if r.id in [r.id for r in valid_lfg_roles] and r not in before.roles), valid_lfg_roles[0])
        roles_to_remove = [r for r in lfg_roles if r != new_lfg_role]
        try:
            await after.remove_roles(*roles_to_remove, reason="Only one LFG role allowed")
        except discord.Forbidden:
            print(f"❌ Cannot remove LFG roles from {after.display_name}")
        # DM the user
        try:
            dm_embed = discord.Embed(
                title="Your LFG roles were updated",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            dm_embed.add_field(name="Kept Role", value=new_lfg_role.name, inline=False)
            dm_embed.add_field(name="Removed Roles", value=", ".join(r.name for r in roles_to_remove), inline=False)
            await after.send(embed=dm_embed)
        except discord.Forbidden:
            print(f"❌ Couldn't DM {after.display_name}")
    elif len(valid_lfg_roles) == 0 and lfg_roles:
        # User has LFG roles but doesn't meet requirements → remove all
        try:
            await after.remove_roles(*lfg_roles, reason="Missing required rank role(s)")
        except discord.Forbidden:
            print(f"❌ Cannot remove invalid LFG roles from {after.display_name}")
        required_ranks_for_first = LFG_TO_RANK[lfg_roles[0].id]
        required_roles = [after.guild.get_role(rid) for rid in required_ranks_for_first if after.guild.get_role(rid)]
        required_names = ", ".join(r.name for r in required_roles)

        try:
            dm_embed = discord.Embed(
                title=f"LFG Role(s) Removed",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            dm_embed.add_field(name="Reason", value=f"You must have one of the following rank roles: **{required_names}**", inline=False)
            dm_embed.add_field(name="Removed", value=", ".join(r.name for r in lfg_roles), inline=False)
            await after.send(embed=dm_embed)
        except discord.Forbidden:
            print(f"❌ Couldn't DM {after.display_name}")

        # Log
        log_embed = discord.Embed(
            title="Invalid LFG Roles Removed",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        log_embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        log_embed.add_field(name="User", value=after.mention)
        log_embed.add_field(name="Removed LFG Roles", value=", ".join(f"<@&{r.id}>" for r in lfg_roles))
        log_embed.add_field(name="Required Rank Role(s)", value=", ".join(f"<@&{r}>" for r in required_ranks_for_first))

        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=log_embed)

            # break  # Only process the first relevant LFG role

    # ----- RANK ROLE CONFLICT CHECK -----
    rank_roles = [r for r in after.roles if r.id in ROLE_GROUP]
    if len(rank_roles) > 1:
        new_role_ids = {r.id for r in after.roles} - {r.id for r in before.roles}
        newest_role = next((r for r in after.roles if r.id in new_role_ids), None)

        if newest_role:
            roles_to_remove = [r for r in rank_roles if r != newest_role]
            try:
                await after.remove_roles(*roles_to_remove, reason="Only one rank role allowed")
            except discord.Forbidden:
                print(f"❌ Cannot remove roles from {after.display_name}")
                return

            # 📨 DM
            embed_dm = discord.Embed(
                title="Your Rank Roles were re-assigned",
                description="You can only have one Rank Role.",
                color=discord.Color.orange(),
                timestamp=datetime.now(UTC)
            )
            embed_dm.add_field(name="Removed Role", value=", ".join(r.name for r in roles_to_remove), inline=False)
            embed_dm.add_field(name="New Role", value=newest_role.name, inline=False)
            try:
                await after.send(embed=embed_dm)
            except discord.Forbidden:
                print(f"❌ Could not DM {after.display_name}")

            # 📝 Log
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
            except Exception as e:
                print(f"❌ Failed to log to channel: {e}")

            # Save the change
            role_data = load_role_data()
            role_data[str(after.id)] = {
                "timestamp": datetime.now(UTC).isoformat(),
                "removed_roles": [r.id for r in roles_to_remove],
                "new_role": newest_role.id
            }
            save_role_data(role_data)

bot.run(TOKEN)
