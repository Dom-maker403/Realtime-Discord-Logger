import discord
import requests

from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
N8N_WEBHOOK_URL = 'http://localhost:5678/webhook/...'

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    # Don't log if the message is from a bot
    if message.author.bot:
        return

  
    try:
        with open('/home/domocsolid/current_status.txt', 'a') as f:
            f.write(f"{message.author}: {message.content}\n")
    except Exception as e:
        print(f"Failed to write to file: {e}")
    

    
    payload = {
        "content": message.content, 
        "author": str(message.author)
    }
    
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload)
        print(f"I heard: {message.content} from {message.author}")
    except Exception as e:
        print(f"Error sending to n8n: {e}")

client.run(TOKEN)



