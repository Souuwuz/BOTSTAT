# MORTEM HOUSE STAT DISCORD RPG BOT - ALL CODE FILES

-------------------------------------------------------------------
# FILE: main.py
-------------------------------------------------------------------
import asyncio
import logging
import os
import threading
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify
import pickle
from pathlib import Path

from bot import setup_bot
from keep_alive import keep_alive
from uptime import setup_uptime_helper

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default-secret-key")

@app.route('/')
def index():
    """Home page for the RPG bot dashboard."""
    return render_template('index.html', title="Mortem House Stat - RPG Bot Dashboard")

@app.route('/api/stats')
def stats():
    """API endpoint to get bot statistics."""
    try:
        # Load the database
        db_path = Path("rpg_database.pkl")
        if not db_path.exists():
            return jsonify({
                'users': 0,
                'items': 0,
                'commands_used': 0
            })
            
        with open(db_path, 'rb') as f:
            data = pickle.load(f)
            
        return jsonify({
            'users': len(data.get('users', {})),
            'items': sum(len(inventory) for inventory in data.get('inventories', {}).values()),
            'commands_used': len(data.get('cooldowns', {}))
        })
    except Exception as e:
        logger.error(f"Error loading stats: {e}")
        return jsonify({'error': 'Failed to load stats'}), 500

@app.route('/status')
def status():
    """Status endpoint for monitoring services."""
    return jsonify({
        'status': 'online',
        'bot': 'STATBOT',
        'version': '1.0.0'
    })

async def main():
    """
    Main entry point for the Discord RPG bot.
    """
    try:
        # Setup and connect the bot
        bot = await setup_bot()
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not bot_token:
            logger.error("No Discord bot token found in environment variables. Please set DISCORD_BOT_TOKEN.")
            return
        
        # Log successful connection
        logger.info("Starting Discord bot with token...")
        await bot.start(bot_token)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

if __name__ == "__main__":
    # Start the keep-alive web server in a separate thread
    keep_alive()
    
    # Setup the uptime helper for 24/7 operation
    setup_uptime_helper()
    
    # Run the Discord bot
    logger.info("Starting Discord RPG Bot - Mortem House Stat")
    asyncio.run(main())

-------------------------------------------------------------------
# FILE: bot.py
-------------------------------------------------------------------
import asyncio
import discord
import logging
import os
from discord.ext import commands

# Import cogs
from cogs.combat import Combat
from cogs.profile import Profile
from cogs.inventory import Inventory
from cogs.gacha import Gacha
from cogs.admin import Admin
from utils.db_manager import DatabaseManager

# Configure logging
logger = logging.getLogger(__name__)

