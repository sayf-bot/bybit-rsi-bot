import os
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


@app.get("/")
def home():
    return "Bybit RSI Bot is running", 200


@app.post("/webhook")
def webhook():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Защита webhook от посторонних запросов
    if data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    action = str(data.get("action", "")).upper()

    if action not in ("BUY", "SELL"):
        return jsonify({"error": "Unknown action"}), 400

    # Пока никаких реальных сделок.
    # Сначала проверяем связь TradingView -> Render.
    print(f"TradingView signal received: {action}", flush=True)

    return jsonify({
        "status": "ok",
        "action": action,
        "trading": "disabled"
    }), 200
