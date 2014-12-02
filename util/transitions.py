"""
Transition class containing the functions for the next state in the finite state machine:

- 'initialize_transitions', initialize backtest class and subclasses futuresdatabase and rangebar
- 'load_daily_data_transitions', gets daily tick data from SQL database
- 'search_for_event_transitions', looks for a break in the range bar to compute indicator and strategy
- 'compute_indicators_transitions', compute indicators at close of bar
- 'check_strategy_transitions', check if strategy needs to enter/exit
"""

import pandas as pd
from pandas.tseries.offsets import *
import ipdb
from util.backtest import Backtest
from util.futuresdatabase import FuturesDatabase
from util.rangebar import RangeBar
from util.dailytick import DailyTick
from util.order import Order
from util.market import Market
from util.indicators import *
from util.strategies import *
from util.trades import Trades

class Transitions:

    @staticmethod
    def initialize_transitions((instr_name, RANGE, init_day, final_day)):
        table_name = instr_name + '_LAST'

        start_stamp = pd.Timestamp(init_day).tz_localize('US/Central')
        start_stamp_utc = start_stamp.tz_convert('utc')

        final_stamp = pd.Timestamp(final_day).tz_localize('US/Central')
        final_stamp_utc = final_stamp.tz_convert('utc')

        bt = Backtest(table_name, RANGE, start_stamp_utc, final_stamp_utc)

        bt.futures_db = FuturesDatabase()
        bt.range_bar = RangeBar(instr_name, RANGE)
        bt.daily_tick = DailyTick(None, 0)
        bt.order = Order()
        bt.market = Market()
        bt.indicators['FisherTransform'] = FisherTransform(bt, bt.range_bar.Close, 15)
        bt.indicators['LinRegSlope'] = LinRegSlope(bt, bt.indicators['FisherTransform'].val, 2)
        bt.strategies['FT_Quicky_Base'] = FT_Quicky_Base(bt, PL=17, offset=3, FTdthresh=0.1, FTthresh=2.5, maxBars=1)
        bt.trades = Trades()

        new_state = "load_daily_data"

        return new_state, bt

    def load_daily_data_transitions(self, bt):

        if bt.start_stamp_utc < bt.final_stamp_utc:
            print bt.start_stamp_utc

            start_date = self.timestamp_to_SQLstring(bt.start_stamp_utc)

            # get end of day timestamp
            end_stamp_utc = bt.start_stamp_utc + Day() - 45*Minute()

            end_date = self.timestamp_to_SQLstring(end_stamp_utc)

            bt.daily_tick.df = bt.futures_db.fetch_between_dates(table_name=bt.table_name,
                                                                 start_date=start_date,
                                                                 end_date=end_date)

            new_state = "search_for_event"

        else:
            new_state = "show_results"


        return new_state, bt

    @staticmethod
    def search_for_event_transitions(bt):

        if bt.daily_tick.cnt < bt.daily_tick.df.shape[0]:
            bt.tick = bt.daily_tick.df.ix[bt.daily_tick.cnt]
            bt.range_bar.tick_list.append(bt.tick['Last'])
            # check for open orders and determine if they need to be filled
            if bt.market.position != "FLAT":
                bt.order.update(bt)

            # compute range bar HLOC
            if bt.daily_tick.cnt == 0:  # first tick of day session
                bt.range_bar.init(bt.tick)

            elif bt.daily_tick.cnt == (bt.daily_tick.df.shape[0]-1):  # last tick of day session
                bt.range_bar.update(bt.tick)
                bt.range_bar.close()

            else:  # normal range bar check and update
                bt.range_bar.update(bt.tick)

            # next state logic
            if bt.range_bar.event_found:
                new_state = "compute_indicators"
                bt.range_bar.event_found = False
            else:
                new_state = "search_for_event"

            bt.daily_tick.cnt += 1

        else:

            bt.daily_tick.cnt = 0

            # increment to next day
            bt.start_stamp_utc += Day()

            # if start date is Thursday 5PM CST jump to Sunday 5PM CST
            if bt.start_stamp_utc.weekday() == 4:
                bt.start_stamp_utc += 2*Day()

            new_state = "load_daily_data"

        return new_state, bt

    @staticmethod
    def compute_indicators_transitions(bt):
        bt.indicators['FisherTransform'].on_bar_update()
        bt.indicators['LinRegSlope'].on_bar_update()

        new_state = "check_strategy"
        return new_state, bt

    @staticmethod
    def check_strategy_transitions(bt):
        new_state = "search_for_event"
        bt.strategies['FT_Quicky_Base'].on_bar_update()
        return new_state, bt

    @staticmethod
    def show_results_transitions(bt):
        bt.trades.convert_to_dataframe()
        bt.trades.trade_log['cum_prof'] = np.cumsum(bt.trades.trade_log['profit'])
        col = ['market_pos', 'entry_price', 'exit_price', 'entry_time', 'exit_time', 'exit_name', 'profit', 'cum_prof']
        print bt.trades.trade_log[col]
        #ipdb.set_trace()
        new_state = "finished"
        return new_state, bt

    def timestamp_to_SQLstring(self, timestamp):
        return str(timestamp)[:-6]