async def setup_bot():
    """
    Set up and configure the Discord bot with all necessary cogs and settings.
    """
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    from config import DEFAULT_PREFIX
    bot = commands.Bot(command_prefix=DEFAULT_PREFIX, intents=intents)
    
    # Initialize database
    bot.db_manager = DatabaseManager()
    await bot.db_manager.initialize()
    
    # Store background tasks
    bot.background_tasks = []

    @bot.event
    async def on_ready():
        """
        Event handler for when the bot is ready and connected to Discord.
        """
        logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
        logger.info("------")
        
        # Start background tasks for HP and Energy regeneration
        bot.background_tasks.append(bot.loop.create_task(regenerate_stats(bot)))
        
        # Set the bot's activity status
        await bot.change_presence(activity=discord.Game(name="RPG Adventure | Statbot!help"))

    @bot.event
    async def on_command_error(ctx, error):
        """
        Global error handler for the bot.
        """
        if isinstance(error, commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            hours, minutes = divmod(minutes, 60)
            if int(hours) == 0 and int(minutes) == 0:
                await ctx.send(f"This command is on cooldown. Try again in {int(seconds)} seconds.")
            elif int(hours) == 0:
                await ctx.send(f"This command is on cooldown. Try again in {int(minutes)} minutes and {int(seconds)} seconds.")
            else:
                await ctx.send(f"This command is on cooldown. Try again in {int(hours)} hours, {int(minutes)} minutes and {int(seconds)} seconds.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: {error.param.name}")
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send("Command not found. Use Statbot!help to see available commands.")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have the required permissions to use this command.")
        else:
            logger.error(f"Command error: {error}")
            await ctx.send(f"An error occurred: {error}")

    # Add cogs to the bot
    await bot.add_cog(Combat(bot))
    await bot.add_cog(Profile(bot))
    await bot.add_cog(Inventory(bot))
    await bot.add_cog(Gacha(bot))
    await bot.add_cog(Admin(bot))
    
    return bot

async def regenerate_stats(bot):
    """
    Background task for regenerating HP and Energy for all users.
    """
    from config import HP_REGEN_RATE, HP_REGEN_INTERVAL, ENERGY_REGEN_RATE, ENERGY_REGEN_INTERVAL, MAX_HP, MAX_ENERGY
    
    logger.info("Starting stats regeneration task")
    
    hp_timer = 0
    energy_timer = 0
    
    while not bot.is_closed():
        await asyncio.sleep(60)  # Check every minute
        
        # Increment timers
        hp_timer += 60
        energy_timer += 60
        
        # HP regeneration cycle
        if hp_timer >= HP_REGEN_INTERVAL:
            hp_timer = 0
            users = await bot.db_manager.get_all_users()
            for user_id, user_data in users.items():
                if user_data['hp'] < MAX_HP:
                    new_hp = min(user_data['hp'] + HP_REGEN_RATE, MAX_HP)
                    await bot.db_manager.update_user_stat(user_id, 'hp', new_hp)
            logger.debug(f"HP regeneration cycle completed for {len(users)} users")
        
        # Energy regeneration cycle
        if energy_timer >= ENERGY_REGEN_INTERVAL:
            energy_timer = 0
            users = await bot.db_manager.get_all_users()
            for user_id, user_data in users.items():
                if user_data['energy'] < MAX_ENERGY:
                    new_energy = min(user_data['energy'] + ENERGY_REGEN_RATE, MAX_ENERGY)
                    await bot.db_manager.update_user_stat(user_id, 'energy', new_energy)
            logger.debug(f"Energy regeneration cycle completed for {len(users)} users")

-------------------------------------------------------------------
# FILE: config.py
-------------------------------------------------------------------
"""
Configuration settings for the Discord RPG bot.
"""

# General settings
DEFAULT_PREFIX = "Statbot!"
MAX_HP = 100
MAX_ENERGY = 100
HP_REGEN_RATE = 2  # HP points per cycle
HP_REGEN_INTERVAL = 5 * 60  # 5 minutes in seconds
ENERGY_REGEN_RATE = 2  # Energy points per cycle
ENERGY_REGEN_INTERVAL = 3 * 60  # 3 minutes in seconds

# Combat settings
ATTACK_ENERGY_COST = 10
DEFENSE_ENERGY_COST = 5

# Level settings
LEVEL_THRESHOLDS = {
    1: 0,      # Default level
    5: 500,    # 500 EXP required for level 5
    10: 1000,  # 1,000 EXP required for level 10
    15: 1500,  # 1,500 EXP required for level 15
    100: 10000 # 10,000 EXP required for level 100
}

# Attack probabilities by level
ATTACK_PROBABILITIES = {
    1: {
        (0, 5): 0.20,   # 20% chance for 0-5 damage
        (6, 10): 0.18,  # 18% chance for 6-10 damage
        (11, 15): 0.15, # 15% chance for 11-15 damage
        (16, 20): 0.10  # 10% chance for 16-20 damage
    },
    5: {
        (0, 5): 0.17,
        (6, 10): 0.20,
        (11, 15): 0.15,
        (16, 20): 0.10
    },
    10: {
        (0, 5): 0.05,
        (6, 10): 0.10,
        (11, 15): 0.17,
        (16, 20): 0.19
    },
    15: {
        (0, 5): 0.05,
        (6, 10): 0.10,
        (11, 15): 0.18,
        (16, 20): 0.20
    },
    100: {
        "fixed_damage": 30  # Fixed 30 damage at level 100
    }
}

# Defense probabilities by level
DEFENSE_PROBABILITIES = {
    1: {
        (0, 5): 0.20,   # 20% chance for 0-5 block
        (6, 10): 0.15,  # 15% chance for 6-10 block
        (11, 15): 0.10  # 10% chance for 11-15 block
    },
    5: {
        (0, 5): 0.15,
        (6, 10): 0.20,
        (11, 15): 0.10
    },
    10: {
        (0, 5): 0.10,
        (6, 10): 0.15,
        (11, 15): 0.20
    },
    15: {
        (0, 5): 0.10,
        (6, 10): 0.15,
        (11, 15): 0.20
    },
    100: {
        "fixed_block": 80  # Fixed 80 block at level 100
    }
}

# EXP gain probabilities
EXERCISE_EXP_PROBABILITIES = {
    (1, 10): 0.30,   # 30% chance for 1-10 EXP
    (11, 20): 0.29,  # 29% chance for 11-20 EXP
    (21, 30): 0.15   # 15% chance for 21-30 EXP
}

# Item settings
ITEMS = {
    "energy_drink": {
        "name": "Energy Drink",
        "description": "Restores 40 Energy points",
        "effect": {"energy": 40},
        "rarity": "common",
        "emoji": "🧃"
    },
    "first_aid_kit": {
        "name": "First Aid Kit",
        "description": "Restores 30 HP points",
        "effect": {"hp": 30},
        "rarity": "common",
        "emoji": "🩹"
    }
}

# Gacha settings
GACHA_COIN_COST = 10
SEARCHING_COOLDOWN = 2 * 60 * 60  # 2 hours in seconds
SEARCHING_PROBABILITIES = {
    "success": 0.80,  # 80% chance to get coins
    "coin_range": (5, 10)  # 5-10 coins when successful
}

# Exercise cooldown (24 hours in seconds)
EXERCISE_COOLDOWN = 24 * 60 * 60

-------------------------------------------------------------------
# FILE: keep_alive.py
-------------------------------------------------------------------
import logging
import threading
import time
from flask import Flask, jsonify
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app for keep-alive service
app = Flask(__name__)

@app.route('/')
def home():
    """Simple endpoint for Replit to ping and keep the repl alive."""
    return "Bot is alive!"

@app.route('/health')
def health():
    """Health check endpoint for monitoring."""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time()
    })

def ping_self():
    """Ping the application to keep it alive."""
    while True:
        try:
            response = requests.get("http://0.0.0.0:8080/health", timeout=10)
            logger.debug(f"Self-ping returned status code: {response.status_code}")
        except Exception as e:
            logger.error(f"Error during self-ping: {e}")
        
        # Sleep for an hour
        time.sleep(60 * 60)

def run():
    """Run the Flask app in a separate thread."""
    logger.info("Keep-alive service started")
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """Start threads to run the Flask app and ping service."""
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
    
    # Also start a thread to ping ourselves
    ping_thread = threading.Thread(target=ping_self)
    ping_thread.daemon = True
    ping_thread.start()

-------------------------------------------------------------------
# FILE: uptime.py
-------------------------------------------------------------------
"""
Uptime helper for Discord bot.
This script helps keep the bot running 24/7 by using external uptime services.
"""
import logging
import os
import time
import requests
from threading import Thread

# Configure logging
logger = logging.getLogger(__name__)

# How often to ping external services (in seconds)
PING_INTERVAL = 4 * 60 * 60  # 4 hours

def get_replit_url():
    """Get the public URL for this repl."""
    # For local development/testing, use the local IP
    return "http://0.0.0.0:8080"

def register_with_uptime_services():
    """
    Register the bot with free uptime monitoring services.
    You'll need to manually sign up for these services and add your URL.
    """
    replit_url = get_replit_url()
    logger.info(f"Replit URL for uptime services: {replit_url}")
    logger.info("To ensure 24/7 uptime:")
    logger.info("1. Sign up at UptimeRobot.com (free)")
    logger.info("2. Add a new HTTP(s) monitor with your repl URL:")
    logger.info(f"   {replit_url}")
    logger.info("3. Set checking interval to 5 minutes")

