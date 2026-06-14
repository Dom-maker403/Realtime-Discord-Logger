import time
import os

status_file = "/home/your-username/current_status.txt"
last_content = ""

print("👀 Status Watcher is LIVE. Send a message in Discord!")

while True:
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            current_content = f.read().strip()
            
        if current_content != last_content:
            print(f"🚀 New Status: {current_content}")
            # This is where you'd put the logic to update your status.json
            last_content = current_content
            
    time.sleep(2)




