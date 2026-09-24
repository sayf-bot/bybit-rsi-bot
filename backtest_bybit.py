import time
import requests
from datetime import datetime, timedelta, timezone


# ============================================================
# НАСТРОЙКИ
# ============================================================

SYMBOL = "BTCUSDC"
INTERVAL = "1m"

DAYS = 365

START_CAPITAL = 1000.0
ORDER_USDC = 50.0

# 0.1% на каждую сторону
COMMISSION = 0.001

RSI_PERIOD = 14

# Диапазоны поиска
BUY_RSI_VALUES = range(20, 36, 2)        # 20,22,...34
EXIT_RSI_VALUES = range(70, 91, 5)       # 70,75,80,85,90

TAKE_PROFIT_VALUES = [
    0.005,   # 0.5%
    0.010,   # 1.0%
    0.015,   # 1.5%
    0.020,   # 2.0%
    0.025,   # 2.5%
    0.030    # 3.0%
]

STOP_LOSS_VALUES = [
    0.005,   # 0.5%
    0.010,   # 1.0%
    0.015,   # 1.5%
    0.020    # 2.0%
]

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"


# ============================================================
# ЗАГРУЗКА ДАННЫХ
# ============================================================

def download_candles():
    print()
    print("=" * 90)
    print(f"ЗАГРУЗКА {DAYS} ДНЕЙ {SYMBOL} {INTERVAL}")
    print("=" * 90)

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=DAYS)

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    candles = []
    current_start = start_ms

    session = requests.Session()

    while current_start < end_ms:

        params = {
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": 1000
        }

        rows = None

        for attempt in range(5):

            try:
                response = session.get(
                    BINANCE_URL,
                    params=params,
                    timeout=20
                )

                if response.status_code == 200:
                    rows = response.json()
                    break

                print(
                    f"\nHTTP {response.status_code}, "
                    f"попытка {attempt + 1}/5"
                )

            except Exception as e:
                print(
                    f"\nОшибка соединения: {e}, "
                    f"попытка {attempt + 1}/5"
                )

            time.sleep(2)

        if rows is None:
            print("\nНе удалось получить данные.")
            return []

        if not rows:
            break

        for row in rows:
            candles.append({
                "time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5])
            })

        current_start = int(rows[-1][0]) + 60_000

        print(
            f"Загружено свечей: {len(candles):,}",
            end="\r"
        )

        time.sleep(0.08)

        if len(rows) < 1000:
            break

    print()
    print(f"Всего свечей: {len(candles):,}")

    if candles:

        first_date = datetime.fromtimestamp(
            candles[0]["time"] / 1000,
            tz=timezone.utc
        )

        last_date = datetime.fromtimestamp(
            candles[-1]["time"] / 1000,
            tz=timezone.utc
        )

        print(f"Начало: {first_date}")
        print(f"Конец:   {last_date}")

    return candles


# ============================================================
# RSI WILDER
# ============================================================

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

        avg_gain = (
            (avg_gain * (period - 1)) + gain
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + loss
        ) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))

    return rsi


# ============================================================
# ОДИН БЭКТЕСТ
# ============================================================

