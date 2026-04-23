import os
import anthropic
from dotenv import load_dotenv

# Force load the .env from the current folder
load_dotenv(os.path.join(os.getcwd(), '.env'))
api_key = os.getenv("ANTHROPIC_API_KEY")

# Manually pass the key to the client
client = anthropic.Anthropic(api_key=api_key)

def generate_report():
    try:
        # We point to the exact path shown in your VS Code sidebar
        with open('/home/domocsolid/current_status.txt', 'r') as f:
            log_data = f.read()
        
        if not log_data.strip():
            print("Logs are empty, Boss.")
            return

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="You are Dominique's Executive Assistant. Summarize these logs into a daily standup.",
            messages=[{"role": "user", "content": log_data}]
        )
        
        print("\n--- EA DAILY REPORT ---")
        print(response.content[0].text)
        print("-----------------------\n")

    except FileNotFoundError:
        print("Still can't find the file. Try moving current_status.txt into the AI_Journey folder!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_report()


