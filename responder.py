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
        # Open inbox.json and read all the message into memory
        # If the data isn't a list (empty or corrupted file), stop here
        with open(INBOX_PATH, 'r') as f:
            inbox_list = json.load(f)

        if not isinstance(inbox_list, list):
            return  
# Load the business rules and knowledge base into memory
# So Claude has context when analyzing each message
        with open(RULES_PATH, 'r') as f:
            business_rules = f.read()

        with open(KB_PATH, 'r') as f:
            knowledge_base = f.read()

        file_updated = False

        # Loop through every message inside the database array
        for ticket in inbox_list:
            if ticket.get('status') == 'unread':
                print(f"--- 🆕 Processing New Message from: {ticket['customer_name']} ---")
                # Build the full system prompt by combining business rules + knowledge base
                # This tells Claude how to behave and what format to return
                # Think of it like a job description you hand to a new employee before they start making calls
                full_system_prompt = (
                    f"{business_rules}\n\n"
                    f"COMPANY KNOWLEDGE BASE:\n{knowledge_base}\n\n"
                    "Return ONLY JSON with keys: sentiment, priority, draft_reply."
                )
                # Send the customer message to Claude along with the system prompt
                # Claude analyzes it using the rules and knowledge base, keeps response under 1000 tokens
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1000,
                    system=full_system_prompt,
                    messages=[
                        {"role": "user", "content": ticket['message']}
                    ]
                )

                # STEP C: THE OUTPUT & CLEANING
                raw_text = response.content[0].text
                # Extract Claude's response and clean off any markdown formatting
                clean_text = raw_text.strip().replace("```json", "").replace("```", "")
                # Convert the text into a Python dictionary so we can read each field
                ai_data = json.loads(clean_text)

                # Deep-cleaning catch to unpack nested strings if Claude double-serializes
                
                
                if isinstance(ai_data, str):
                    ai_data = json.loads(ai_data)
                # Print the sentiment, priority and draft reply to the terminal
                print("\n[AI ANALYSIS]")
                print(f"SENTIMENT: {ai_data.get('sentiment', 'N/A').upper()}")
                print(f"PRIORITY:  {ai_data.get('priority', 'N/A').upper()}")
                print(f"\n[DRAFT]\n{ai_data.get('draft_reply')}")

                # Mark this specific message as read inside the array
                ticket['status'] = 'read'
                file_updated = True
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