def run_backtest(
    data,
    buy_level,
    exit_rsi_level,
    take_profit_pct,
    stop_loss_pct
):

    closes = [x["close"] for x in data]

    rsi_values = calculate_rsi(
        closes,
        RSI_PERIOD
    )

    cash = START_CAPITAL
    btc = 0.0

    entry_price = None
    entry_total_cost = None

    trades = []

    total_fees = 0.0

    peak_equity = START_CAPITAL
    max_drawdown = 0.0
    max_drawdown_percent = 0.0

    tp_hits = 0
    sl_hits = 0
    rsi_exits = 0

    for i in range(
        RSI_PERIOD + 1,
        len(data) - 1
    ):

        previous_rsi = rsi_values[i - 1]
        current_rsi = rsi_values[i]

        if (
            previous_rsi is None
            or current_rsi is None
        ):
            continue

        candle = data[i]

        current_close = candle["close"]
        current_high = candle["high"]
        current_low = candle["low"]

        next_open = data[i + 1]["open"]

        # ====================================================
        # BUY SIGNAL
        # ====================================================

        buy_signal = (
            previous_rsi <= buy_level
            and current_rsi > buy_level
        )

        if (
            btc == 0
            and buy_signal
            and cash >= ORDER_USDC
        ):

            buy_fee = ORDER_USDC * COMMISSION

            usable_usdc = (
                ORDER_USDC - buy_fee
            )

            btc = usable_usdc / next_open

            entry_price = next_open
            entry_total_cost = ORDER_USDC

            cash -= ORDER_USDC
            total_fees += buy_fee

            continue

        # ====================================================
        # ЕСЛИ ПОЗИЦИЯ ОТКРЫТА
        # ====================================================

        if btc > 0:

            take_profit_price = (
                entry_price
                * (1 + take_profit_pct)
            )

            stop_loss_price = (
                entry_price
                * (1 - stop_loss_pct)
            )

            exit_price = None
            exit_reason = None

            # ------------------------------------------------
            # Сначала проверяем SL и TP внутри свечи
            #
            # Если в одной и той же свече были задеты
            # и TP, и SL, выбираем худший вариант: SL.
            # Это более консервативный тест.
            # ------------------------------------------------

            sl_touched = (
                current_low <= stop_loss_price
            )

            tp_touched = (
                current_high >= take_profit_price
            )

            if sl_touched and tp_touched:

                exit_price = stop_loss_price
                exit_reason = "SL"

            elif sl_touched:

                exit_price = stop_loss_price
                exit_reason = "SL"

            elif tp_touched:

                exit_price = take_profit_price
                exit_reason = "TP"

            else:

                # RSI exit:
                # пересечение сверху вниз
                rsi_exit_signal = (
                    previous_rsi >= exit_rsi_level
                    and current_rsi < exit_rsi_level
                )

                if rsi_exit_signal:
                    exit_price = next_open
                    exit_reason = "RSI"

            # =================================================
            # ЗАКРЫТИЕ
            # =================================================

            if exit_price is not None:

                gross_value = (
                    btc * exit_price
                )

                sell_fee = (
                    gross_value * COMMISSION
                )

                received = (
                    gross_value - sell_fee
                )

                cash += received

                pnl = (
                    received - entry_total_cost
                )

                trades.append(pnl)

                total_fees += sell_fee

                if exit_reason == "TP":
                    tp_hits += 1

                elif exit_reason == "SL":
                    sl_hits += 1

                elif exit_reason == "RSI":
                    rsi_exits += 1

                btc = 0.0
                entry_price = None
                entry_total_cost = None

        # ====================================================
        # EQUITY / DRAWDOWN
        # ====================================================

        equity = (
            cash
            + btc * current_close
        )

        if equity > peak_equity:
            peak_equity = equity

        drawdown = (
            peak_equity - equity
        )

        if drawdown > max_drawdown:
            max_drawdown = drawdown

        if peak_equity > 0:

            dd_percent = (
                drawdown
                / peak_equity
                * 100
            )

            if (
                dd_percent
                > max_drawdown_percent
            ):
                max_drawdown_percent = (
                    dd_percent
                )

    # ========================================================
    # ФИНАЛЬНАЯ EQUITY
    # ========================================================

    last_price = data[-1]["close"]

    final_equity = (
        cash
        + btc * last_price
    )

    net_profit = (
        final_equity
        - START_CAPITAL
    )

    closed_trades = len(trades)

    winning_trades = sum(
        1 for x in trades
        if x > 0
    )

    losing_trades = sum(
        1 for x in trades
        if x < 0
    )

    gross_profit = sum(
        x for x in trades
        if x > 0
    )

    gross_loss = abs(
        sum(
            x for x in trades
            if x < 0
        )
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit / gross_loss
        )

    elif gross_profit > 0:

        profit_factor = float("inf")

    else:

        profit_factor = 0.0

    if closed_trades > 0:

        win_rate = (
            winning_trades
            / closed_trades
            * 100
        )

        average_trade = (
            sum(trades)
            / closed_trades
        )

    else:

        win_rate = 0.0
        average_trade = 0.0

    return {
        "buy": buy_level,
        "exit_rsi": exit_rsi_level,

        "tp": take_profit_pct,
        "sl": stop_loss_pct,

        "profit": net_profit,

        "trades": closed_trades,

        "wins": winning_trades,
        "losses": losing_trades,

        "win_rate": win_rate,

        "average_trade": average_trade,

        "gross_profit": gross_profit,
        "gross_loss": gross_loss,

        "profit_factor": profit_factor,

        "max_drawdown": max_drawdown,
        "max_drawdown_percent":
            max_drawdown_percent,

        "fees": total_fees,

        "tp_hits": tp_hits,
        "sl_hits": sl_hits,
        "rsi_exits": rsi_exits,

        "open_position": btc > 0
    }


