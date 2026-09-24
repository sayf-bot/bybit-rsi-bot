import time
from datetime import datetime, timedelta, timezone
from pybit.unified_trading import HTTP

# =========================
# НАСТРОЙКИ ТЕСТА
# =========================

SYMBOL = "BTCUSDC"
CATEGORY = "spot"
INTERVAL = "1"

# Сначала тестируем 90 дней.
# Потом увеличим до 180/365.
DAYS = 90

START_CAPITAL = 1000.0
ORDER_USDC = 50.0

# Комиссия 0.1% на покупку и продажу
COMMISSION = 0.001

RSI_PERIOD = 14

# Диапазон параметров, которые будем проверять
BUY_RSI_VALUES = range(15, 36)      # 15 ... 35
SELL_RSI_VALUES = range(65, 91)     # 65 ... 90


session = HTTP(testnet=False)


# =========================
# ЗАГРУЗКА СВЕЧЕЙ BYBIT
# =========================

def download_candles():
    print(f"Загружаю {DAYS} дней {SYMBOL} 1m с Bybit...")

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=DAYS)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    candles = []

    current_end = end_ms

    while current_end > start_ms:
        result = session.get_kline(
            category=CATEGORY,
            symbol=SYMBOL,
            interval=INTERVAL,
            start=start_ms,
            end=current_end,
            limit=1000
        )

        rows = result.get("result", {}).get("list", [])

        if not rows:
            break

        candles.extend(rows)

        oldest = min(int(row[0]) for row in rows)

        if oldest <= start_ms:
            break

        current_end = oldest - 1

        print(f"Загружено свечей: {len(candles)}", end="\r")

        time.sleep(0.08)

    # Bybit возвращает данные от новых к старым
    unique = {}

    for row in candles:
        ts = int(row[0])

        if ts >= start_ms:
            unique[ts] = row

    ordered = [unique[k] for k in sorted(unique)]

    data = []

    for row in ordered:
        data.append({
            "time": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4])
        })

    print()
    print(f"Готово. Свечей: {len(data)}")

    return data


# =========================
# RSI
# =========================

def calculate_rsi(closes, period=14):
    rsi = [None] * len(closes)

    if len(closes) <= period:
        return rsi

    gains = []
    losses = []

    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]

        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]

        gain = max(change, 0)
        loss = max(-change, 0)

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))

    return rsi


# =========================
# ОДИН БЭКТЕСТ
# =========================

def run_backtest(data, rsi_values, buy_level, sell_level):
    cash = START_CAPITAL

    btc = 0.0
    entry_price = None
    entry_cost = None

    trades = []

    peak_equity = START_CAPITAL
    max_drawdown = 0.0

    for i in range(RSI_PERIOD + 1, len(data) - 1):

        current_rsi = rsi_values[i]
        previous_rsi = rsi_values[i - 1]

        if current_rsi is None or previous_rsi is None:
            continue

        current_close = data[i]["close"]

        # Исполнение на открытии следующей свечи
        next_open = data[i + 1]["open"]

        # BUY: RSI пересёк уровень снизу вверх
        buy_signal = (
            previous_rsi <= buy_level
            and current_rsi > buy_level
        )

        # SELL: RSI пересёк уровень сверху вниз
        sell_signal = (
            previous_rsi >= sell_level
            and current_rsi < sell_level
        )

        if btc == 0 and buy_signal and cash >= ORDER_USDC:

            buy_fee = ORDER_USDC * COMMISSION
            usable_usdc = ORDER_USDC - buy_fee

            btc = usable_usdc / next_open
            entry_price = next_open
            entry_cost = ORDER_USDC

            cash -= ORDER_USDC

        elif btc > 0 and sell_signal:

            # Продаём только если цена выше цены покупки
            if current_close > entry_price:

                gross_value = btc * next_open
                sell_fee = gross_value * COMMISSION
                received = gross_value - sell_fee

                cash += received

                pnl = received - entry_cost

                trades.append(pnl)

                btc = 0.0
                entry_price = None
                entry_cost = None

        # Equity с учётом открытой BTC позиции
        equity = cash + (btc * current_close)

        if equity > peak_equity:
            peak_equity = equity

        drawdown = peak_equity - equity

        if drawdown > max_drawdown:
            max_drawdown = drawdown

    # Открытая позиция оценивается по последней цене,
    # чтобы убыток нельзя было "спрятать".
    last_price = data[-1]["close"]

    final_equity = cash + (btc * last_price)

    net_profit = final_equity - START_CAPITAL

    winning = sum(1 for x in trades if x > 0)
    losing = sum(1 for x in trades if x < 0)

    gross_profit = sum(x for x in trades if x > 0)
    gross_loss = abs(sum(x for x in trades if x < 0))

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    win_rate = (
        winning / len(trades) * 100
        if trades
        else 0
    )

    return {
        "buy": buy_level,
        "sell": sell_level,
        "profit": net_profit,
        "trades": len(trades),
        "win_rate": win_rate,
        "max_drawdown": max_drawdown,
        "profit_factor": profit_factor,
        "open_position": btc > 0
    }


