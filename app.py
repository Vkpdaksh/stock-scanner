# -------------------------------------------------------------
# TELEGRAM SECRETS & DISPATCHER FIX
# -------------------------------------------------------------
def get_secret(key_name):
    # Pehle Streamlit Cloud secrets check karega, fir system environment
    if key_name in st.secrets:
        return str(st.secrets[key_name])
    return os.environ.get(key_name, "")

TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")

def send_telegram_msg(msg_text):
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        return False, "Bot Token ya Chat ID missing hai! Streamlit Cloud Settings -> Secrets check karein."
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": msg_text,
            "parse_mode": "HTML"
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return True, "Success"
            return False, f"Telegram API Error: Status {response.status}"
    except Exception as e:
        return False, f"Error: {str(e)}"
