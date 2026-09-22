import os
import time
import requests
from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET", "")
ORDER_USDC = os.environ.get("ORDER_USDC", "50")
INITIAL_BUY_ORDER_ID = os.environ.get("INITIAL_BUY_ORDER_ID", "")
TRADING_ENABLED = os.environ.get("TRADING_ENABLED", "false").lower() == "true"
# Основной Bybit — НЕ testnet
session = HTTP(
    testnet=False,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

@app.get("/check-ip")
def check_ip():
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=10)
        return jsonify(response.json()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.get("/")
def home():
    return "Bybit RSI Bot is running", 200
@app.get("/check-bybit")
def check_bybit():
    try:
        balance = session.get_wallet_balance(accountType="UNIFIED")
        return jsonify({
            "status": "ok",
            "bybit": "connected",
            "retMsg": balance.get("retMsg")
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.get("/check-btcusdc")
def check_btcusdc():
    try:
        info = session.get_instruments_info(
            category="spot",
            symbol="BTCUSDC"
        )

        instrument = info.get("result", {}).get("list", [])[0]
        lot = instrument.get("lotSizeFilter", {})

        return jsonify({
            "status": "ok",
            "symbol": instrument.get("symbol"),
            "minOrderAmt": lot.get("minOrderAmt"),
            "minOrderQty": lot.get("minOrderQty"),
            "quotePrecision": lot.get("quotePrecision")
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
@app.post("/webhook")
def webhook():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    if data.get("secret") != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    action = str(data.get("action", "")).upper()

    if action not in ("BUY", "SELL"):
        return jsonify({"error": "Unknown action"}), 400

    print(f"TradingView signal received: {action}", flush=True)

    # ВАЖНО: реальные сделки пока отключены
    if not TRADING_ENABLED:
        return jsonify({
            "status": "ok",
            "action": action,
            "trading": "disabled"
        }), 200
    if action == "BUY":
        try:
            order = session.place_order(
                category="spot",
                symbol="BTCUSDC",
                side="Buy",
                orderType="Market",
                qty=ORDER_USDC,
                marketUnit="quoteCoin",
                orderLinkId=f"rsi-buy-{int(time.time())}"
            )

            return jsonify({
                "status": "ok",
                "action": "BUY",
                "trading": "enabled",
                "retMsg": order.get("retMsg"),
                "orderId": order.get("result", {}).get("orderId")
            }), 200

        except Exception as e:
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500
    if action == "SELL":
        return jsonify({
            "status": "ok",
            "action": "SELL",
            "trading": "sell_not_configured"
        }), 200