def setup_uptime_helper():
    """Set up the uptime helper."""
    register_with_uptime_services()
    
    # Even if not using uptime services, we can ping ourselves
    def self_ping_background():
        # Give the Flask server time to start up
        time.sleep(10)
        
        replit_url = get_replit_url()
        ping_url = f"{replit_url}/health"
        
        while True:
            try:
                logger.info(f"Self-pinging: {ping_url}")
                response = requests.get(ping_url, timeout=10)
                if response.status_code == 200:
                    logger.info("Self-ping successful")
                else:
                    logger.warning(f"Self-ping returned status code: {response.status_code}")
            except Exception as e:
                logger.error(f"Error during self-ping: {e}")
                logger.info("Will try again later...")
            
            # Sleep before next ping
            time.sleep(PING_INTERVAL)
    
    # Start self-ping thread
    ping_thread = Thread(target=self_ping_background)
    ping_thread.daemon = True
    ping_thread.start()
    
    logger.info("Uptime helper started!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_uptime_helper()

-------------------------------------------------------------------
# FILE: utils/db_manager.py
-------------------------------------------------------------------
import json
import logging
import os
import pickle
from pathlib import Path

from config import MAX_HP, MAX_ENERGY

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Manages persistence of user data and game stats.
    Uses pickle for data storage between sessions.
    """
    
    def __init__(self):
        """Initialize the database manager."""
        self.db_path = Path("rpg_database.pkl")
        self.data = {
            "users": {},
            "cooldowns": {},
            "inventories": {}
        }
    
    async def initialize(self):
        """Initialize the database and load existing data if available."""
        try:
            if self.db_path.exists():
                with open(self.db_path, 'rb') as f:
                    self.data = pickle.load(f)
                logger.info(f"Loaded database with {len(self.data['users'])} users")
            else:
                logger.info("No existing database found. Creating new database.")
                await self.save_data()
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            # Ensure we have a valid database even if loading fails
            await self.save_data()
    
    async def save_data(self):
        """Save the current data to disk."""
        try:
            with open(self.db_path, 'wb') as f:
                pickle.dump(self.data, f)
            logger.debug("Database saved successfully")
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    async def get_user(self, user_id):
        """
        Get a user's data from the database.
        If the user doesn't exist, create a new entry.
        """
        user_id = str(user_id)  # Ensure user_id is a string
        
        if user_id not in self.data["users"]:
            # Create new user with default values
            self.data["users"][user_id] = {
                "hp": MAX_HP,
                "energy": MAX_ENERGY,
                "exp": 0,
                "level": 1
            }
            
            # Create empty inventory for the user
            self.data["inventories"][user_id] = {}
            
            # Create cooldowns entry for the user
            self.data["cooldowns"][user_id] = {}
            
            await self.save_data()
            
        return self.data["users"][user_id]
    
    async def get_all_users(self):
        """Get all users' data."""
        return self.data["users"]
    
    async def update_user_stat(self, user_id, stat, value):
        """Update a specific stat for a user."""
        user_id = str(user_id)
        
        # Get the user (or create if doesn't exist)
        user = await self.get_user(user_id)
        
        # Update the stat
        user[stat] = value
        await self.save_data()
        
        return user
    
    async def get_inventory(self, user_id):
        """Get a user's inventory."""
        user_id = str(user_id)
        
        # Ensure user exists
        await self.get_user(user_id)
        
        if user_id not in self.data["inventories"]:
            self.data["inventories"][user_id] = {}
            await self.save_data()
        
        return self.data["inventories"][user_id]
    
    async def add_item_to_inventory(self, user_id, item_id, quantity=1):
        """Add an item to a user's inventory."""
        user_id = str(user_id)
        inventory = await self.get_inventory(user_id)
        
        if item_id in inventory:
            inventory[item_id] += quantity
        else:
            inventory[item_id] = quantity
        
        await self.save_data()
        return inventory
    
    async def remove_item_from_inventory(self, user_id, item_id, quantity=1):
        """Remove an item from a user's inventory."""
        user_id = str(user_id)
        inventory = await self.get_inventory(user_id)
        
        if item_id not in inventory or inventory[item_id] < quantity:
            return False
        
        inventory[item_id] -= quantity
        
        if inventory[item_id] <= 0:
            del inventory[item_id]
        
        await self.save_data()
        return True
    
    async def set_cooldown(self, user_id, command, timestamp):
        """Set a cooldown for a specific command for a user."""
        user_id = str(user_id)
        
        # Ensure user exists
        await self.get_user(user_id)
        
        if user_id not in self.data["cooldowns"]:
            self.data["cooldowns"][user_id] = {}
        
        self.data["cooldowns"][user_id][command] = timestamp
        await self.save_data()
    
    async def get_cooldown(self, user_id, command):
        """Get the cooldown timestamp for a specific command for a user."""
        user_id = str(user_id)
        
        # Ensure user exists
        await self.get_user(user_id)
        
        if user_id not in self.data["cooldowns"] or command not in self.data["cooldowns"][user_id]:
            return 0
        
        return self.data["cooldowns"][user_id][command]
    
    async def add_coins(self, user_id, amount):
        """Add gacha coins to a user's account."""
        user_id = str(user_id)
        user = await self.get_user(user_id)
        
        if "coins" not in user:
            user["coins"] = 0
        
        user["coins"] += amount
        await self.save_data()
        return user["coins"]
    
    async def remove_coins(self, user_id, amount):
        """Remove gacha coins from a user's account."""
        user_id = str(user_id)
        user = await self.get_user(user_id)
        
        if "coins" not in user:
            return False
        
        if user["coins"] < amount:
            return False
        
        user["coins"] -= amount
        await self.save_data()
        return user["coins"]

-------------------------------------------------------------------
# FILE: utils/helpers.py
-------------------------------------------------------------------
import random
import time
from typing import Tuple

from config import LEVEL_THRESHOLDS, EXERCISE_EXP_PROBABILITIES


def get_current_level(exp: int) -> int:
    """
    Calculate the current level based on experience points.
    
    Args:
        exp: The current experience points
        
    Returns:
        int: The current level
    """
    current_level = 1
    
    for level, threshold in sorted(LEVEL_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
        if exp >= threshold:
            current_level = level
            break
    
    return current_level


def calculate_damage(attacker_level: int) -> int:
    """
    Calculate the damage based on attacker's level.
    
    Args:
        attacker_level: The attacker's level
        
    Returns:
        int: The calculated damage
    """
    from config import ATTACK_PROBABILITIES
    
    # Find the closest level in the configuration
    available_levels = sorted(ATTACK_PROBABILITIES.keys())
    level_to_use = 1  # Default to level 1
    
    for level in available_levels:
        if attacker_level >= level:
            level_to_use = level
        else:
            break
    
    # Check if the level has fixed damage (like level 100)
    if "fixed_damage" in ATTACK_PROBABILITIES[level_to_use]:
        return ATTACK_PROBABILITIES[level_to_use]["fixed_damage"]
    
    # Otherwise, calculate random damage based on probabilities
    damage_ranges = list(ATTACK_PROBABILITIES[level_to_use].keys())
    probabilities = list(ATTACK_PROBABILITIES[level_to_use].values())
    
    # Normalize probabilities (might not sum to 1.0)
    total_prob = sum(probabilities)
    if total_prob < 1.0:
        # Add a "miss" chance if probabilities don't sum to 1
        damage_ranges.append((0, 0))  # 0 damage range for miss
        probabilities.append(1.0 - total_prob)
    
    # Select a damage range based on probabilities
    selected_range = random.choices(damage_ranges, weights=probabilities, k=1)[0]
    
    # Return a random value within the selected range
    return random.randint(selected_range[0], selected_range[1])


def calculate_defense(defender_level: int) -> int:
    """
    Calculate the defense based on defender's level.
    
    Args:
        defender_level: The defender's level
        
    Returns:
        int: The calculated defense
    """
    from config import DEFENSE_PROBABILITIES
    
    # Find the closest level in the configuration
    available_levels = sorted(DEFENSE_PROBABILITIES.keys())
    level_to_use = 1  # Default to level 1
    
    for level in available_levels:
        if defender_level >= level:
            level_to_use = level
        else:
            break
    
    # Check if the level has fixed block (like level 100)
    if "fixed_block" in DEFENSE_PROBABILITIES[level_to_use]:
        return DEFENSE_PROBABILITIES[level_to_use]["fixed_block"]
    
    # Otherwise, calculate random defense based on probabilities
    defense_ranges = list(DEFENSE_PROBABILITIES[level_to_use].keys())
    probabilities = list(DEFENSE_PROBABILITIES[level_to_use].values())
    
    # Normalize probabilities (might not sum to 1.0)
    total_prob = sum(probabilities)
    if total_prob < 1.0:
        # Add a "no block" chance if probabilities don't sum to 1
        defense_ranges.append((0, 0))  # 0 defense range for no block
        probabilities.append(1.0 - total_prob)
    
    # Select a defense range based on probabilities
    selected_range = random.choices(defense_ranges, weights=probabilities, k=1)[0]
    
    # Return a random value within the selected range
    return random.randint(selected_range[0], selected_range[1])


def calculate_exp_gain() -> int:
    """
    Calculate the EXP gain from exercise command.
    
    Returns:
        int: The calculated EXP gain
    """
    # Get ranges and probabilities from config
    exp_ranges = list(EXERCISE_EXP_PROBABILITIES.keys())
    probabilities = list(EXERCISE_EXP_PROBABILITIES.values())
    
    # Normalize probabilities
    total_prob = sum(probabilities)
    if total_prob < 1.0:
        # Add a minimal EXP range if probabilities don't sum to 1
        exp_ranges.append((1, 1))  # Minimum 1 EXP
        probabilities.append(1.0 - total_prob)
    
    # Select an EXP range based on probabilities
    selected_range = random.choices(exp_ranges, weights=probabilities, k=1)[0]
    
    # Return a random value within the selected range
    return random.randint(selected_range[0], selected_range[1])


def is_on_cooldown(last_used_time: int, cooldown_seconds: int) -> Tuple[bool, int]:
    """
    Check if a command is on cooldown.
    
    Args:
        last_used_time: The timestamp when the command was last used
        cooldown_seconds: The cooldown period in seconds
        
    Returns:
        Tuple[bool, int]: (is_on_cooldown, remaining_seconds)
    """
    current_time = int(time.time())
    elapsed_time = current_time - last_used_time
    
    if elapsed_time < cooldown_seconds:
        remaining_seconds = cooldown_seconds - elapsed_time
        return True, remaining_seconds
    
    return False, 0

-------------------------------------------------------------------
# FILE: utils/embeds.py
-------------------------------------------------------------------
import discord
from config import MAX_HP, MAX_ENERGY

def create_profile_embed(user, user_data):
    """
    Create an embed for displaying a user's profile.
    
    Args:
        user: The discord.User or discord.Member object
        user_data: The user's data from the database
    
    Returns:
        discord.Embed: The formatted profile embed
    """
    # Get user stats
    hp = user_data['hp']
    energy = user_data['energy']
    exp = user_data['exp']
    level = user_data['level']
    coins = user_data.get('coins', 0)
    
    # Create the embed
    embed = discord.Embed(
        title=f"{user.display_name}'s Profile",
        description="Character statistics and progression",
        color=discord.Color.blue()
    )
    
    # Add user avatar if available
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
    
    # Add HP stat with progress bar
    hp_percent = (hp / MAX_HP) * 100
    hp_bar = create_progress_bar(hp, MAX_HP)
    embed.add_field(
        name=f"🤍 HP: {hp}/{MAX_HP} ({hp_percent:.1f}%)",
        value=hp_bar,
        inline=False
    )
    
    # Add Energy stat with progress bar
    energy_percent = (energy / MAX_ENERGY) * 100
    energy_bar = create_progress_bar(energy, MAX_ENERGY)
    embed.add_field(
        name=f"⚡️พลังงาน: {energy}/{MAX_ENERGY} ({energy_percent:.1f}%)",
        value=energy_bar,
        inline=False
    )
    
    # Add level and EXP
    embed.add_field(
        name=f"Level {level}",
        value=f"EXP: {exp}",
        inline=True
    )
    
    # Add coins
    embed.add_field(
        name="Gacha Coins",
        value=f"🪙 {coins}",
        inline=True
    )
    
    # Add footer
    embed.set_footer(text="Use Statbot!help to see available commands")
    
    return embed

def create_attack_embed(attacker, defender, damage, defense, energy_cost, attacker_energy, defender_hp):
    """Create an embed for displaying attack results."""
    # Calculate the final damage after defense
    final_damage = max(0, damage - defense)
    
    # Create the embed
    embed = discord.Embed(
        title="⚔️ Attack Results",
        description=f"{attacker.display_name} attacked {defender.display_name}!",
        color=discord.Color.red()
    )
    
    # Attack details
    embed.add_field(
        name="Attack Details",
        value=f"Damage Roll: **{damage}**\nDefense Roll: **{defense}**\nFinal Damage: **{final_damage}**",
        inline=False
    )
    
    # Status after attack
    embed.add_field(
        name="Status",
        value=f"{attacker.display_name}'s Energy: {attacker_energy}/{MAX_ENERGY} (-{energy_cost})\n"
              f"{defender.display_name}'s HP: {defender_hp}/{MAX_HP} (-{final_damage})",
        inline=False
    )
    
    # Add user avatars if available
    if attacker.avatar:
        embed.set_thumbnail(url=attacker.avatar.url)
    
    return embed

def create_inventory_embed(user, inventory, items_data):
    """Create an embed for displaying a user's inventory."""
    embed = discord.Embed(
        title=f"{user.display_name}'s Inventory",
        description="Items that can be used with Statbot!use [item_name]",
        color=discord.Color.green()
    )
    
    if not inventory:
        embed.add_field(
            name="Empty Inventory",
            value="You don't have any items yet. Try using Statbot!searching to find gacha coins, "
                  "then use Statbot!gacha to roll for items.",
            inline=False
        )
    else:
        for item_id, quantity in inventory.items():
            if item_id in items_data:
                item = items_data[item_id]
                embed.add_field(
                    name=f"{item['emoji']} {item['name']} x{quantity}",
                    value=f"{item['description']}",
                    inline=True
                )
    
    # Add user avatar if available
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
    
    embed.set_footer(text="Use Statbot!use [item_name] to use an item")
    
    return embed

def create_gacha_embed(user, item, cost):
    """Create an embed for displaying gacha results."""
    embed = discord.Embed(
        title="🎰 Gacha Results",
        description=f"{user.display_name} spent {cost} coins on the gacha machine!",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name=f"You got: {item['emoji']} {item['name']}",
        value=f"{item['description']}",
        inline=False
    )
    
    # Add user avatar if available
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
    
    embed.set_footer(text="Item has been added to your inventory")
    
    return embed

def create_searching_embed(user, result, coins=None):
    """Create an embed for displaying searching results."""
    embed = discord.Embed(
        title="🔍 Searching Results",
        description=f"{user.display_name} went searching for gacha coins!",
        color=discord.Color.teal()
    )
    
    if result:
        embed.add_field(
            name="Success!",
            value=f"You found {coins} gacha coins! 🪙",
            inline=False
        )
    else:
        embed.add_field(
            name="No luck this time...",
            value="You didn't find any gacha coins. Try again later!",
            inline=False
        )
    
    # Add user avatar if available
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
    
    embed.set_footer(text="Use Statbot!gacha to roll the gacha machine")
    
    return embed

def create_exercise_embed(user, exp_gained, new_exp, level, level_up=False):
    """Create an embed for displaying exercise results."""
    embed = discord.Embed(
        title="💪 Exercise Results",
        description=f"{user.display_name} completed their daily exercise!",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="Experience Gained",
        value=f"+{exp_gained} EXP",
        inline=False
    )
    
    if level_up:
        embed.add_field(
            name="Level Up!",
            value=f"You are now level {level}! 🎉",
            inline=False
        )
    else:
        embed.add_field(
            name="Current Progress",
            value=f"Level: {level}\nTotal EXP: {new_exp}",
            inline=False
        )
    
    # Add user avatar if available
    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)
    
    embed.set_footer(text="Exercise can be done once per day")
    
    return embed

def create_progress_bar(current, maximum, length=10, filled_char="█", empty_char="░"):
    """Create a text-based progress bar."""
    # Calculate how many blocks should be filled
    progress = min(maximum, max(0, current))
    filled_length = int(length * progress / maximum)
    
    # Create the bar
    bar = filled_char * filled_length + empty_char * (length - filled_length)
    
    return bar

-------------------------------------------------------------------
# FILE: cogs/admin.py
-------------------------------------------------------------------
import discord
import logging
from discord.ext import commands

from config import MAX_HP, MAX_ENERGY

logger = logging.getLogger(__name__)

class Admin(commands.Cog):
    """
    Admin commands for the RPG bot.
    Special commands that can only be used by authorized roles.
    """
    
    def __init__(self, bot):
        self.bot = bot
        
        # List to store authorized role IDs
        # These would normally be stored in a configuration file or database
        self.authorized_roles = []
        
        # Special role ID for healing command
        self.healing_role_id = 1356952258444525750
        
        # List to store moderator role IDs for EXP grant
        self.moderator_roles = []
    
    def cog_check(self, ctx):
        """
        Check that runs before any command in this cog.
        Verifies the user has an authorized role.
        """
        # Always allow bot owner
        if ctx.author.id == self.bot.owner_id:
            return True
            
        # Check for authorized roles
        if ctx.guild:
            user_roles = [role.id for role in ctx.author.roles]
            return any(role_id in self.authorized_roles for role_id in user_roles)
        
        return False
    
    async def heal_check(self, ctx):
        """Special check for heal command."""
        # Always allow bot owner
        if ctx.author.id == self.bot.owner_id:
            return True
            
        # Check for healing role
        if ctx.guild:
            user_roles = [role.id for role in ctx.author.roles]
            return self.healing_role_id in user_roles
        
        return False
    
    @commands.command(name="heal")
    async def heal(self, ctx, user: discord.Member = None):
        """
        Fully restore HP and Energy for a user.
        Only available to the healing role (ID: 1356952258444525750).
        
        Usage: Statbot!heal or Statbot!heal @username
        """
        if not await self.heal_check(ctx):
            await ctx.send("You don't have permission to use this command. It's restricted to the Healer role only.")
            return
            
        # If no user specified, use the command author
        if user is None:
            user = ctx.author
        
        # Get user data
        user_data = await self.bot.db_manager.get_user(user.id)
        
        # Restore HP and Energy
        user_data['hp'] = MAX_HP
        user_data['energy'] = MAX_ENERGY
        
        # Update in database
        await self.bot.db_manager.update_user_stat(user.id, 'hp', MAX_HP)
        await self.bot.db_manager.update_user_stat(user.id, 'energy', MAX_ENERGY)
        
        await ctx.send(f"✨ {user.mention}'s HP and Energy have been fully restored!")
    
    async def moderator_check(self, ctx):
        """Check if user has a moderator role."""
        # Always allow bot owner
        if ctx.author.id == self.bot.owner_id:
            return True
            
        # Check for moderator roles
        if ctx.guild:
            user_roles = [role.id for role in ctx.author.roles]
            return any(role_id in self.moderator_roles for role_id in user_roles) or any(role.permissions.administrator or role.permissions.manage_guild for role in ctx.author.roles)
        
        return False
    
    @commands.command(name="grantexp")
    async def grant_exp(self, ctx, user: discord.Member, amount: int):
        """
        Grant experience points to a user.
        Only available to moderator roles and above.
        Max 10,000 EXP per grant.
        
        Usage: Statbot!grantexp @username <amount>
        """
        if not await self.moderator_check(ctx):
            await ctx.send("You don't have permission to use this command. It's restricted to moderator roles only.")
            return
            
        # Limit amount to 10,000
        amount = min(amount, 10000)
        
        if amount <= 0:
            await ctx.send("The EXP amount must be positive.")
            return
        
        # Get user data
        user_data = await self.bot.db_manager.get_user(user.id)
        
        # Get current level before adding EXP
        from utils.helpers import get_current_level
        current_level = get_current_level(user_data['exp'])
        
        # Add EXP
        user_data['exp'] += amount
        await self.bot.db_manager.update_user_stat(user.id, 'exp', user_data['exp'])
        
        # Calculate new level
        new_level = get_current_level(user_data['exp'])
        
        # Check if user leveled up
        level_up = new_level > current_level
        
        if level_up:
            # Update level in the database
            await self.bot.db_manager.update_user_stat(user.id, 'level', new_level)
            await ctx.send(f"Granted {amount} EXP to {user.mention}. They leveled up to Level {new_level}! 🎉")
        else:
            await ctx.send(f"Granted {amount} EXP to {user.mention}. Current level: {new_level}")
    
    @commands.command(name="grantrole")
    @commands.is_owner()
    async def grant_role(self, ctx, role: discord.Role):
        """
        Add a role to the list of authorized roles.
        Only available to the bot owner.
        
        Usage: Statbot!grantrole @role
        """
        if role.id in self.authorized_roles:
            await ctx.send(f"The role {role.name} is already authorized.")
            return
        
        self.authorized_roles.append(role.id)
        await ctx.send(f"The role {role.name} has been added to the authorized roles list.")
    
    @commands.command(name="grantmodrole")
    @commands.is_owner()
    async def grant_mod_role(self, ctx, role: discord.Role):
        """
        Add a role to the list of moderator roles.
        Only available to the bot owner.
        
        Usage: Statbot!grantmodrole @role
        """
        if role.id in self.moderator_roles:
            await ctx.send(f"The role {role.name} is already a moderator role.")
            return
        
        self.moderator_roles.append(role.id)
        await ctx.send(f"The role {role.name} has been added to the moderator roles list.")
    
    @commands.command(name="revokerole")
    @commands.is_owner()
    async def revoke_role(self, ctx, role: discord.Role):
        """
        Remove a role from the list of authorized roles.
        Only available to the bot owner.
        
        Usage: Statbot!revokerole @role
        """
        if role.id not in self.authorized_roles:
            await ctx.send(f"The role {role.name} is not an authorized role.")
            return
        
        self.authorized_roles.remove(role.id)
        await ctx.send(f"The role {role.name} has been removed from the authorized roles list.")
    
    @commands.command(name="revokemodrole")
    @commands.is_owner()
    async def revoke_mod_role(self, ctx, role: discord.Role):
        """
        Remove a role from the list of moderator roles.
        Only available to the bot owner.
        
        Usage: Statbot!revokemodrole @role
        """
        if role.id not in self.moderator_roles:
            await ctx.send(f"The role {role.name} is not a moderator role.")
            return
        
        self.moderator_roles.remove(role.id)
        await ctx.send(f"The role {role.name} has been removed from the moderator roles list.")
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors."""
        if isinstance(error, commands.CheckFailure):
            if ctx.command.cog_name == self.__class__.__name__:
                await ctx.send("You don't have permission to use this command. It's restricted to authorized roles only.")

-------------------------------------------------------------------
# FILE: cogs/combat.py
-------------------------------------------------------------------
import discord
import logging
import random
from discord.ext import commands

from config import MAX_HP, MAX_ENERGY, ATTACK_ENERGY_COST, DEFENSE_ENERGY_COST
from utils.embeds import create_attack_embed
from utils.helpers import calculate_damage, calculate_defense

logger = logging.getLogger(__name__)

class Combat(commands.Cog):
    """
    Combat system for the RPG bot.
    Handles attack commands and defense mechanics.
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="attack")
    async def attack(self, ctx, target: discord.Member = None):
        """
        Attack another user to deal damage.
        
        Usage: Statbot!attack @username
        """
        # Check if a target was specified
        if target is None:
            await ctx.send("You need to specify a user to attack. Usage: `Statbot!attack @username`")
            return
        
        # Check if user is trying to attack themselves
        if target.id == ctx.author.id:
            await ctx.send("You can't attack yourself!")
            return
        
        # Check if user is trying to attack the bot
        if target.id == self.bot.user.id:
            await ctx.send("You can't attack me! I'm the game master.")
            return
        
        # Get user data for attacker and target
        attacker_data = await self.bot.db_manager.get_user(ctx.author.id)
        defender_data = await self.bot.db_manager.get_user(target.id)
        
        # Check if attacker has enough energy
        if attacker_data['energy'] < ATTACK_ENERGY_COST:
            await ctx.send(f"You don't have enough energy to attack! You need {ATTACK_ENERGY_COST} Energy.")
            return
        
        # Calculate damage based on attacker's level
        damage = calculate_damage(attacker_data['level'])
        
        # Calculate defense if defender has enough energy
        defense = 0
        if defender_data['energy'] >= DEFENSE_ENERGY_COST:
            defense = calculate_defense(defender_data['level'])
            # Deduct energy from defender for defense
            defender_data['energy'] -= DEFENSE_ENERGY_COST
            await self.bot.db_manager.update_user_stat(target.id, 'energy', defender_data['energy'])
        
        # Calculate final damage
        final_damage = max(0, damage - defense)
        
        # Update attacker's energy
        attacker_data['energy'] -= ATTACK_ENERGY_COST
        await self.bot.db_manager.update_user_stat(ctx.author.id, 'energy', attacker_data['energy'])
        
        # Update defender's HP
        defender_data['hp'] = max(0, defender_data['hp'] - final_damage)
        await self.bot.db_manager.update_user_stat(target.id, 'hp', defender_data['hp'])
        
        # Create and send the attack embed
        embed = create_attack_embed(
            ctx.author, 
            target, 
            damage, 
            defense, 
            ATTACK_ENERGY_COST,
            attacker_data['energy'],
            defender_data['hp']
        )
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors."""
        if isinstance(error, commands.MemberNotFound):
            if ctx.command.name == 'attack':
                await ctx.send("I couldn't find that user. Make sure you're mentioning a valid user.")

-------------------------------------------------------------------
# FILE: cogs/gacha.py
-------------------------------------------------------------------
import discord
import logging
import random
import time
from discord.ext import commands

from config import ITEMS, GACHA_COIN_COST, SEARCHING_COOLDOWN, SEARCHING_PROBABILITIES
from utils.embeds import create_gacha_embed, create_searching_embed
from utils.helpers import is_on_cooldown

logger = logging.getLogger(__name__)

class Gacha(commands.Cog):
    """
    Gacha system for the RPG bot.
    Handles gacha rolls and searching for coins.
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="gacha")
    async def gacha(self, ctx):
        """
        Roll the gacha machine to get items.
        Costs 10 gacha coins per roll.
        
        Usage: Statbot!gacha
        """
        # Get user data
        user_data = await self.bot.db_manager.get_user(ctx.author.id)
        
        # Check if user has enough coins
        if 'coins' not in user_data or user_data['coins'] < GACHA_COIN_COST:
            await ctx.send(f"You don't have enough gacha coins! You need {GACHA_COIN_COST} coins to roll.")
            return
        
        # Deduct coins
        user_data['coins'] -= GACHA_COIN_COST
        await self.bot.db_manager.update_user_stat(ctx.author.id, 'coins', user_data['coins'])
        
        # Select a random item from the available items
        item_id = random.choice(list(ITEMS.keys()))
        item = ITEMS[item_id]
        
        # Add item to inventory
        await self.bot.db_manager.add_item_to_inventory(ctx.author.id, item_id)
        
        # Create and send gacha embed
        embed = create_gacha_embed(ctx.author, item, GACHA_COIN_COST)
        await ctx.send(embed=embed)
    
    @commands.command(name="searching")
    async def searching(self, ctx):
        """
        Search for gacha coins.
        Has a cooldown of 2 hours.
        80% chance to find 5-10 coins, 20% chance to find nothing.
        
        Usage: Statbot!searching
        """
        # Get last used time for searching command
        last_used = await self.bot.db_manager.get_cooldown(ctx.author.id, "searching")
        
        # Check if on cooldown
        on_cooldown, remaining = is_on_cooldown(last_used, SEARCHING_COOLDOWN)
        if on_cooldown:
            minutes, seconds = divmod(remaining, 60)
            hours, minutes = divmod(minutes, 60)
            
            if hours > 0:
                await ctx.send(f"You can search again in {int(hours)} hours and {int(minutes)} minutes.")
            else:
                await ctx.send(f"You can search again in {int(minutes)} minutes and {int(seconds)} seconds.")
            return
        
        # Set cooldown
        current_time = int(time.time())
        await self.bot.db_manager.set_cooldown(ctx.author.id, "searching", current_time)
        
        # Determine if search was successful
        success = random.random() < SEARCHING_PROBABILITIES["success"]
        
        if success:
            # Determine coin amount
            coin_range = SEARCHING_PROBABILITIES["coin_range"]
            coins_found = random.randint(coin_range[0], coin_range[1])
            
            # Add coins to user
            await self.bot.db_manager.add_coins(ctx.author.id, coins_found)
            
            # Create and send success embed
            embed = create_searching_embed(ctx.author, True, coins_found)
            await ctx.send(embed=embed)
        else:
            # Create and send failure embed
            embed = create_searching_embed(ctx.author, False)
            await ctx.send(embed=embed)

