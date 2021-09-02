from colorama import init
import glob
import importlib
import threading
import sys
from datetime import datetime
from logging import DEBUG
import supertrend_ta as ta
import pandas as pd
import time
import ccxt
import requests
import warnings
import schedule
from binance.client import Client
import config
# use for environment variables
import os
# used to store trades and sell assets
import json
warnings.filterwarnings('ignore')

# use if needed to pass args to external modules

# used to create threads & dynamic loading of modules

# used for directory handling

# Needed for colorful console output Install with: python3 -m pip install colorama (Mac/Linux) or pip install colorama (PC)
init()

# for colourful logging to the console


class txcolors:
    BUY = '\033[92m'
    WARNING = '\033[93m'
    SELL_LOSS = '\033[91m'
    SELL_PROFIT = '\033[32m'
    DIM = '\033[2m\033[35m'
    DEFAULT = '\033[39m'


# tracks profit/loss each session
global session_profit
session_profit = 0
global dollar_profit
dollar_profit = 0

# print with timestamps
old_out = sys.stdout


class St_ampe_dOut:
    """Stamped stdout."""
    nl = True

    def write(self, x):
        """Write function overloaded."""
        if x == '\n':
            old_out.write(x)
            self.nl = True
        elif self.nl:
            old_out.write(
                f'{txcolors.DIM}[{str(datetime.now().replace(microsecond=0))}]{txcolors.DEFAULT} {x}')
            self.nl = False
        else:
            old_out.write(x)

    def flush(self):
        pass


sys.stdout = St_ampe_dOut()


# instantiate ccxt
exchange = ccxt.binance()
markets = exchange.load_markets()
# instantiate binance client
client = Client(config.API_KEY, config.API_SECRET)
# get the list of symbols:


def get_symbols():
    global PAIRS_WITH
    response = requests.get('https://api.binance.com/api/v3/ticker/price')
    PAIRS_WITH = 'USDT'
    ignore = ['UP', 'DOWN']
    symbols = []

    for symbol in response.json():
        if PAIRS_WITH in symbol['symbol'] and all(item not in symbol['symbol'] for item in ignore):
            if symbol['symbol'][-len(PAIRS_WITH):] == PAIRS_WITH:
                symbols.append(symbol['symbol'][:-len(PAIRS_WITH)])
            symbols.sort()
    return symbols