# =========================
# ПОИСК ПАРАМЕТРОВ
# =========================

def main():
    data = download_candles()

    if len(data) < 1000:
        print("Недостаточно данных.")
        return

    closes = [x["close"] for x in data]
    rsi_values = calculate_rsi(closes, RSI_PERIOD)

    # 70% истории для подбора
    split = int(len(data) * 0.70)

    train_data = data[:split]
    train_rsi = rsi_values[:split]

    # 30% истории — отдельная проверка
    test_data = data[split - RSI_PERIOD - 2:]
    test_rsi = rsi_values[split - RSI_PERIOD - 2:]

    candidates = []

    print()
    print("Проверяю комбинации RSI...")

    total = len(BUY_RSI_VALUES) * len(SELL_RSI_VALUES)
    count = 0

    for buy_level in BUY_RSI_VALUES:

        for sell_level in SELL_RSI_VALUES:

            count += 1

            train = run_backtest(
                train_data,
                train_rsi,
                buy_level,
                sell_level
            )

            # Не рассматриваем варианты,
            # где почти нет сделок
            if train["trades"] < 10:
                continue

            candidates.append(train)

            if count % 50 == 0:
                print(f"Проверено {count}/{total}")

    # Сначала отбираем хорошие результаты
    # на тренировочной части
    candidates.sort(
        key=lambda x: (
            x["profit"],
            -x["max_drawdown"]
        ),
        reverse=True
    )

    top_train = candidates[:30]

    final_results = []

    # Теперь эти варианты проверяем
    # на данных, которые не использовали для подбора
    for candidate in top_train:

        test = run_backtest(
            test_data,
            test_rsi,
            candidate["buy"],
            candidate["sell"]
        )

        final_results.append({
            "buy": candidate["buy"],
            "sell": candidate["sell"],

            "train_profit": candidate["profit"],
            "train_trades": candidate["trades"],
            "train_dd": candidate["max_drawdown"],

            "test_profit": test["profit"],
            "test_trades": test["trades"],
            "test_win_rate": test["win_rate"],
            "test_dd": test["max_drawdown"],
            "test_pf": test["profit_factor"],
            "open_position": test["open_position"]
        })

    # Приоритет: положительный результат
    # на НЕВИДАННЫХ данных
    final_results.sort(
        key=lambda x: (
            x["test_profit"],
            -x["test_dd"]
        ),
        reverse=True
    )

    print()
    print("=" * 90)
    print("ТОП РЕЗУЛЬТАТОВ НА ОТДЕЛЬНОЙ ТЕСТОВОЙ ЧАСТИ")
    print("=" * 90)

    print(
        f"{'BUY':>5} "
        f"{'SELL':>5} "
        f"{'TEST $':>10} "
        f"{'TRADES':>8} "
        f"{'WIN %':>8} "
        f"{'DD $':>10} "
        f"{'PF':>8} "
        f"{'OPEN':>7}"
    )

    for result in final_results[:15]:

        print(
            f"{result['buy']:>5} "
            f"{result['sell']:>5} "
            f"{result['test_profit']:>10.2f} "
            f"{result['test_trades']:>8} "
            f"{result['test_win_rate']:>8.2f} "
            f"{result['test_dd']:>10.2f} "
            f"{result['test_pf']:>8.2f} "
            f"{str(result['open_position']):>7}"
        )

    print()
    print("Важно:")
    print("Это исторический тест, а не гарантия будущей прибыли.")
    print("Особенно смотрим на TEST $, DD $, количество сделок и OPEN.")


if __name__ == "__main__":
    main()
