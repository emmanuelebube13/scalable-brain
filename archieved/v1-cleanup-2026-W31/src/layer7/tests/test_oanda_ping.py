import os
import requests
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

# Grab the exact variables you set
API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID_DEMO")
OANDA_URL = "https://api-fxpractice.oanda.com/v3"

def ping_oanda():
    if not API_KEY or not ACCOUNT_ID:
        print("[!] Error: Missing OANDA_API_KEY or OANDA_ACCOUNT_ID_DEMO in your .env file.")
        return

    print(f"Pinging Oanda Practice Account: {ACCOUNT_ID}...")
    
    # The endpoint for retrieving account summary
    endpoint = f"{OANDA_URL}/accounts/{ACCOUNT_ID}/summary"
    
    # Oanda requires the Bearer token for authentication
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept-Datetime-Format": "RFC3339"
    }

    try:
        response = requests.get(endpoint, headers=headers)
        
        if response.status_code == 200:
            data = response.json().get("account", {})
            balance = data.get("balance")
            currency = data.get("currency")
            margin_avail = data.get("marginAvailable")
            
            print("\n✅ SUCCESS! Connection Established.")
            print("-------------------------------------------------")
            print(f"Account Currency   : {currency}")
            print(f"Current Balance    : ${balance}")
            print(f"Available Margin   : ${margin_avail}")
            print("-------------------------------------------------")
            print("You are cleared hot to start building the Fractional Kelly execution module!")
        else:
            print(f"\n❌ FAILED to connect. Status Code: {response.status_code}")
            print(f"Error Message: {response.text}")
            
    except Exception as e:
        print(f"\n❌ System Error: {str(e)}")

if __name__ == "__main__":
    ping_oanda()