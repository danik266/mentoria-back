import os
import asyncio
import urllib.request
import urllib.parse
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv(override=True)


def _send_tg_sync(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read()

async def send_telegram(chat_id: int, text: str):
    """
    Sends a message to a Telegram Chat ID.
    If bot token is not configured, it will print the message to the console.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "YOUR_BOT_TOKEN":
        print(f"\n[TELEGRAM MOCK SEND] to chat_id={chat_id}:\n{text}\n")
        return True
        
    try:
        await asyncio.to_thread(_send_tg_sync, token, chat_id, text)
        return True
    except Exception as e:
        print(f"[Telegram Send Error] Failed to send message to {chat_id}: {e}")
        return False

def _send_email_sync(smtp_host, smtp_port, username, password, from_email, to_email, subject, body):
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    if smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        
    server.login(username, password)
    server.send_message(msg)
    server.quit()

async def send_email(to_email: str, subject: str, body: str):
    """
    Sends an email to a user.
    If SMTP variables are not configured, it will print the email to the console.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port_str = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM", username)
    
    if not smtp_host or not username or not password or smtp_host == "YOUR_SMTP_HOST":
        print(f"\n[EMAIL MOCK SEND] to={to_email}\nSubject: {subject}\nBody:\n{body}\n")
        return True
        
    # If using Resend, prefer their HTTPS REST API over SMTP to bypass cloud provider port blocks
    if smtp_host and "resend.com" in smtp_host.lower() and password.startswith("re_"):
        try:
            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {password}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            payload = {
                "from": from_email,
                "to": to_email,
                "subject": subject,
                "text": body
            }
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            
            def _api_call():
                with urllib.request.urlopen(req, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))
                    
            res = await asyncio.to_thread(_api_call)
            print(f"[Email Send] Successfully sent email via Resend API to {to_email}: {res}")
            return True
        except Exception as e:
            if hasattr(e, "read"):
                try:
                    error_details = e.read().decode("utf-8")
                    print(f"[Email Send Error] Resend API detail: {error_details}")
                except:
                    pass
            print(f"[Email Send Error] Failed to send email via Resend API to {to_email}: {e}")
            print("[Email Send] Falling back to SMTP...")
            
    smtp_port = int(smtp_port_str) if smtp_port_str else 587
    try:
        await asyncio.to_thread(
            _send_email_sync, 
            smtp_host, 
            smtp_port, 
            username, 
            password, 
            from_email, 
            to_email, 
            subject, 
            body
        )
        return True
    except Exception as e:
        print(f"[Email Send Error] Failed to send email to {to_email}: {e}")
        return False
