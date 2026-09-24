import time
import requests
from datetime import datetime, timedelta, timezone


# ============================================================
# НАСТРОЙКИ
# ============================================================

SYMBOL = "BTCUSDC"
INTERVAL = "1m"

# Тестируем 365 дней
DAYS = 365

START_CAPITAL = 1000.0

# Размер одной сделки
ORDER_USDC = 50.0

# Комиссия 0.1% на покупку и 0.1% на продажу
COMMISSION = 0.001

RSI_PERIOD = 14

# Диапазоны параметров, которые будем проверять
BUY_RSI_VALUES = range(15, 36)   # 15...35
SELL_RSI_VALUES = range(65, 91)  # 65...90

BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"


# ============================================================
# ЗАГРУЗКА СВЕЧЕЙ
# ============================================================

def download_candles():
    print()
    print("=" * 80)
    print(f"ЗАГРУЗКА {DAYS} ДНЕЙ {SYMBOL} {INTERVAL}")
    print("=" * 80)

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

        last_open_time = int(rows[-1][0])

        current_start = last_open_time + 60_000

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

        rsi[period] = (
            100 - (100 / (1 + rs))
        )

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

            rsi[i] = (
                100 - (100 / (1 + rs))
            )

    return rsi


# ============================================================
# ОДИН БЭКТЕСТ
# ============================================================

def run_backtest(data, buy_level, sell_level):

    closes = [
        candle["close"]
        for candle in data
    ]

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

        current_close = data[i]["close"]

        # Сигнал появился на закрытии текущей свечи.
        # Сделку считаем исполненной на открытии следующей.
        next_open = data[i + 1]["open"]

        # RSI пересёк BUY уровень снизу вверх
        buy_signal = (
            previous_rsi <= buy_level
            and current_rsi > buy_level
        )

        # RSI пересёк SELL уровень сверху вниз
        sell_signal = (
            previous_rsi >= sell_level
            and current_rsi < sell_level
        )

        # ====================================================
        # BUY
        # ====================================================

        if (
            btc == 0
            and buy_signal
            and cash >= ORDER_USDC
        ):

            buy_fee = (
                ORDER_USDC
                * COMMISSION
            )

            usable_usdc = (
                ORDER_USDC
                - buy_fee
            )

            btc = (
                usable_usdc
                / next_open
            )

            entry_price = next_open

            entry_total_cost = ORDER_USDC

            cash -= ORDER_USDC

            total_fees += buy_fee

        # ====================================================
        # SELL
        # ====================================================

        elif (
            btc > 0
            and sell_signal
        ):

            gross_value = (
                btc
                * next_open
            )

            sell_fee = (
                gross_value
                * COMMISSION
            )

            received = (
                gross_value
                - sell_fee
            )

            # ВАЖНО:
            # теперь закрываем сделку
            # независимо от того,
            # прибыль она дала или убыток.
            cash += received

            pnl = (
                received
                - entry_total_cost
            )

            trades.append(pnl)

            total_fees += sell_fee

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
            peak_equity
            - equity
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
    # ФИНАЛЬНАЯ СТОИМОСТЬ
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
        1
        for pnl in trades
        if pnl > 0
    )

    losing_trades = sum(
        1
        for pnl in trades
        if pnl < 0
    )

    breakeven_trades = sum(
        1
        for pnl in trades
        if pnl == 0
    )

    gross_profit = sum(
        pnl
        for pnl in trades
        if pnl > 0
    )

    gross_loss = abs(
        sum(
            pnl
            for pnl in trades
            if pnl < 0
        )
    )

    if gross_loss > 0:

        profit_factor = (
            gross_profit
            / gross_loss
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
        "sell": sell_level,

        "profit": net_profit,

        "trades": closed_trades,

        "wins": winning_trades,
        "losses": losing_trades,
        "breakeven": breakeven_trades,

        "win_rate": win_rate,

        "gross_profit": gross_profit,
        "gross_loss": gross_loss,

        "profit_factor": profit_factor,

        "max_drawdown": max_drawdown,
        "max_drawdown_percent":
            max_drawdown_percent,

        "average_trade": average_trade,

        "fees": total_fees,

        "open_position": btc > 0,

        "entry_price": entry_price
    }