def check_symbols():
    symbols_to_buy = []
    last_price = {}
    symbols_to_sell = []
    global PAIRS_WITH
    print('fetching symbols')
    symbols = get_symbols()
    for symbol in symbols:
        try:
            bars = exchange.fetch_ohlcv(
                symbol+'/'+PAIRS_WITH, timeframe='5m', limit=50)
            df_temp = pd.DataFrame(
                bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_temp['Symbol'] = symbol
            df_temp['timestamp'] = pd.to_datetime(
                df_temp['timestamp'], unit='ms')
            df_temp = ta.supertrend(df_temp)
            df_temp = ta.check_trend_change(df_temp)
            df_temp = ta.sideways_trend(df_temp, 7)
            df_temp = ta.check_trend_direction(df_temp)

            symbol += PAIRS_WITH
            last_price[symbol] = df_temp['close'].iloc[-1]
            if df_temp['instruction'].iloc[-1] == 'buy':
                symbols_to_buy.append(symbol)
            if df_temp['instruction'].iloc[-1] == 'sell':
                symbols_to_sell.append(symbol)
        except Exception as e:
            print('{} - {}'.format(symbol, e))
    print('collected all symbols')
    return symbols_to_buy, last_price, symbols_to_sell


def convert_volume(volatile_coins, last_price):
    '''Converts the volume given in QUANTITY from USDT to the each coin's volume'''

    lot_size = {}
    volume = {}

    for coin in volatile_coins:

        # Find the correct step size for each coin
        # max accuracy for BTC for example is 6 decimal points
        # while XRP is only 1
        try:
            info = client.get_symbol_info(coin)
            step_size = info['filters'][2]['stepSize']
            lot_size[coin] = step_size.index('1') - 1

            if lot_size[coin] < 0:
                lot_size[coin] = 0

        except:
            pass

        # calculate the volume in coin from QUANTITY in USDT (default)
        volume[coin] = float(QUANTITY / float(last_price[coin]))

        # define the volume with the correct step size
        if coin not in lot_size:
            volume[coin] = float('{:.1f}'.format(volume[coin]))

        else:
            # if lot size has 0 decimal points, make the volume an integer
            if lot_size[coin] == 0:
                volume[coin] = int(volume[coin])
            else:
                volume[coin] = float('{:.{}f}'.format(
                    volume[coin], lot_size[coin]))

    return volume, last_price


def buy(volume, last_price):
    '''Place Buy market orders for each volatile coin found'''

    orders = {}

    for coin in volume:

        # only buy if the there are no active trades on the coin
        if coin not in coins_bought:
            print(
                f"{txcolors.BUY}Preparing to buy {volume[coin]} {coin}{txcolors.DEFAULT}")

            if TEST_MODE:
                orders[coin] = [{
                    'symbol': coin,
                    'orderId': 0,
                    'time': datetime.now().timestamp()
                }]

                # Log trade
                if LOG_TRADES:
                    write_log(
                        f"Buy : {volume[coin]} {coin} - {last_price[coin]}")

                continue

            # try to create a real order if the test orders did not raise an exception
            try:
                buy_limit = client.create_order(
                    symbol=coin,
                    side='BUY',
                    type='MARKET',
                    quantity=volume[coin]
                )

            # error handling here in case position cannot be placed
            except Exception as e:
                print(e)

            # run the else block if the position has been placed and return order info
            else:
                orders[coin] = client.get_all_orders(symbol=coin, limit=1)

                # binance sometimes returns an empty list, the code will wait here until binance returns the order
                while orders[coin] == []:
                    print(
                        'Binance is being slow in returning the order, calling the API again...')

                    orders[coin] = client.get_all_orders(symbol=coin, limit=1)
                    time.sleep(1)

                else:
                    print('Order returned, saving order to file')

                    # Log trade
                    if LOG_TRADES:
                        write_log(
                            f"Buy : {volume[coin]} {coin} - {last_price[coin]}")

        else:
            print(
                f'Signal detected, but there is already an active trade on {coin}')

    return orders, last_price, volume


def sell_coins(to_sell, last_price):
    '''sell coins that have reached the STOP LOSS or TAKE PROFIT threshold'''
    global session_profit
    global dollar_profit
    coins_sold = {}

    for coin in list(to_sell):
        if coin in coins_bought:

            LastPrice = float(last_price[coin])
            BuyPrice = float(coins_bought[coin]['bought_at'])
            PriceChange = float((LastPrice - BuyPrice) / BuyPrice * 100)

            print(
                f"{txcolors.SELL_PROFIT if PriceChange >= 0. else txcolors.SELL_LOSS}Selling {coins_bought[coin]['volume']} {coin} - {BuyPrice} - {LastPrice} : {PriceChange:.2f}%{txcolors.DEFAULT}")

            # try to create a real order
            try:

                if not TEST_MODE:
                    sell_coins_limit = client.create_order(
                        symbol=coin,
                        side='SELL',
                        type='MARKET',
                        quantity=coins_bought[coin]['volume']

                    )

            # error handling here in case position cannot be placed
            except Exception as e:
                print(e)

            # run the else block if coin has been sold and create a dict for each coin sold
            else:
                coins_sold[coin] = coins_bought[coin]
                # Log trade

                if LOG_TRADES:
                    profit = (LastPrice - BuyPrice) * \
                        coins_sold[coin]['volume']
                    write_log(
                        f"Sell: {coins_sold[coin]['volume']} {coin} - {BuyPrice} - {LastPrice} Profit: {profit:.2f} {PriceChange:.2f}%")
                    session_profit = session_profit + PriceChange
                    dollar_profit = dollar_profit + profit
            continue

    return coins_sold


def update_portfolio(orders, last_price, volume):
    '''add every coin bought to our portfolio for tracking/selling later'''
    if DEBUG:
        print(orders)
    for coin in orders:

        coins_bought[coin] = {
            'symbol': orders[coin][0]['symbol'],
            'orderid': orders[coin][0]['orderId'],
            'timestamp': orders[coin][0]['time'],
            'bought_at': last_price[coin],
            'volume': volume[coin],
        }

        # save the coins in a json file in the same directory
        with open(coins_bought_file_path, 'w') as file:
            json.dump(coins_bought, file, indent=4)

        print(
            f'Order with id {orders[coin][0]["orderId"]} placed and saved to file')


def remove_from_portfolio(coins_sold):
    '''Remove coins sold due to SL or TP from portfolio'''
    for coin in coins_sold:
        coins_bought.pop(coin)

    with open(coins_bought_file_path, 'w') as file:
        json.dump(coins_bought, file, indent=4)


def write_log(logline):
    timestamp = datetime.now().strftime("%d/%m %H:%M:%S")
    with open(LOG_FILE, 'a+') as f:
        f.write(timestamp + ' ' + logline + '\n')


def run_bot():
    symbols_to_buy, last_price, symbols_to_sell = check_symbols()
    print('to buy:')
    print(symbols_to_buy)
    print('to sell:')
    print(symbols_to_sell)
    # print('last_price')
    # print(last_price)
    symbol_volume, last_price = convert_volume(symbols_to_buy, last_price)
    orders, last_price, symbol_volume = buy(symbol_volume, last_price)
    update_portfolio(orders, last_price, symbol_volume)
    coins_sold = sell_coins(symbols_to_sell, last_price)
    remove_from_portfolio(coins_sold)
    print("sleeping until the loop starts again (3 minutes)")
    print(f'Current session P/L %:{session_profit:.2f}%')
    print(f'Current session P/L usd: ${dollar_profit:.2f}')


if __name__ == '__main__':

    TEST_MODE = True
    LOG_TRADES = True
    LOG_FILE = 'trades.txt'

    # prevent including a coin in volatile_coins if it has already appeared there less than TIME_DIFFERENCE minutes ago
    volatility_cooloff = {}

    # amount of coin to buy in USD
    QUANTITY = 50

    DEBUG = False

    # try to load all the coins bought by the bot if the file exists and is not empty
    coins_bought = {}

    # path to the saved coins_bought file
    coins_bought_file_path = 'coins_bought.json'

    # use separate files for testing and live trading
    if TEST_MODE:
        coins_bought_file_path = 'test_' + coins_bought_file_path

    # if saved coins_bought json file exists and it's not empty then load it
    if os.path.isfile(coins_bought_file_path) and os.stat(coins_bought_file_path).st_size != 0:
        with open(coins_bought_file_path) as file:
            coins_bought = json.load(file)

    if not TEST_MODE:
        print('WARNING: You are using the Mainnet and live funds. Waiting 10 seconds as a security measure')
        time.sleep(10)
    else:
        print('You are in TEST MODE, no funds are being used.')

    # # Schedule will wait the time period before starting, so do a run first before calling it.
    run_bot()
    schedule.every(3).minutes.do(run_bot)

    while True:
        schedule.run_pending()
        time.sleep(1)
