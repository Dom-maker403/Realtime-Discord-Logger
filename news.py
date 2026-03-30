import requests
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from sumy.parsers.html import HtmlParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

load_dotenv()
# --- CONFIGURATION ---
WEBHOOK_URL = os.getenv ("WEBHOOK_URL")
KEYWORDS = ["python", " ai ", "automation", "llm", "bot", "web scraping", "robot", "alien"]

def get_summary(url):
    try:
        parser = HtmlParser.from_url(url, Tokenizer("english"))
        summarizer = LsaSummarizer()
        # Get 5 sentences to ensure we find "meaty" ones
        summary_sentences = summarizer(parser.document, 5)
        
        clean_sentences = []
        for s in summary_sentences:
            if len(str(s)) > 45: # Filter out short junk/menu text
                clean_sentences.append(str(s))
            if len(clean_sentences) == 2: # Keep the best 2
                break
        
        return " ".join(clean_sentences) if clean_sentences else "No summary available."
    except:
        return "Click link to read full article."

# --- MAIN EXECUTION ---
print("🚀 Starting the Research Bot...")

try:
    response = requests.get("https://news.ycombinator.com/")
    soup = BeautifulSoup(response.text, 'html.parser')
    headlines = soup.find_all('span', class_='titleline')

    matches = []
    for h in headlines:
        title = h.text
        link = h.find('a')
        if link:
            url = link['href'] 
        if any(word in title.lower() for word in KEYWORDS):
            print(f"🔎 Found match: {title}")
            summary = get_summary(url)
            matches.append(f"🎯 **{title}**\n📝 *AI Summary:* {summary}\n🔗 {link}")

    if matches:
        print(f"📦 Sending {len(matches)} matches to Discord...")
        payload = {"content": "\n\n".join(matches[:3])} # Top 3 only
        
        # DISCORD POST
        res = requests.post(WEBHOOK_URL, json=payload)
        
        if res.status_code == 204:
            print("✅ SUCCESS: Messages are now in Discord!")
        else:
            print(f"❌ DISCORD ERROR: Status {res.status_code} - {res.text}")
    else:
        print("😴 No matches found for your keywords today.")

except Exception as e:
    print(f"⚠️ SYSTEM ERROR: {e}")