-------------------------------------------------------------------
# FILE: cogs/inventory.py
-------------------------------------------------------------------
import discord
import logging
from discord.ext import commands

from config import ITEMS, MAX_HP, MAX_ENERGY
from utils.embeds import create_inventory_embed

logger = logging.getLogger(__name__)

class Inventory(commands.Cog):
    """
    Inventory management for the RPG bot.
    Handles displaying and using items.
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="inventory")
    async def inventory(self, ctx):
        """
        Display your inventory.
        
        Usage: Statbot!inventory
        """
        # Get user inventory
        inventory = await self.bot.db_manager.get_inventory(ctx.author.id)
        
        # Create and send inventory embed
        embed = create_inventory_embed(ctx.author, inventory, ITEMS)
        await ctx.send(embed=embed)
    
    @commands.command(name="use")
    async def use_item(self, ctx, *, item_name: str):
        """
        Use an item from your inventory.
        
        Usage: Statbot!use <item_name>
        """
        # Get user inventory
        inventory = await self.bot.db_manager.get_inventory(ctx.author.id)
        
        # Find the item ID from the name
        found_item_id = None
        for item_id, item_data in ITEMS.items():
            if item_data['name'].lower() == item_name.lower():
                found_item_id = item_id
                break
        
        if not found_item_id:
            await ctx.send(f"Item '{item_name}' not found. Check your inventory with `Statbot!inventory`.")
            return
        
        # Check if user has the item
        if found_item_id not in inventory or inventory[found_item_id] <= 0:
            await ctx.send(f"You don't have any {item_name} in your inventory.")
            return
        
        # Get the item data
        item = ITEMS[found_item_id]
        
        # Apply item effects
        user_data = await self.bot.db_manager.get_user(ctx.author.id)
        effect_applied = False
        effect_description = ""
        
        if 'effect' in item:
            for stat, value in item['effect'].items():
                if stat == 'hp':
                    # HP cannot exceed max
                    new_hp = min(user_data['hp'] + value, MAX_HP)
                    await self.bot.db_manager.update_user_stat(ctx.author.id, 'hp', new_hp)
                    effect_description += f"+{new_hp - user_data['hp']} HP"
                    effect_applied = True
                    
                elif stat == 'energy':
                    # Energy cannot exceed max
                    new_energy = min(user_data['energy'] + value, MAX_ENERGY)
                    await self.bot.db_manager.update_user_stat(ctx.author.id, 'energy', new_energy)
                    effect_description += f"+{new_energy - user_data['energy']} Energy"
                    effect_applied = True
        
        if effect_applied:
            # Remove one of the item from inventory
            await self.bot.db_manager.remove_item_from_inventory(ctx.author.id, found_item_id)
            
            # Send success message
            await ctx.send(f"You used {item['emoji']} **{item['name']}**. Effect: {effect_description}")
        else:
            await ctx.send(f"Something went wrong when using the item. No effect was applied.")

-------------------------------------------------------------------
# FILE: cogs/profile.py
-------------------------------------------------------------------
import discord
import logging
import time
from discord.ext import commands

from config import EXERCISE_COOLDOWN
from utils.embeds import create_profile_embed, create_exercise_embed
from utils.helpers import calculate_exp_gain, get_current_level, is_on_cooldown

logger = logging.getLogger(__name__)

class Profile(commands.Cog):
    """
    Profile management for the RPG bot.
    Handles displaying user profiles and leveling mechanics.
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="profile")
    async def profile(self, ctx, user: discord.Member = None):
        """
        Display your profile or another user's profile.
        
        Usage: Statbot!profile or Statbot!profile @username
        """
        # If no user specified, show the command author's profile
        if user is None:
            user = ctx.author
            
        # Get user data
        user_data = await self.bot.db_manager.get_user(user.id)
        
        # Create and send profile embed
        embed = create_profile_embed(user, user_data)
        await ctx.send(embed=embed)
    
    @commands.command(name="exercise")
    async def exercise(self, ctx):
        """
        Exercise to gain EXP. Can be used once per day.
        
        Usage: Statbot!exercise
        """
        # Get last used time for exercise command
        last_used = await self.bot.db_manager.get_cooldown(ctx.author.id, "exercise")
        
        # Check if on cooldown
        on_cooldown, remaining = is_on_cooldown(last_used, EXERCISE_COOLDOWN)
        if on_cooldown:
            minutes, seconds = divmod(remaining, 60)
            hours, minutes = divmod(minutes, 60)
            
            await ctx.send(f"You can exercise again in {int(hours)} hours, {int(minutes)} minutes, and {int(seconds)} seconds.")
            return
        
        # Set cooldown
        current_time = int(time.time())
        await self.bot.db_manager.set_cooldown(ctx.author.id, "exercise", current_time)
        
        # Calculate EXP gain
        exp_gain = calculate_exp_gain()
        
        # Get user data
        user_data = await self.bot.db_manager.get_user(ctx.author.id)
        
        # Get current level before adding EXP
        current_level = get_current_level(user_data['exp'])
        
        # Add EXP
        user_data['exp'] += exp_gain
        await self.bot.db_manager.update_user_stat(ctx.author.id, 'exp', user_data['exp'])
        
        # Calculate new level
        new_level = get_current_level(user_data['exp'])
        
        # Check if user leveled up
        level_up = new_level > current_level
        
        if level_up:
            # Update level in database
            await self.bot.db_manager.update_user_stat(ctx.author.id, 'level', new_level)
        
        # Create and send exercise embed
        embed = create_exercise_embed(ctx.author, exp_gain, user_data['exp'], new_level, level_up)
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Initialize user data when someone joins the server."""
        # This will create a default user entry if the user doesn't exist
        await self.bot.db_manager.get_user(member.id)
        logger.info(f"Initialized database entry for new member: {member.name} (ID: {member.id})")

-------------------------------------------------------------------
# FILE: .env (Template - replace with your values)
-------------------------------------------------------------------
# Discord bot token from Discord Developer Portal
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Flask session secret key
SESSION_SECRET=your_session_secret_here

-------------------------------------------------------------------
# FILE: README.md
-------------------------------------------------------------------
# Mortem House Stat - Discord RPG Bot

A Discord RPG bot offering immersive gameplay with combat mechanics, character progression, inventory management, and gacha-style item collection.

## Features

- **Player Profiles**: Display HP, Energy, Level, and EXP
- **Combat System**: Attack other players and defend yourself
- **Inventory Management**: Collect and use items
- **Gacha System**: Roll for new items using gacha coins
- **Admin Commands**: Special commands for server moderators

## Bot Commands

All commands use the prefix `Statbot!`

### Profile Commands
- `Statbot!profile` - View your profile
- `Statbot!profile @username` - View another user's profile
- `Statbot!exercise` - Exercise once per day to gain EXP

### Combat Commands
- `Statbot!attack @username` - Attack another user

### Inventory Commands
- `Statbot!inventory` - View your inventory
- `Statbot!use [item name]` - Use an item from your inventory

### Gacha Commands
- `Statbot!gacha` - Roll the gacha (costs 10 coins)
- `Statbot!searching` - Search for gacha coins (2 hour cooldown)

### Admin Commands
- `Statbot!heal @username` - Fully restore a user's HP and Energy (healing role only)
- `Statbot!grantexp @username [amount]` - Grant EXP to a user (moderator+ only)
- `Statbot!grantrole @role` - Add a role to authorized roles (owner only)
- `Statbot!grantmodrole @role` - Add a role to moderator roles (owner only)
- `Statbot!revokerole @role` - Remove a role from authorized roles (owner only)
- `Statbot!revokemodrole @role` - Remove a role from moderator roles (owner only)

## Setup for 24/7 Uptime

To ensure your bot stays online 24/7, follow these steps:

1. **Enable Replit Always On**:
   - In your Replit project, click on "Tools" in the left sidebar
   - Select "Always On" 
   - Toggle the switch to enable

2. **Use an External Uptime Service**:
   - Sign up for a free account at [UptimeRobot](https://uptimerobot.com/)
   - Add a new HTTP(s) monitor 
   - Enter your Replit URL: `https://[your-repl-name].[your-username].repl.co/status`
   - Set the monitoring interval to 5 minutes

## Troubleshooting

If your bot goes offline:

1. Check that the DISCORD_BOT_TOKEN is still valid
2. Verify the Replit is running (green "Running" indicator)
3. Check UptimeRobot for any downtime alerts
4. Restart the Replit project

## Important Links

- Discord Developer Portal: https://discord.com/developers/applications
- UptimeRobot: https://uptimerobot.com/
- Discord.py Documentation: https://discordpy.readthedocs.io/