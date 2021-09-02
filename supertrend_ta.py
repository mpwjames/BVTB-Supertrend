import pandas as pd
import numpy as np


def true_range(df):
    df['previous_close'] = df['close'].shift(1)
    df['high-low'] = df['high'] - df['low']
    df['high-pc'] = abs(df['high'] - df['previous_close'])
    df['low-pc'] = abs(df['low'] - df['previous_close'])
    tr = df[['high-low', 'high-pc', 'low-pc']].max(axis=1)
    return tr


def absolute_true_range(df, period=7):
    df['tr'] = true_range(df)
    the_atr = df['tr'].rolling(period).mean()
    return the_atr


def supertrend(df, period=7, multiplier=3.5):

    df['atr'] = absolute_true_range(df, period=period)
    df['upperband'] = ((df['high'] + df['low']) /
                       2) + (multiplier * df['atr'])
    df['lowerband'] = ((df['high'] + df['low']) /
                       2) - (multiplier * df['atr'])
    df['in_uptrend'] = True

    for current in range(1, len(df.index)):
        previous = current - 1
        if df['close'][current] > df['upperband'][previous]:
            df['in_uptrend'][current] = True
        elif df['close'][current] < df['lowerband'][previous]:
            df['in_uptrend'][current] = False
        else:
            df['in_uptrend'][current] = df['in_uptrend'][previous]

            if df['in_uptrend'][current] and df['lowerband'][current] < df['lowerband'][previous]:
                df['lowerband'][current] = df['lowerband'][previous]

            if not df['in_uptrend'][current] and df['upperband'][current] > df['upperband'][previous]:
                df['upperband'][current] = df['upperband'][previous]
    return df


def check_trend_change(df):
    last_row_index = len(df.index) - 1
    previous_row_index = last_row_index - 1

    if not df['in_uptrend'][previous_row_index] and df['in_uptrend'][last_row_index]:
        df['ST_instruction'] = 'buy'
    elif df['in_uptrend'][previous_row_index] and not df['in_uptrend'][last_row_index]:
        df['ST_instruction'] = 'sell'
    else:
        df['ST_instruction'] = 'wait'
    return df


def check_trend_direction(df):
    df['direction'] = "unknown"
    df['instruction'] = 'unknown'
    for current in range(1, len(df.index)):
        previous = current - 1
        if df['in_uptrend'][previous] and df['sideways'][previous] == 0 and df['sideways'][current] == 1:
            df['direction'][current] = "sideways"
            df['instruction'][current] = "sell"

        if (df['in_uptrend'][previous] == True) & (df['sideways'][previous] == 0) & (df['in_uptrend'][current] == False) & (df['sideways'][current] == 0):
            df['direction'][current] = "downwards"
            df['instruction'][current] = "sell"

        if (df['sideways'][previous] == 1) & (df['in_uptrend'][current] == True) & (df['sideways'][current] == 0):
            df['direction'][current] = "upwards"
            df['instruction'][current] = "buy"

        if (df['in_uptrend'][previous] == False) & (df['sideways'][previous] == 0) & (df['in_uptrend'][current] == True) & (df['sideways'][current] == 0):
            df['direction'][current] = "upwards"
            df['instruction'][current] = "buy"

        # these will result in a wait instruction
        if (df['in_uptrend'][previous] == False) & (df['sideways'][previous] == 0) & (df['sideways'][current] == 1):
            df['direction'][current] = "sideways"
            df['instruction'][current] = "wait"

        if (df['sideways'][previous] == 1) & (df['in_uptrend'][current] == False) & (df['sideways'][current] == 0):
            df['direction'][current] = "downwards"
            df['instruction'][current] = "wait"

        if (df['in_uptrend'][previous] == False) & (df['sideways'][previous] == 0) & (df['in_uptrend'][current] == False) & (df['sideways'][current] == 0):
            df['direction'][current] = "downwards"
            df['instruction'][current] = "wait"

        if (df['sideways'][previous] == 1) & (df['sideways'][current] == 1):
            df['direction'][current] = "sideways"
            df['instruction'][current] = "wait"

        if (df['in_uptrend'][previous] == True) & (df['sideways'][previous] == 0) & (df['in_uptrend'][current] == True) & (df['sideways'][current] == 0):
            df['direction'][current] = "upwards"
            df['instruction'][current] = "wait"

    return df


def sideways_trend(df, n):
    df[['avehigh', 'avelow']] = df[['high', 'low']].rolling(n).mean()
    df['avemidprice'] = (df['avehigh'] + df['avelow']) / 2
    # get upper and lower bounds to compare to period highs and lows
    atr_multiple = 2.
    df['atr14'] = absolute_true_range(df, 14)
    df['UPB'] = df['avemidprice'] + atr_multiple * df['atr']
    df['LPB'] = df['avemidprice'] - atr_multiple * df['atr']
    # get the period highs and lows
    df['rangemaxprice'] = df[['high']].rolling(n).max()
    df['rangeminprice'] = df[['low']].rolling(n).min()
    df['sideways'] = 0

    def sideways_range(maxp, minp, upb, lpb):
        if maxp < upb and maxp > lpb and minp < upb and minp > lpb:
            return 1
        else:
            return 0

    df['sideways'] = df[['rangemaxprice', 'rangeminprice', 'UPB', 'LPB']].apply(
        lambda x: sideways_range(x['rangemaxprice'], x['rangeminprice'], x['UPB'], x['LPB']), axis=1)

    return df