# ============================================================
# ПЕЧАТЬ
# ============================================================

def print_result(result):

    pf = result["profit_factor"]

    if pf == float("inf"):
        pf_text = "INF"
    else:
        pf_text = f"{pf:.2f}"

    open_text = (
        "YES"
        if result["open_position"]
        else "NO"
    )

    print(
        f"BUY {result['buy']:>2} | "
        f"EXIT RSI {result['exit_rsi']:>2} | "
        f"TP {result['tp'] * 100:>4.1f}% | "
        f"SL {result['sl'] * 100:>4.1f}% | "
        f"Profit ${result['profit']:>8.2f} | "
        f"Trades {result['trades']:>4} | "
        f"W {result['wins']:>3} | "
        f"L {result['losses']:>3} | "
        f"Win {result['win_rate']:>6.2f}% | "
        f"Avg ${result['average_trade']:>6.2f} | "
        f"PF {pf_text:>6} | "
        f"DD% {result['max_drawdown_percent']:>6.2f} | "
        f"TP#{result['tp_hits']:>3} | "
        f"SL#{result['sl_hits']:>3} | "
        f"RSI#{result['rsi_exits']:>3} | "
        f"Open {open_text}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    data = download_candles()

    if len(data) < 5000:

        print()
        print("Недостаточно исторических данных.")

        return

    # ========================================================
    # TRAIN / TEST
    # ========================================================

    split_index = int(
        len(data) * 0.70
    )

    train_data = data[:split_index]
    test_data = data[split_index:]

    print()
    print("=" * 90)
    print("РАЗДЕЛЕНИЕ ДАННЫХ")
    print("=" * 90)

    print(
        f"TRAIN свечей: "
        f"{len(train_data):,}"
    )

    print(
        f"TEST свечей:  "
        f"{len(test_data):,}"
    )

    # ========================================================
    # TRAIN SEARCH
    # ========================================================

    print()
    print("=" * 90)
    print("ПОИСК КОМБИНАЦИЙ")
    print("=" * 90)

    train_results = []

    total = (
        len(BUY_RSI_VALUES)
        * len(EXIT_RSI_VALUES)
        * len(TAKE_PROFIT_VALUES)
        * len(STOP_LOSS_VALUES)
    )

    counter = 0

    for buy_level in BUY_RSI_VALUES:

        for exit_rsi_level in EXIT_RSI_VALUES:

            for tp in TAKE_PROFIT_VALUES:

                for sl in STOP_LOSS_VALUES:

                    counter += 1

                    result = run_backtest(
                        train_data,
                        buy_level,
                        exit_rsi_level,
                        tp,
                        sl
                    )

                    # Для 365 дней
                    # хотим хотя бы 20 закрытых сделок.
                    if result["trades"] >= 20:

                        train_results.append(
                            result
                        )

                    if counter % 50 == 0:

                        print(
                            f"Проверено "
                            f"{counter}/{total}",
                            end="\r"
                        )

    print()

    if not train_results:

        print(
            "Нет вариантов "
            "с достаточным количеством сделок."
        )

        return

    # ========================================================
    # TRAIN FILTER
    # ========================================================

    profitable_train = []

    for result in train_results:

        if (
            result["profit"] > 0
            and result["profit_factor"] > 1
            and result["max_drawdown_percent"] < 10
        ):

            profitable_train.append(
                result
            )

    if not profitable_train:

        print()
        print("=" * 120)
        print("РЕЗУЛЬТАТ")
        print("=" * 120)

        print(
            "На TRAIN не найдено "
            "ни одной прибыльной комбинации."
        )

        print(
            "Эту версию стратегии "
            "не стоит переносить в реального бота."
        )

        return

    # Не просто максимальная прибыль.
    # Сортируем по прибыли,
    # потом по PF,
    # потом по меньшей просадке.
    profitable_train.sort(
        key=lambda x: (
            x["profit"],
            x["profit_factor"],
            -x["max_drawdown_percent"]
        ),
        reverse=True
    )

    top_train = profitable_train[:40]

    print()
    print("=" * 130)
    print("ТОП-15 НА TRAIN")
    print("=" * 130)

    for result in top_train[:15]:
        print_result(result)

    # ========================================================
    # TEST
    # ========================================================

    test_pairs = []

    for train_result in top_train:

        test_result = run_backtest(
            test_data,
            train_result["buy"],
            train_result["exit_rsi"],
            train_result["tp"],
            train_result["sl"]
        )

        test_pairs.append({
            "train": train_result,
            "test": test_result
        })

    # ========================================================
    # ROBUST FILTER
    # ========================================================

    robust = []

    for pair in test_pairs:

        train = pair["train"]
        test = pair["test"]

        if (
            train["profit"] > 0
            and test["profit"] > 0

            and train["profit_factor"] > 1
            and test["profit_factor"] > 1

            and train["trades"] >= 20
            and test["trades"] >= 10

            and train["max_drawdown_percent"] < 10
            and test["max_drawdown_percent"] < 10
        ):

            robust.append(pair)

    robust.sort(
        key=lambda pair: (
            pair["test"]["profit"],
            pair["test"]["profit_factor"],
            -pair["test"]["max_drawdown_percent"]
        ),
        reverse=True
    )

    # ========================================================
    # TEST OUTPUT
    # ========================================================

    print()
    print("=" * 130)
    print("РЕЗУЛЬТАТЫ НА НЕВИДАННЫХ TEST-ДАННЫХ")
    print("=" * 130)

    test_pairs.sort(
        key=lambda pair: (
            pair["test"]["profit"],
            pair["test"]["profit_factor"],
            -pair["test"]["max_drawdown_percent"]
        ),
        reverse=True
    )

    for pair in test_pairs[:15]:

        print_result(
            pair["test"]
        )

    # ========================================================
    # ROBUST OUTPUT
    # ========================================================

    print()
    print("=" * 130)
    print("УСТОЙЧИВЫЕ КАНДИДАТЫ")
    print("=" * 130)

    if not robust:

        print(
            "Устойчивых вариантов "
            "на TRAIN + TEST пока не найдено."
        )

    else:

        for index, pair in enumerate(
            robust[:10],
            start=1
        ):

            print()
            print(
                f"КАНДИДАТ #{index}"
            )

            print("TRAIN:")
            print_result(
                pair["train"]
            )

            print("TEST:")
            print_result(
                pair["test"]
            )

    print()
    print("=" * 130)
    print("ВАЖНО")
    print("=" * 130)

    print(
        "TP и SL проверяются по High/Low свечи."
    )

    print(
        "Если TP и SL коснулись в одной свече, "
        "бэктест считает, что первым сработал SL."
    )

    print(
        "Это специально консервативное допущение."
    )

    print(
        "Комиссия учитывается "
        "и на покупке, и на продаже."
    )

    print(
        "Сначала смотрим на результат TEST, "
        "Profit Factor, просадку "
        "и количество сделок."
    )

    print(
        "Даже хороший исторический результат "
        "не гарантирует будущую прибыль."
    )


if __name__ == "__main__":
    main()
