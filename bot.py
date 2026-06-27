import discord
from discord.ext import commands
import json
import random
import string
import datetime
import asyncio
import aiohttp
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

KEYS_FILE = 'keys.json'
VERIFIED_FILE = 'verified.json'
KEY_LENGTH = 16
COOLDOWN_HOURS = 24

def load_keys():
    if not os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, 'w') as f:
            json.dump({}, f)
        return {}
    with open(KEYS_FILE, 'r') as f:
        return json.load(f)

def save_keys(keys):
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=4)

def load_verified():
    if not os.path.exists(VERIFIED_FILE):
        with open(VERIFIED_FILE, 'w') as f:
            json.dump({}, f)
        return {}
    with open(VERIFIED_FILE, 'r') as f:
        return json.load(f)

def save_verified(verified):
    with open(VERIFIED_FILE, 'w') as f:
        json.dump(verified, f, indent=4)

def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=KEY_LENGTH))

def can_generate_key(user_id):
    verified = load_verified()
    if str(user_id) not in verified:
        return False, "You are not verified. Ask an admin to verify you."
    
    data = verified[str(user_id)]
    last_generate = datetime.datetime.fromisoformat(data['last_generate'])
    now = datetime.datetime.now()
    
    if (now - last_generate).total_seconds() < COOLDOWN_HOURS * 3600:
        remaining = COOLDOWN_HOURS * 3600 - (now - last_generate).total_seconds()
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return False, f"You are on cooldown. Remaining: {hours}h {minutes}m"
    
    return True, ""

def update_last_generate(user_id):
    verified = load_verified()
    if str(user_id) in verified:
        verified[str(user_id)]['last_generate'] = datetime.datetime.now().isoformat()
        save_verified(verified)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="Safe Hub Keys"
    ))

def is_admin():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)

async def send_private_key(user, key, expiry):
    try:
        embed = discord.Embed(
            title="Safe Hub Access Key",
            description="**IMPORTANT: Keep this key private. Do not share it with anyone.**",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Your Key",
            value=f"`{key}`",
            inline=False
        )
        embed.add_field(
            name="Valid For",
            value="30 days",
            inline=True
        )
        embed.add_field(
            name="Max Uses",
            value="1",
            inline=True
        )
        embed.add_field(
            name="Expires",
            value=expiry.strftime("%Y-%m-%d %H:%M:%S"),
            inline=False
        )
        embed.add_field(
            name="Website",
            value="https://dime-scripts.github.io/safehubserverside/",
            inline=False
        )
        embed.set_footer(text="Safe Hub Key System - Keep this key secure!")
        
        await user.send(embed=embed)
        return True
    except discord.Forbidden:
        return False

@bot.command(name='verify')
@is_admin()
async def verify_user(ctx, member: discord.Member = None):
    if member is None:
        await ctx.send("Please specify a user to verify. Usage: `!verify @user`")
        return
    
    verified = load_verified()
    user_id = str(member.id)
    
    if user_id in verified:
        await ctx.send(f"{member.mention} is already verified.")
        return
    
    verified[user_id] = {
        'username': str(member),
        'verified_at': datetime.datetime.now().isoformat(),
        'last_generate': datetime.datetime.now().isoformat()
    }
    save_verified(verified)
    
    embed = discord.Embed(
        title="User Verified",
        description=f"{member.mention} has been verified!",
        color=discord.Color.green()
    )
    embed.add_field(name="Verified By", value=str(ctx.author), inline=True)
    embed.add_field(name="User ID", value=member.id, inline=True)
    await ctx.send(embed=embed)
    
    try:
        await member.send("You have been verified in the Safe Hub key system. You can now use `!generatekey` to get your access key.")
    except discord.Forbidden:
        await ctx.send(f"Could not DM {member.mention}. Please ensure they have DMs enabled.")

