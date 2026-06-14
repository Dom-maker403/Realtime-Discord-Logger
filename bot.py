import os
import json
import uuid
import re
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from anthropic import Anthropic  


# --- System & Environment Setup ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
REVIEW_CHANNEL_ID = int(os.getenv("REVIEW_CHANNEL_ID"))
CUSTOMER_CHANNEL_ID = int(os.getenv("CUSTOMER_CHANNEL_ID"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
STAFF_PING_ID = os.getenv("STAFF_PING_ID", "")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_PATH = os.path.join(BASE_DIR, "inbox.json")


# ✅ Production standard initialization
anthropic_client_instance = Anthropic(api_key=ANTHROPIC_API_KEY)


intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)




# ==========================================
#     🤖 HELPER: LLM DRAFT GENERATION
# ==========================================
def generate_ai_draft(customer_message, staff_feedback=None):
    """Calls Claude to analyze sentiment and draft tailored responses."""
    print("🧠 Calling Anthropic API endpoint to analyze and generate premium draft response...")
   
    system_prompt = (
        "You are an elite, expert retail customer support engineer for Domo's Tech Hub, a premier custom computer and component storefront. "
        "Analyze the customer query thoroughly.\n\n"
        "CRITICAL SENTIMENT CRITERIA:\n"
        "- If the customer mentions broken components, smoke, sparks, shipping damage, missing high-value orders, or uses aggressive/deeply frustrated language, set the sentiment to exactly: URGENT\n"
        "- Otherwise, classify as positive or neutral based on context.\n\n"
        "DRAFTING RULES:\n"
        "- Be professional, empathetic, and direct. Do not say 'As an AI...'\n"
        "- Address hardware issues with technical precision (e.g., grounding, loose connections, cable seating).\n\n"
        "Provide your final analysis wrapped inside this precise XML format:\n"
        "<sentiment>positive/neutral/URGENT</sentiment>\n"
        "<draft>Your premium, complete retail support response draft goes here</draft>"
    )


    user_content = customer_message
    if staff_feedback:
        user_content = (
            f"Original Customer Message: {customer_message}\n\n"
            f"Staff feedback on previous draft: {staff_feedback}\n\n"
            f"Please regenerate the draft response incorporating the staff feedback perfectly."
        )


    try:
        response = anthropic_client_instance.messages.create(
            model="claude-haiku-4-5-20251001", # ✅ Production standard string
            max_tokens=1000,
            temperature=0.5,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}]
        )
        raw_text = response.content[0].text
       
        # Safe RegEx Extractors for XML Tags
        sentiment_match = re.search(r"<sentiment>(.*?)</sentiment>", raw_text, re.DOTALL)
        draft_match = re.search(r"<draft>(.*?)</draft>", raw_text, re.DOTALL)
        
        sentiment = sentiment_match.group(1).strip() if sentiment_match else "neutral"
        draft = draft_match.group(1).strip() if draft_match else raw_text
           
        return sentiment, draft
    except Exception as e:
        print(f"❌ Claude API Call failed: {e}")
        return "neutral", f"Error generating automated draft. Staff review required. (Details: {e})"




# ==========================================
#    ⚡ LIVE EVENT: PUBLIC & THREAD CATCHER
# ==========================================
@client.event
async def on_message(message):
    if message.author == client.user:
        return


    # Handle Staff Feedback inside revision threads
    if isinstance(message.channel, discord.Thread) and message.channel.parent_id == REVIEW_CHANNEL_ID:
        try:
            with open(INBOX_PATH, 'r') as f:
                inbox_list = json.load(f)
        except Exception:
            return


        file_updated = False
        for ticket in inbox_list:
            if ticket.get('status') == 'under_revision' and ticket.get('review_msg_id') == message.channel.id:
                print(f"✍️ Staff feedback received for ticket {ticket['ticket_id']}: '{message.content}'")
               
                sentiment, dynamic_draft = generate_ai_draft(ticket['message'], staff_feedback=message.content)
               
                ticket['sentiment'] = sentiment
                ticket['draft_reply'] = dynamic_draft
                ticket['status'] = 'pending_review' 
                ticket['review_msg_id'] = None      
                file_updated = True
               
                try:
                    await message.channel.delete()
                    print(f"🧹 Closed revision thread for ticket {ticket['ticket_id']}.")
                except Exception as thread_err:
                    print(f"⚠️ Could not delete thread: {thread_err}")
                break


        if file_updated:
            with open(INBOX_PATH, 'w') as f:
                json.dump(inbox_list, f, indent=4)
        return


    # Catch inbound customer messages in public chat
    if message.channel.id != CUSTOMER_CHANNEL_ID:
        return


    print(f"📩 Live ticket captured from {message.author.name}! Initializing in queue...")


    try:
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        inbox_list = []


    new_ticket = {
        "ticket_id": f"tk_{str(uuid.uuid4())[:8]}",
        "customer_name": message.author.name,
        "customer_id": str(message.author.id),
        "channel_id": str(message.channel.id),
        "message": message.content,
        "sentiment": "neutral",
        "draft_reply": "Generating draft...",
        "status": "unread", 
        "review_msg_id": None
    }


    inbox_list.append(new_ticket)
   
    try:
        with open(INBOX_PATH, 'w') as f:
            json.dump(inbox_list, f, indent=4)
        print(f"💾 Ticket {new_ticket['ticket_id']} safely queued as unread.")
    except Exception as e:
        print(f"❌ Failed to save live ticket to file: {e}")




