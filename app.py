import os
import requests
from flask import Flask, request
from google import genai

app = Flask(__name__)

# Read secret values from environment variables
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

GRAPH_VERSION = os.environ.get("GRAPH_API_VERSION", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")


@app.get("/")
def home():
    return "Facebook AI Bot server is running!"


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN and VERIFY_TOKEN:
        return challenge or "", 200

    return "Verification failed", 403


def ask_gemini(message):
    client = genai.Client(api_key=GEMINI_API_KEY)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            "You are a helpful, polite Facebook page assistant. "
            "Reply naturally in the language used by the customer. "
            "Keep replies clear and concise. Do not invent product "
            "prices, stock availability, or business policies.\n\n"
            f"Customer message: {message}"
        ),
    )

    return (response.text or "").strip() or "দুঃখিত, একটু পরে আবার চেষ্টা করুন।"


def send_message(recipient_id, message_text):
    url = (
        f"https://graph.facebook.com/"
        f"{GRAPH_VERSION}/me/messages"
    )

    response = requests.post(
        url,
        params={"access_token": PAGE_ACCESS_TOKEN},
        json={
            "recipient": {"id": recipient_id},
            "message": {"text": message_text[:2000]},
        },
        timeout=20,
    )

    response.raise_for_status()


@app.post("/webhook")
def receive_message():
    data = request.get_json(silent=True) or {}

    if data.get("object") != "page":
        return "Not a page event", 404

    # Acknowledge valid webhook notifications
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            message = event.get("message", {})
            sender = event.get("sender", {})
            sender_id = sender.get("id")

            # Ignore page echoes and non-text messages
            if message.get("is_echo"):
                continue

            text = message.get("text", "").strip()

            if not sender_id or not text:
                continue

            # Avoid replying to the page itself
            if sender_id == entry.get("id"):
                continue

            try:
                if not PAGE_ACCESS_TOKEN or not GEMINI_API_KEY:
                    raise RuntimeError("Required environment variables are missing")

                answer = ask_gemini(text)
                send_message(sender_id, answer)

            except Exception as error:
                # Keep secrets out of logs
                app.logger.error(
                    "Message processing failed: %s",
                    type(error).__name__,
                )

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