@bot.command(name='unverify')
@is_admin()
async def unverify_user(ctx, member: discord.Member = None):
    if member is None:
        await ctx.send("Please specify a user to unverify. Usage: `!unverify @user`")
        return
    
    verified = load_verified()
    user_id = str(member.id)
    
    if user_id not in verified:
        await ctx.send(f"{member.mention} is not verified.")
        return
    
    del verified[user_id]
    save_verified(verified)
    
    embed = discord.Embed(
        title="User Unverified",
        description=f"{member.mention} has been unverified.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)
    
    try:
        await member.send("You have been unverified from the Safe Hub key system. Your access keys have been revoked.")
    except discord.Forbidden:
        pass

@bot.command(name='generatekey')
async def generate_key(ctx):
    user_id = str(ctx.author.id)
    
    can_generate, message = can_generate_key(user_id)
    if not can_generate:
        embed = discord.Embed(
            title="Cooldown Active",
            description=message,
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    keys = load_keys()
    
    key = generate_key()
    while key in keys:
        key = generate_key()
    
    expiry = datetime.datetime.now() + datetime.timedelta(days=30)
    
    keys[key] = {
        'created_by': str(ctx.author),
        'user_id': user_id,
        'created_at': datetime.datetime.now().isoformat(),
        'expires_at': expiry.isoformat(),
        'max_uses': 1,
        'uses': 0,
        'active': True,
        'duration_days': 30
    }
    
    save_keys(keys)
    update_last_generate(user_id)
    
    sent = await send_private_key(ctx.author, key, expiry)
    
    if sent:
        embed = discord.Embed(
            title="Key Generated Successfully",
            description="Your access key has been sent to your DMs. Please check your private messages.",
            color=discord.Color.green()
        )
        embed.add_field(name="Cooldown", value=f"You can generate another key in {COOLDOWN_HOURS} hours", inline=False)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="Key Generated",
            description="Could not send key via DM. Please enable DMs and try again, or contact an admin.",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="Your Key",
            value=f"`{key}`",
            inline=False
        )
        embed.add_field(name="Expires", value=expiry.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(
        title="Safe Hub Key Bot - Commands",
        description="Available commands for the Safe Hub key system",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="!verify @user",
        value="Verify a user (Admin only)",
        inline=False
    )
    embed.add_field(
        name="!unverify @user",
        value="Unverify a user (Admin only)",
        inline=False
    )
    embed.add_field(
        name="!generatekey",
        value=f"Generate a new access key (Verified users only, {COOLDOWN_HOURS}h cooldown)",
        inline=False
    )
    embed.add_field(
        name="!help",
        value="Show this help message",
        inline=False
    )
    
    embed.set_footer(text=f"Cooldown: {COOLDOWN_HOURS} hours per key generation")
    await ctx.send(embed=embed)

@bot.command(name='mykey')
async def my_key(ctx):
    keys = load_keys()
    user_id = str(ctx.author.id)
    
    user_keys = []
    for key, data in keys.items():
        if data.get('user_id') == user_id and data['active']:
            expiry = datetime.datetime.fromisoformat(data['expires_at'])
            if expiry > datetime.datetime.now():
                user_keys.append(key)
    
    if not user_keys:
        await ctx.send("You don't have any active keys. Use `!generatekey` to create one.")
        return
    
    try:
        for key in user_keys:
            await ctx.author.send(f"Your active key: `{key}`")
        await ctx.send("Your active keys have been sent to your DMs.")
    except discord.Forbidden:
        await ctx.send(f"Could not send keys via DM. Please enable DMs. Your keys: {', '.join([f'`{k}`' for k in user_keys])}")

@bot.command(name='listverified')
@is_admin()
async def list_verified(ctx):
    verified = load_verified()
    
    if not verified:
        await ctx.send("No verified users found.")
        return
    
    embed = discord.Embed(
        title="Verified Users",
        color=discord.Color.blue()
    )
    
    for user_id, data in verified.items():
        try:
            user = await bot.fetch_user(int(user_id))
            username = user.name
        except:
            username = data.get('username', 'Unknown')
        
        verified_at = datetime.datetime.fromisoformat(data['verified_at']).strftime("%Y-%m-%d")
        embed.add_field(
            name=username,
            value=f"ID: {user_id}\nVerified: {verified_at}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='revokekey')
@is_admin()
async def revoke_key_admin(ctx, key: str):
    keys = load_keys()
    
    if key not in keys:
        await ctx.send("Key not found.")
        return
    
    user_id = keys[key].get('user_id')
    keys[key]['active'] = False
    save_keys(keys)
    
    embed = discord.Embed(
        title="Key Revoked",
        description=f"Key `{key}` has been revoked.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)
    
    if user_id:
        try:
            user = await bot.fetch_user(int(user_id))
            await user.send(f"Your key `{key}` has been revoked by an administrator.")
        except:
            pass

@bot.command(name='revokeuserkeys')
@is_admin()
async def revoke_user_keys(ctx, member: discord.Member = None):
    if member is None:
        await ctx.send("Please specify a user. Usage: `!revokeuserkeys @user`")
        return
    
    keys = load_keys()
    user_id = str(member.id)
    revoked = 0
    
    for key, data in keys.items():
        if data.get('user_id') == user_id and data['active']:
            keys[key]['active'] = False
            revoked += 1
    
    if revoked > 0:
        save_keys(keys)
        embed = discord.Embed(
            title="Keys Revoked",
            description=f"Revoked {revoked} keys for {member.mention}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        
        try:
            await member.send(f"All your active keys have been revoked by an administrator.")
        except:
            pass
    else:
        await ctx.send(f"{member.mention} has no active keys.")

# Get Discord token from environment variable
discord_token = os.getenv('DISCORD_TOKEN')
if not discord_token:
    raise ValueError("DISCORD_TOKEN environment variable is not set. Please set it in Railway.")

bot.run(discord_token)

