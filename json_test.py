ticket = {
	"customer_name": "Dom",
	"message": "My screen is cracked",
	"status": "unread"
}

print(ticket["customer_name"])
print(ticket["status"])

import json
print(json.dumps(ticket, indent=4))
