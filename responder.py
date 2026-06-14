import os
import json
import anthropic
import time
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# AUTOMATIC PATH FINDER: Points directly to your project root folder
# Set up file paths sp the script can find inbox.json, system_prompt.txt, and knowledge_base.md
# No matter what folder we run it from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_PATH = os.path.join(BASE_DIR, "inbox.json")
RULES_PATH = os.path.join(BASE_DIR, "system_prompt.txt")
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.md")

def run_auto_responder():
    try:
        # STEP A: THE READER
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)

        if not isinstance(inbox_list, list):
            return  

        with open(RULES_PATH, 'r') as f:
            business_rules = f.read()

        with open(KB_PATH, 'r') as f:
            knowledge_base = f.read()

        file_updated = False

        # Loop through every message inside the database array
        for ticket in inbox_list:
            if ticket.get('status') == 'unread':
                print(f"--- 🆕 Processing New Message from: {ticket['customer_name']} ---")
                
                # Combine instructions flawlessly
                full_system_prompt = (
                    f"{business_rules}\n\n"
                    f"COMPANY KNOWLEDGE BASE:\n{knowledge_base}\n\n"
                    "Return ONLY valid JSON with keys: sentiment, priority, draft_reply. Do not include markdown code block backticks."
                )

                # Adjusted API Call Structure to ensure 100% system parameter compliance
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1000,
                    system=full_system_prompt,
                    messages=[
                        {"role": "user", "content": ticket['message']}
                    ]
                )

                              # STEP C: THE OUTPUT & SAFE CLEANING
                raw_text = response.content[0].text
                clean_text = raw_text.strip()
                
                if clean_text.startswith("```"):
                    clean_text = clean_text.replace("```json", "").replace("```", "").strip()

                try:
                    ai_data = json.loads(clean_text)
                    if isinstance(ai_data, str):
                        ai_data = json.loads(ai_data)
                except json.JSONDecodeError:
                    print(f"❌ Failed to parse AI Response as JSON. Raw output was:\n{raw_text}")
                    ai_data = {
                        "sentiment": "UNKNOWN",
                        "priority": "STANDARD",
                        "draft_reply": "Thank you for your message. We are looking into this."
                    }
               # 1. Update all tracking keys in the data payload
                ticket['status'] = 'pending_review'
                ticket['sentiment'] = ai_data.get('sentiment', 'UNKNOWN')
                ticket['priority'] = ai_data.get('priority', 'STANDARD')
                ticket['draft_reply'] = ai_data.get('draft_reply', '')
                
                file_updated = True
                print(f"🔬 Success: {ticket['customer_name']}'s ticket state set to pending_review.")

                # 2. Commit the structural changes securely back to disk
                if file_updated:
                    with open(INBOX_PATH, 'w') as f:
                        json.dump(inbox_list, f, indent=4)
                    print("💾 inbox.json successfully updated on disk.")

                # 3. Clean terminal reporting
                print("\n[AI ANALYSIS]")
                print(f"SENTIMENT: {ticket['sentiment']}")
                print(f"PRIORITY: {ticket['priority']}")
                print(f"\n[DRAFT]\n{ticket['draft_reply']}")


                # Mark this specific message as read inside the array
                
                print(f"✅ Message from {ticket['customer_name']} processed and marked as READ.\n")

        # Save the updated array back to the file if any statuses changed
        if file_updated:
            with open(INBOX_PATH, 'w') as f:
                json.dump(inbox_list, f, indent=4)

    except Exception as e:
        print(f"Error: {e}")



if __name__ == "__main__":
    print("👀 Watcher Active... Listening for new data in inbox.json")
    while True:
        try:
            run_auto_responder()
            time.sleep(10)
        except KeyboardInterrupt:
            print("\nShutting down Watcher...")
            break


