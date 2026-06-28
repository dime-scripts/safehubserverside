import discord
from discord.ext import commands
import json
import random
import string
import datetime
import os
import aiohttp
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Railway backend URL
RAILWAY_API_URL = 'https://safehub-backend-production.up.railway.app'
KEY_LENGTH = 16
COOLDOWN_HOURS = 24

# Local file for verification only
VERIFIED_FILE = 'verified.json'

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = False  # <-- ADD THIS LINE to disable voice features


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
    user_id_str = str(user_id)
    
    if user_id_str not in verified:
        return False, "You are not verified. Ask an admin to verify you."
    
    data = verified[user_id_str]
    
    if 'last_generate' not in data:
        return True, ""
    
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
    user_id_str = str(user_id)
    if user_id_str in verified:
        verified[user_id_str]['last_generate'] = datetime.datetime.now().isoformat()
        save_verified(verified)

async def add_key_to_railway(key, user_id, username):
    """Send the generated key to Railway backend"""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                'key': key,
                'userId': str(user_id),
                'username': username,
                'maxUses': 1
            }
            async with session.post(f'{RAILWAY_API_URL}/api/addkey', json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('success', False)
                return False
    except Exception as e:
        print(f'Error adding key to Railway: {e}')
        return False

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

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, 
        name="Safe Hub Keys"
    ))

@bot.command()
@commands.has_permissions(administrator=True)
async def verify(ctx, member: discord.Member = None):
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
        'verified_at': datetime.datetime.now().isoformat()
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

@bot.command()
@commands.has_permissions(administrator=True)
async def unverify(ctx, member: discord.Member = None):
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

@bot.command()
async def generatekey(ctx):
    try:
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
        
        key = generate_key()
        expiry = datetime.datetime.now() + datetime.timedelta(days=30)
        
        # Add key to Railway backend
        success = await add_key_to_railway(key, user_id, str(ctx.author))
        
        if not success:
            await ctx.send("Failed to save key to backend. Please try again later.")
            return
        
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
                title="Key Generated - DM Failed",
                description=f"Could not send key via DM. Your key is: `{key}`",
                color=discord.Color.orange()
            )
            embed.add_field(name="Expires", value=expiry.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            await ctx.send(embed=embed)
            
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        print(f"Error in generatekey: {e}")

@bot.command()
async def help(ctx):
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
    embed.add_field(
        name="!mykey",
        value="Show your active keys",
        inline=False
    )
    
    embed.set_footer(text=f"Cooldown: {COOLDOWN_HOURS} hours per key generation")
    await ctx.send(embed=embed)

@bot.command()
async def mykey(ctx):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{RAILWAY_API_URL}/api/keys') as response:
                if response.status == 200:
                    data = await response.json()
                    user_id = str(ctx.author.id)
                    user_keys = []
                    
                    for key_data in data.get('keys', []):
                        if key_data.get('user_id') == user_id and key_data.get('active', False):
                            user_keys.append(key_data.get('key'))
                    
                    if not user_keys:
                        await ctx.send("You don't have any active keys. Use `!generatekey` to create one.")
                        return
                    
                    try:
                        for key in user_keys:
                            await ctx.author.send(f"Your active key: `{key}`")
                        await ctx.send("Your active keys have been sent to your DMs.")
                    except discord.Forbidden:
                        await ctx.send(f"Could not send keys via DM. Your keys: {', '.join([f'`{k}`' for k in user_keys])}")
                else:
                    await ctx.send("Could not fetch keys from backend.")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        print(f"Error in mykey: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def listverified(ctx):
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

@bot.command()
@commands.has_permissions(administrator=True)
async def revokekey(ctx, key: str):
    try:
        async with aiohttp.ClientSession() as session:
            payload = {'key': key}
            async with session.post(f'{RAILWAY_API_URL}/api/revokekey', json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('success'):
                        embed = discord.Embed(
                            title="Key Revoked",
                            description=f"Key `{key}` has been revoked.",
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"Failed to revoke key: {data.get('reason', 'Unknown error')}")
                else:
                    await ctx.send("Failed to connect to backend.")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        print(f"Error in revokekey: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def revokeuserkeys(ctx, member: discord.Member = None):
    if member is None:
        await ctx.send("Please specify a user. Usage: `!revokeuserkeys @user`")
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            payload = {'userId': str(member.id)}
            async with session.post(f'{RAILWAY_API_URL}/api/revokeuserkeys', json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('success'):
                        embed = discord.Embed(
                            title="Keys Revoked",
                            description=f"Revoked keys for {member.mention}",
                            color=discord.Color.red()
                        )
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"Failed to revoke keys: {data.get('reason', 'Unknown error')}")
                else:
                    await ctx.send("Failed to connect to backend.")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")
        print(f"Error in revokeuserkeys: {e}")

@bot.command()
async def test(ctx):
    await ctx.send("Bot is working! Use !generatekey to generate a key.")

discord_token = os.getenv('DISCORD_TOKEN')
if not discord_token:
    raise ValueError("DISCORD_TOKEN environment variable is not set. Please set it in Railway.")

bot.run(discord_token)
