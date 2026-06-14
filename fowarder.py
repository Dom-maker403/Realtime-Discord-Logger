import os
import json
import discord
from discord.ext import tasks
from dotenv import load_dotenv

# --- System & Environment Setup ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
REVIEW_CHANNEL_ID = int(os.getenv("REVIEW_CHANNEL_ID"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_PATH = os.path.join(BASE_DIR, "inbox.json")

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True  # 🔥 THE MISSING LINK!
client = discord.Client(intents=intents)



# ==========================================
#     BACKGROUND TASK: MONITOR QUEUE
# ==========================================
@tasks.loop(seconds=5)
async def check_for_reviews():
    """Monitors inbox.json for tickets pending staff verification."""
    review_channel = client.get_channel(REVIEW_CHANNEL_ID)
    if not review_channel:
        return

    try:
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    file_updated = False

    for ticket in inbox_list:
        if ticket.get('status') == 'pending_review' and not ticket.get('review_msg_id'):
            print(f"📢 Posting ticket for {ticket['customer_name']} to staff review channel...")

            embed = discord.Embed(
                title="🚨 Ticket Review Needed (STANDARD Priority)",
                description=f"**Customer:** {ticket['customer_name']}\n**Sentiment:** {ticket.get('sentiment', 'NEUTRAL').upper()}",
                color=discord.Color.blue()
            )
            embed.add_field(name="💬 Original Message", value=ticket['message'], inline=False)
            embed.add_field(name="🤖 AI Suggested Draft Reply", value=ticket['draft_reply'], inline=False)
            embed.set_footer(text="React with 👍 to Approve and Send | 👎 to Reject")

            try:
                msg = await review_channel.send(embed=embed)
                await msg.add_reaction("👍")
                await msg.add_reaction("👎")

                ticket['review_msg_id'] = msg.id
                ticket['status'] = 'waiting_human_click'
                file_updated = True
            except Exception as send_err:
                print(f"❌ Failed to post review card: {send_err}")

    if file_updated:
        try:
            with open(INBOX_PATH, 'w') as f:
                json.dump(inbox_list, f, indent=4)
            print("💾 Database securely synchronized with review message IDs.")
        except Exception as write_err:
            print(f"❌ Failed to write database update: {write_err}")


# ==========================================
#      EVENT: RAW EMOJI REACTION LISTENER
# ==========================================
@client.event
async def on_raw_reaction_add(payload):
    # Ignore reactions from this specific script instance
    if payload.user_id == client.user.id:
        return

    emoji_str = str(payload.emoji)
    if emoji_str not in ["👍", "👎"]:
        return

    review_msg_id = payload.message_id
    file_updated = False
    status_text = ""

    try:
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)
    except Exception as e:
        print(f"❌ Error reading database during reaction: {e}")
        return

    try:
        staff_channel = client.get_channel(payload.channel_id) or await client.fetch_channel(payload.channel_id)
        review_msg = await staff_channel.fetch_message(review_msg_id)
    except Exception as fetch_err:
        print(f"❌ Failed to retrieve target message properties: {fetch_err}")
        return

    # Fallback parsing: if the card embed exists, extract the customer name directly from it
    embed_customer_name = None
    if review_msg.embeds:
        desc = review_msg.embeds[0].description or ""
        if "**Customer:**" in desc:
            try:
                embed_customer_name = desc.split("**Customer:**")[1].split("\n")[0].strip()
            except Exception:
                pass

    for ticket in inbox_list:
        # Match by direct message ID reference OR fallback via customer name string matching
        is_msg_match = ticket.get('review_msg_id') == review_msg_id
        is_fallback_match = (embed_customer_name and ticket.get('customer_name') == embed_customer_name)
        
        if (is_msg_match or is_fallback_match) and ticket.get('status') == 'waiting_human_click':
            
            # Synchronize missing tracking parameters if matched via fallback name parsing
            if not ticket.get('review_msg_id'):
                ticket['review_msg_id'] = review_msg_id

            if emoji_str == "👍":
                customer_channel_id = ticket.get('channel_id')
                draft_reply = ticket.get('draft_reply', '')
                customer_id = ticket.get('customer_id')

                try:
                    customer_channel = client.get_channel(customer_channel_id) or await client.fetch_channel(customer_channel_id)
                    if customer_channel:
                        await customer_channel.send(f"<@{customer_id}>, {draft_reply}")
                        print(f"🚀 Dispatched approved reply to customer channel {customer_channel_id}.")
                except Exception as dispatch_err:
                    print(f"❌ Failed sending message out to customer space: {dispatch_err}")

                ticket['status'] = 'completed'
                status_text = "✅ Approved & Sent to Customer"
                embed_color = discord.Color.green()

            elif emoji_str == "👎":
                print(f"❌ Ticket for {ticket['customer_name']} was rejected by staff.")
                ticket['status'] = 'rejected'
                status_text = "❌ Rejected by Staff"
                embed_color = discord.Color.red()

            file_updated = True
            
            try:
                if review_msg.embeds:
                    old_embed = review_msg.embeds[0]
                    updated_embed = old_embed.copy()
                    updated_embed.color = embed_color
                    updated_embed.set_footer(text=f"Status: {status_text}")
                    
                    await review_msg.edit(embed=updated_embed)
                await review_msg.clear_reactions()
                print("🔒 Review panel card properties successfully preserved and closed.")
            except Exception as ui_err:
                print(f"⚠️ Failed updating card visual state configurations: {ui_err}")
            break

    if file_updated:
        with open(INBOX_PATH, 'w') as f:
            json.dump(inbox_list, f, indent=4)
        print("💾 Database securely updated with final ticket disposition.")


# ==========================================
#         BOT LIFE SYSTEM INITIALIZER
# ==========================================
@client.event
async def on_ready():
    print(f"🟢 Discord Gateway Active! Connected as: {client.user}")
    if not check_for_reviews.is_running():
        check_for_reviews.start()
        print("🔍 Background ticket queue monitor loop started.")

if __name__ == "__main__":
    print("📡 Starting Discord Gateway Connection Bot...")
    client.run(TOKEN)


