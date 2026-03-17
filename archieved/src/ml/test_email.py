import logging
from email.mime.text import MIMEText
import smtplib
from datetime import datetime

# === TEMPORARY TEST VALUES — replace these 3 lines only ===
SMTP_USER = "emmanuelebubembachu@gmail.com"          # ← your Gmail
SMTP_PASS = "yqtkbqeaydtvzshh"             # ← your 16-char App Password (NOT normal password!)
EMAIL_TO  = "emmanuelebubembachu@gmail.com"          # ← your email OR phone SMS gateway (see below)

def send_email(alert_text):
    msg = MIMEText(alert_text)
    msg['Subject'] = '💰 Scalable Brain Trade Alert - TEST'
    msg['From'] = SMTP_USER
    msg['To'] = EMAIL_TO

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
            print("✅ SUCCESS: Email alert sent!")
            logging.info("Email alert sent.")
    except Exception as e:
        print(f"❌ FAILED: {type(e).__name__}: {e}")
        logging.error(f"Email send failed: {e}")

# ====================== RUN THE TEST ======================
if __name__ == "__main__":
    test_alert = f"Test message from trading bot at {datetime.now()}\nPrice: $123.45 | Signal: BUY"
    send_email(test_alert)
    print("Test finished — check the output above!")