import os
import json
import uuid
import discord
from discord.ext import tasks
from dotenv import load_dotenv

# Try importing your custom client fallback module if standard anthropic isn't used
try:
    import anthropic_client
    anthropic_module = anthropic_client.anthropic
except ImportError:
    import anthropic
    anthropic_module = anthropic

# --- System & Environment Setup ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
REVIEW_CHANNEL_ID = int(os.getenv("REVIEW_CHANNEL_ID"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# 🔥 NEW ENVIRONMENT VARIABLE: The public channel your customers use
# Add CUSTOMER_CHANNEL_ID=your_id to your .env file
CUSTOMER_CHANNEL_ID = int(os.getenv("CUSTOMER_CHANNEL_ID"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_PATH = os.path.join(BASE_DIR, "inbox.json")

# Initialize Direct Anthropic Client using your working syntax architecture
anthropic_client_instance = anthropic_module.Anthropic(api_key=ANTHROPIC_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)


# ==========================================
#     🤖 HELPER: LLM DRAFT GENERATION
# ==========================================

#Sends the customer's message to Claude, analyzes the sentiment and returns a drafted reply based on the tone and content of the message
def generate_ai_draft(customer_message):
    """Calls Claude to analyze sentiment and draft a tailored response."""
    print("🧠 Calling working Anthropic API endpoint to analyze and generate draft response...")
    
    system_prompt = (
        "You are an elite, helpful retail customer support agent. "
        "Analyze the customer query. Be polite, clear, and concise. "
        "Provide your answer wrapped inside an XML tag format like this:\n"
        "<sentiment>positive/neutral/negative</sentiment>\n"
        "<draft>Your support reply draft goes here</draft>"
    )

    try:
        response = anthropic_client_instance.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            temperature=0.5,
            system=system_prompt,
            messages=[{"role": "user", "content": customer_message}]
        )
        raw_text = response.content[0].text
        
        sentiment = "neutral"
        if "<sentiment>" in raw_text:
            sentiment = raw_text.split("<sentiment>")[1].split("</sentiment>")[0].strip()
            
        draft = "Thank you for reaching out! A team member will be with you shortly."
        if "<draft>" in raw_text:
            draft = raw_text.split("<draft>")[1].split("</draft>")[0].strip()
            
        return sentiment, draft
    except Exception as e:
        
        return "neutral", "Thank you for your message. We are reviewing your request."


# ==========================================
#    ⚡ LIVE EVENT: PUBLIC TICKET CATCHER
# ==========================================
@client.event

# Listens for new customer messages in the designated channel, generates an AI draft immediately, and saves the ticket to inbox.json as pending_review, bypassing the background loop to prevent double processing
async def on_message(message):
    # 🛑 GOLDEN RULE: Never process messages sent by the bot itself!
    if message.author == client.user:
        return

    # Only catch messages typed inside your designated customer help channel
    if message.channel.id != CUSTOMER_CHANNEL_ID:
        return

    print(f"📩 Live ticket captured from {message.author.name}! Generating draft immediately...")

    # 1. Read current array contents safely
    try:
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        inbox_list = []

    # 2. Generate the AI draft immediately right here to prevent loop racing
    sentiment, draft_reply = generate_ai_draft(message.content)

    # 3. Build the ticket object already processed and ready for Phase 2 dispatch
    new_ticket = {
        "ticket_id": f"tk_{str(uuid.uuid4())[:8]}",
        "customer_name": message.author.name,
        "customer_id": str(message.author.id),
        "channel_id": str(message.channel.id),
        "message": message.content,
        "sentiment": sentiment,
        "draft_reply": draft_reply,
        "status": "pending_review",  # 🔥 Skips 'unread' phase so the background loop never double-processes it!
        "review_msg_id": None
    }

    # 4. Append to database file instantly
    inbox_list.append(new_ticket)
    
    try:
        with open(INBOX_PATH, 'w') as f:
            json.dump(inbox_list, f, indent=4)
        print(f"💾 Ticket {new_ticket['ticket_id']} securely queued as pending_review.")
    except Exception as e:
        print(f"❌ Failed to save live ticket to file: {e}")



# ==========================================
#     🔄 UNIFIED BACKGROUND QUEUE LOOP
# ==========================================

# Runs every 5 seconds, checks inbox.json for unread tickets to generate AI drafts and pending_review tickets to dispath staff embed cards on Discord, using PROCESSING lock to prevent double posting
@tasks.loop(seconds=5)
async def process_ticket_pipeline():
    """Loops through all tickets in the queue safely without double-posting."""
    # 🔥 FIXED: Robust channel fetching so it never returns None and crashes
    review_channel = client.get_channel(REVIEW_CHANNEL_ID)
    if not review_channel:
        try:
            review_channel = await client.fetch_channel(REVIEW_CHANNEL_ID)
        except Exception:
            return

    try:
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    file_updated = False

    for ticket in inbox_list:
        # --- PHASE 1: GENERATE DRAFT FOR UNREAD TICKETS (Fallback safety) ---
        if ticket.get('status') == 'unread':
            customer_name = ticket.get('customer_name', 'Unknown Customer')
            print(f"📥 Processing unread message from {customer_name} ({ticket['ticket_id']})...")
            
            sentiment, draft_reply = generate_ai_draft(ticket.get('message', 'No message content provided.'))
            
            ticket['sentiment'] = sentiment
            ticket['draft_reply'] = draft_reply
            ticket['status'] = 'pending_review'
            file_updated = True

        # --- PHASE 2: DISPATCH EMBED FOR TICKETS PENDING REVIEW ---
        if ticket.get('status') == 'pending_review' and not ticket.get('review_msg_id'):
            # 🔥 THE LOCK: Instantly give it a placeholder ID so the next loop cycle ignores it while we wait on Discord
            ticket['review_msg_id'] = "PROCESSING"
            file_updated = True
            
            # Save immediately to lock it in the JSON file
            with open(INBOX_PATH, 'w') as f:
                json.dump(inbox_list, f, indent=4)

            print(f"📢 Generating staff review card for {ticket.get('customer_name')}...")

            embed = discord.Embed(
                title="🚨 Ticket Review Needed (STANDARD Priority)",
                description=f"**Customer:** {ticket.get('customer_name', 'Unknown')}\n**Sentiment:** {ticket.get('sentiment', 'NEUTRAL').upper()}",
                color=discord.Color.blue()
            )
            embed.add_field(name="💬 Original Message", value=ticket['message'], inline=False)
            embed.add_field(name="🤖 AI Suggested Draft Reply", value=ticket['draft_reply'], inline=False)
            embed.set_footer(text=f"Ticket ID: {ticket['ticket_id']} | 👍 Approve | 👎 Reject")

            try:
                msg = await review_channel.send(embed=embed)
                await msg.add_reaction("👍")
                await msg.add_reaction("👎")

                # Replace placeholder with the real Discord Message ID
                ticket['review_msg_id'] = msg.id
                ticket['status'] = 'waiting_human_click'
            except Exception as send_err:
                print(f"❌ Failed to post review card: {send_err}")
                # Reset if it fails so it can retry safely
                ticket['review_msg_id'] = None
                ticket['status'] = 'pending_review'

    if file_updated:
        with open(INBOX_PATH, 'w') as f:
            json.dump(inbox_list, f, indent=4)

# ==========================================
#      EVENT: RAW EMOJI REACTION LISTENER
# ==========================================

# Listens for emoji reactions on staff review cards - a thumbs approves and sends the draft reply directly to the customer, while a thumbs down rejects it and updates the embed card color and status accordingly
@client.event
async def on_raw_reaction_add(payload):
    if payload.user_id == client.user.id:
        return

    emoji_str = str(payload.emoji)
    if emoji_str not in ["👍", "👎"]:
        return

    review_msg_id = payload.message_id

    try:
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)
    except Exception:
        return

    try:
        staff_channel = client.get_channel(payload.channel_id) or await client.fetch_channel(payload.channel_id)
        review_msg = await staff_channel.fetch_message(review_msg_id)
    except Exception as fetch_err:
        print(f"❌ Failed to retrieve target message properties: {fetch_err}")
        return

    target_ticket_id = None
    if review_msg.embeds and review_msg.embeds[0].footer:
        footer_text = review_msg.embeds[0].footer.text or ""
        if "Ticket ID:" in footer_text:
            try:
                target_ticket_id = footer_text.split("Ticket ID:")[1].split("|")[0].strip()
            except Exception:
                pass

    file_updated = False
    
    for ticket in inbox_list:
        if ticket.get('ticket_id') == target_ticket_id and ticket.get('status') == 'waiting_human_click':
            
            if not ticket.get('review_msg_id'):
                ticket['review_msg_id'] = review_msg_id

            if emoji_str == "👍":
                customer_channel_id = int(ticket.get('channel_id'))
                draft_reply = ticket.get('draft_reply', '')
                customer_id = ticket.get('customer_id')

                try:
                    customer_channel = client.get_channel(customer_channel_id) or await client.fetch_channel(customer_channel_id)
                    if customer_channel:
                        await customer_channel.send(f"<@{customer_id}>, {draft_reply}")
                        print(f"🚀 Dispatched approved reply for ticket {ticket['ticket_id']}.")
                except Exception as dispatch_err:
                    print(f"❌ Failed sending message out to customer space: {dispatch_err}")

                ticket['status'] = 'completed'
                status_text = "✅ Approved & Sent"
                embed_color = discord.Color.green()

            elif emoji_str == "👎":
                print(f"❌ Ticket {ticket['ticket_id']} was rejected by staff.")
                ticket['status'] = 'rejected'
                status_text = "❌ Rejected by Staff"
                embed_color = discord.Color.red()

            file_updated = True
            
            try:
                if review_msg.embeds:
                    old_embed = review_msg.embeds[0]
                    updated_embed = old_embed.copy()
                    updated_embed.color = embed_color
                    updated_embed.set_footer(text=f"Status: {status_text} | ID: {target_ticket_id}")
                    
                    await review_msg.edit(embed=updated_embed)
                await review_msg.clear_reactions()
                print(f"🔒 Review panel card {ticket['ticket_id']} successfully preserved and closed.")
            except Exception as ui_err:
                print(f"⚠️ Failed updating card visual state configurations: {ui_err}")
            break

    if file_updated:
        with open(INBOX_PATH, 'w') as f:
            json.dump(inbox_list, f, indent=4)


# ==========================================
#         BOT LIFE SYSTEM INITIALIZER
# ==========================================
# When the bot successfully connects to Discord, it prints a confirmation to the terminal and prints a confirmation to the terminal and starts the background queue loop, but only if it isn't already running
@client.event
async def on_ready():
    print(f"🟢 Discord Gateway Active! Connected as: {client.user}")
    if not process_ticket_pipeline.is_running():
        process_ticket_pipeline.start()
        print("🔍 Multi-Queue pipeline background worker loop active.")

if __name__ == "__main__":
    print("📡 Starting Multi-Queue Discord Customer Pipeline Bot...")
    client.run(TOKEN)


