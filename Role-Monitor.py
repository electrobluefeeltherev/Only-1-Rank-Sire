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
    current_rank_role = next((r for r in after.roles if r.id in ROLE_GROUP), None)
    new_roles = [role for role in after.roles if role not in before.roles]

    for role in new_roles:
        lfg_role_id = role.id

        if lfg_role_id in LFG_TO_RANK:
            required_rank_ids = LFG_TO_RANK[lfg_role_id]
            user_role_ids = [r.id for r in after.roles]
            has_required = any(rank_id in user_role_ids for rank_id in required_rank_ids)

            if not has_required:
                try:
                    await after.remove_roles(role, reason="Missing required rank role.")
                except discord.Forbidden:
                    print(f"❌ Cannot remove {role.name} from {after.display_name}")
                    return

                # Only now that required_rank_ids exists, build readable role names
                required_roles = [after.guild.get_role(rid) for rid in required_rank_ids if after.guild.get_role(rid)]
                required_role_names = ", ".join(r.name for r in required_roles)

                # 📨 DM Embed
                dm_embed = discord.Embed(
                    title=f"You have been stripped off of {role.name}",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                dm_embed.add_field(
                    name="**Reason:**",
                    value=f"You need to have either of **{required_role_names}** rank roles to have **{role.name}**\n", inline=False
                )
                dm_embed.add_field(
                    name="**Reason(dumb version):**",
                    value=f"You can't pick up **{role.name}** role if you're **{current_rank_role}**", inline=False
                )
                dm_embed.set_footer(text="Only 1 Rank Sire")

                try:
                    await after.send(embed=dm_embed)
                except discord.Forbidden:
                    print(f"❌ Couldn't DM {after.display_name}")

                # 📝 Log Embed
                log_embed = discord.Embed(
                    title="Blocked LFG Role Assignment",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                log_embed.set_author(name=str(after), icon_url=after.display_avatar.url)
                log_embed.add_field(name="**User:**", value=f"{after.mention}")
                log_embed.add_field(name="**Tried to add:**", value=f"<@&{role.id}>")
                log_embed.add_field(name="**Current Rank:**", value=f"{current_rank_role.mention if current_rank_role else 'None'}")
                log_embed.add_field(
                    name="**Missing one of:**",
                    value=f"{', '.join(f'<@&{rid}>' for rid in required_rank_ids)}"
                )

                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    await log_channel.send(embed=log_embed)

            break  # Only process the first relevant LFG role

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