# ==========================================
#     🔄 UNIFIED BACKGROUND QUEUE LOOP
# ==========================================
@tasks.loop(seconds=5)
async def process_ticket_pipeline():
    """Loops through all tickets in the queue safely without double-posting."""
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
        if ticket.get('status') == 'unread':
            customer_name = ticket.get('customer_name', 'Unknown Customer')
            print(f"📥 Processing unread message from {customer_name} ({ticket['ticket_id']})...")
            sentiment, draft_reply = generate_ai_draft(ticket.get('message', 'No message content provided.'))
            ticket['sentiment'] = sentiment
            ticket['draft_reply'] = draft_reply
            ticket['status'] = 'pending_review'
            file_updated = True


        if ticket.get('status') == 'pending_review' and not ticket.get('review_msg_id'):
            ticket['review_msg_id'] = "PROCESSING"
            file_updated = True
           
            with open(INBOX_PATH, 'w') as f:
                json.dump(inbox_list, f, indent=4)


            print(f"📢 Generating staff review card for {ticket.get('customer_name')}...")


            ticket_sentiment = ticket.get('sentiment', 'neutral').upper()
           
            if ticket_sentiment == "URGENT":
                embed_title = "🔥 URGENT TICKET PRIORITY CRITICAL 🔥"
                card_color = discord.Color.red()
                alert_text = f"🚨 <@{STAFF_PING_ID}> **Emergency Review Escalation Required!**" if STAFF_PING_ID else "🚨 **Emergency Review Escalation Required!**"
            else:
                embed_title = "🚨 Ticket Review Needed (STANDARD Priority)"
                card_color = discord.Color.blue()
                alert_text = "New standard ticket awaiting review."


            embed = discord.Embed(
                title=embed_title,
                description=f"**Customer:** {ticket.get('customer_name', 'Unknown')}\n**Sentiment:** {ticket_sentiment}",
                color=card_color
            )
            
            original_msg = ticket['message']
            draft_msg = ticket['draft_reply']
            if len(original_msg) > 1024:
                original_msg = original_msg[:1020] + "..."
            if len(draft_msg) > 1024:
                draft_msg = draft_msg[:1020] + "..."
            
            embed.add_field(name="💬 Original Message", value=original_msg, inline=False)
            embed.add_field(name="🤖 AI Suggested Draft Reply", value=draft_msg, inline=False)
            embed.set_footer(text=f"Ticket ID: {ticket['ticket_id']} | 👍 Approve | 👎 Reject")


            try:
                msg = await review_channel.send(content=alert_text if ticket_sentiment == "URGENT" else None, embed=embed)
                await msg.add_reaction("👍")
                await msg.add_reaction("👎")


                ticket['review_msg_id'] = msg.id
                ticket['status'] = 'waiting_human_click'
            except Exception as send_err:
                print(f"❌ Failed to post review card: {send_err}")
                ticket['review_msg_id'] = None
                ticket['status'] = 'pending_review'


    if file_updated:
        with open(INBOX_PATH, 'w') as f:
            json.dump(inbox_list, f, indent=4)




# ==========================================
#      EVENT: RAW EMOJI REACTION LISTENER
# ==========================================
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
               
                try:
                    if review_msg.embeds:
                        updated_embed = review_msg.embeds[0].copy()
                        updated_embed.color = embed_color
                        updated_embed.set_footer(text=f"Status: {status_text} | ID: {target_ticket_id}")
                        await review_msg.edit(embed=updated_embed)
                    await review_msg.clear_reactions()
                except Exception:
                    pass


            elif emoji_str == "👎":
                print(f"🔄 Ticket {ticket['ticket_id']} rejected. Creating revision thread...")
                ticket['status'] = 'under_revision'
                status_text = "🔄 Revision In Progress"
                embed_color = discord.Color.gold()
               
                try:
                    if review_msg.embeds:
                        updated_embed = review_msg.embeds[0].copy()
                        updated_embed.color = embed_color
                        updated_embed.set_footer(text=f"Status: {status_text} | ID: {target_ticket_id}")
                        await review_msg.edit(updated_embed)
                    await review_msg.clear_reactions()
                   
                    thread = await review_msg.create_thread(
                        name=f"Fix-Ticket-{ticket['ticket_id']}",
                        auto_archive_duration=60
                    )
                    await thread.send(
                        f"👋 <@{payload.user_id}>, what should Claude fix in this draft? "
                        f"Just type your instructions below."
                    )
                    ticket['review_msg_id'] = thread.id
                except Exception as thread_create_err:
                    print(f"❌ Failed to set up correction thread: {thread_create_err}")
                    ticket['status'] = 'rejected'


            file_updated = True
            break


    if file_updated:
        with open(INBOX_PATH, 'w') as f:
            json.dump(inbox_list, f, indent=4)




# ==========================================
#         BOT LIFE SYSTEM INITIALIZER
# ==========================================
@client.event
async def on_ready():
    print(f"🟢 Discord Gateway Active! Connected as: {client.user}")
    if not process_ticket_pipeline.is_running():
        process_ticket_pipeline.start()
        print("🔍 Multi-Queue pipeline background worker loop active.")




if __name__ == "__main__":
    print("📡 Starting Multi-Queue Discord Customer Pipeline Bot...")
    
    # ⚡ FORCED PRE-FLIGHT TEST: Verify Anthropic credentials BEFORE boot
    print("⚡ Verifying API connection...")
    try:
        test_response = anthropic_client_instance.messages.create(
            model="claude-haiku-4-5-20251001", # ✅ Production standard string
            max_tokens=10,
            messages=[{"role": "user", "content": "Ping"}]
        )
        print("✅ Anthropic API Credentials verified successfully!")
    except Exception as api_err:
        print("\n🛑 CRITICAL ERROR: Anthropic initialization failed!")
        print(f"Details: {api_err}")
        print("Please check your .env file or model string identifiers.\n")
        os._exit(1)
        
    client.run(TOKEN)



