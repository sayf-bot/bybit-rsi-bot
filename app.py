import os
import time
from decimal import Decimal, ROUND_DOWN
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
def get_filled_btc_qty(order_id):
    history = session.get_order_history(
        category="spot",
        symbol="BTCUSDC",
        orderId=order_id
    )

    orders = history.get("result", {}).get("list", [])

    if not orders:
        raise Exception("Buy order not found")

    order = orders[0]

    if order.get("orderStatus") != "Filled":
        raise Exception(f"Buy order is not filled: {order.get('orderStatus')}")

    qty = Decimal(order.get("cumExecQty", "0"))

    fee_detail = order.get("cumFeeDetail", {}) or {}
    btc_fee = Decimal(fee_detail.get("BTC", "0"))

    net_qty = qty - btc_fee

    if net_qty <= 0:
        raise Exception("Net BTC quantity is zero")
    step = Decimal("0.000001")
    net_qty = net_qty.quantize(step, rounding=ROUND_DOWN)
    return format(net_qty, "f")
def get_latest_bot_buy_order_id():
    history = session.get_order_history(
        category="spot",
        symbol="BTCUSDC",
        limit=50
    )
    
    orders = history.get("result", {}).get("list", [])
    
    bot_buys = [
        order for order in orders
        if order.get("side") == "Buy"
        and order.get("orderStatus") == "Filled"
        and str(order.get("orderLinkId", "")).startswith("rsi-buy-")
    ]
    
    if bot_buys:
        bot_buys.sort(
            key=lambda order: int(order.get("createdTime", "0")),
            reverse=True
        )
        return bot_buys[0].get("orderId")
    
    if INITIAL_BUY_ORDER_ID:
        return INITIAL_BUY_ORDER_ID
    
    raise Exception("No bot buy order found")
def is_buy_sold(buy_order_id):
    sell_link_id = f"rsi-sell-{buy_order_id}"

    history = session.get_order_history(
        category="spot",
        symbol="BTCUSDC",
        orderLinkId=sell_link_id,
        limit=1
    )

    orders = history.get("result", {}).get("list", [])

    return any(
        order.get("orderStatus") == "Filled"
        for order in orders
    )
@app.get("/check-position")
def check_position():
    try:
        buy_order_id = get_latest_bot_buy_order_id()
        sold = is_buy_sold(buy_order_id)

        return jsonify({
            "status": "ok",
            "buyOrderId": buy_order_id,
            "sold": sold
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
@app.get("/check-initial-buy")
def check_initial_buy():
    try:
        qty = get_filled_btc_qty(INITIAL_BUY_ORDER_ID)

        return jsonify({
            "status": "ok",
            "orderId": INITIAL_BUY_ORDER_ID,
            "netBtcQty": qty
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
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
            "basePrecision": lot.get("basePrecision"),
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
            buy_order_id = get_latest_bot_buy_order_id()

            if buy_order_id and not is_buy_sold(buy_order_id):
                return jsonify({
                    "status": "ok",
                    "action": "BUY",
                    "trading": "skipped_existing_position"
                }), 200
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
        try:
            buy_order_id = get_latest_bot_buy_order_id()
            if is_buy_sold(buy_order_id):
                return jsonify({
                    "status": "ok",
                    "action": "SELL",
                    "trading": "skipped_already_sold"
                }), 200
            sell_link_id = f"rsi-sell-{buy_order_id}"
            qty = get_filled_btc_qty(buy_order_id)
    
            order = session.place_order(
                category="spot",
                symbol="BTCUSDC",
                side="Sell",
                orderType="Market",
                qty=qty,
                marketUnit="baseCoin",
                orderLinkId=sell_link_id
            )
    
            return jsonify({
                "status": "ok",
                "action": "SELL",
                "trading": "enabled",
                "qty": qty,
                "retMsg": order.get("retMsg"),
                "orderId": order.get("result", {}).get("orderId")
            }), 200
    
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500