# ============================================================
# ВЫВОД ОДНОЙ СТРОКИ
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
        f"BUY {result['buy']:>2}  "
        f"SELL {result['sell']:>2} | "
        f"Profit ${result['profit']:>8.2f} | "
        f"Trades {result['trades']:>4} | "
        f"W {result['wins']:>3} | "
        f"L {result['losses']:>3} | "
        f"Win {result['win_rate']:>6.2f}% | "
        f"Avg ${result['average_trade']:>6.2f} | "
        f"DD ${result['max_drawdown']:>7.2f} | "
        f"DD% {result['max_drawdown_percent']:>6.2f} | "
        f"PF {pf_text:>6} | "
        f"Fees ${result['fees']:>7.2f} | "
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
    print("=" * 80)
    print("РАЗДЕЛЕНИЕ ДАННЫХ")
    print("=" * 80)

    print(
        f"TRAIN свечей: "
        f"{len(train_data):,}"
    )

    print(
        f"TEST свечей:  "
        f"{len(test_data):,}"
    )

    # ========================================================
    # TRAIN
    # ========================================================

    print()
    print("=" * 80)
    print("ПРОВЕРЯЮ КОМБИНАЦИИ RSI")
    print("=" * 80)

    train_results = []

    total = (
        len(BUY_RSI_VALUES)
        * len(SELL_RSI_VALUES)
    )

    counter = 0

    for buy_level in BUY_RSI_VALUES:

        for sell_level in SELL_RSI_VALUES:

            counter += 1

            result = run_backtest(
                train_data,
                buy_level,
                sell_level
            )

            # Не рассматриваем совсем
            # редкие стратегии
            if result["trades"] >= 10:

                train_results.append(
                    result
                )

            if counter % 25 == 0:

                print(
                    f"Проверено "
                    f"{counter}/{total}",
                    end="\r"
                )

    print()

    if not train_results:

        print(
            "Не найдено вариантов "
            "с достаточным количеством сделок."
        )

        return

    # ========================================================
    # ФИЛЬТР TRAIN
    # ========================================================

    filtered_train = []

    for result in train_results:

        if (
            result["profit"] > 0
            and result["max_drawdown_percent"] < 10
            and result["profit_factor"] > 1
        ):

            filtered_train.append(
                result
            )

    if not filtered_train:

        print()
        print(
            "На TRAIN нет прибыльных "
            "вариантов по заданным условиям."
        )

        # Всё равно покажем лучшие,
        # чтобы понять общую картину.
        filtered_train = train_results

    filtered_train.sort(
        key=lambda x: (
            x["profit"],
            x["profit_factor"],
            -x["max_drawdown_percent"]
        ),
        reverse=True
    )

    top_train = filtered_train[:30]

    print()
    print("=" * 120)
    print("ТОП-15 НА TRAIN")
    print("=" * 120)

    for result in top_train[:15]:
        print_result(result)

    # ========================================================
    # TEST
    # ========================================================

    print()
    print("=" * 120)
    print("ПРОВЕРКА НА НЕВИДАННЫХ TEST-ДАННЫХ")
    print("=" * 120)

    test_results = []

    for candidate in top_train:

        result = run_backtest(
            test_data,
            candidate["buy"],
            candidate["sell"]
        )

        test_results.append(
            result
        )

    test_results.sort(
        key=lambda x: (
            x["profit"],
            x["profit_factor"],
            -x["max_drawdown_percent"]
        ),
        reverse=True
    )

    print()
    print("=" * 120)
    print("ТОП-15 РЕЗУЛЬТАТОВ НА TEST")
    print("=" * 120)

    for result in test_results[:15]:
        print_result(result)

    # ========================================================
    # УСТОЙЧИВЫЕ КАНДИДАТЫ
    # ========================================================

    robust = []

    for test_result in test_results:

        matching_train = None

        for train_result in train_results:

            if (
                train_result["buy"]
                == test_result["buy"]
                and
                train_result["sell"]
                == test_result["sell"]
            ):

                matching_train = train_result
                break

        if matching_train is None:
            continue

        # Требуем прибыль И на TRAIN,
        # И на TEST.
        if (
            matching_train["profit"] > 0
            and test_result["profit"] > 0

            and matching_train["profit_factor"] > 1
            and test_result["profit_factor"] > 1

            and test_result["trades"] >= 10

            and
            test_result["max_drawdown_percent"] < 10
        ):

            robust.append({
                "train": matching_train,
                "test": test_result
            })

    print()
    print("=" * 120)
    print("КАНДИДАТЫ ДЛЯ ДАЛЬНЕЙШЕЙ ПРОВЕРКИ")
    print("=" * 120)

    if not robust:

        print(
            "Устойчивых вариантов пока не найдено."
        )

    else:

        for item in robust[:10]:

            print()
            print("TRAIN:")

            print_result(
                item["train"]
            )

            print("TEST:")

            print_result(
                item["test"]
            )

    print()
    print("=" * 120)
    print("ВАЖНО")
    print("=" * 120)

    print(
        "Теперь убыточные сделки "
        "тоже закрываются и учитываются."
    )

    print(
        "Высокий процент побед сам по себе "
        "не означает хорошую стратегию."
    )

    print(
        "Особенно смотрим на TEST, "
        "Profit Factor, просадку "
        "и количество сделок."
    )

    print(
        "Это исторический тест, "
        "а не гарантия будущей прибыли."
    )

    print(
        "Используются данные Binance BTCUSDC."
    )

    print(
        "Перед реальной торговлей "
        "нужно отдельно проверить "
        "исполнение, проскальзывание "
        "и данные Bybit."
    )


if __name__ == "__main__":
    main()
