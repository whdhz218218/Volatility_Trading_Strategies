import pandas as pd
from datetime import timedelta, datetime
from numpy import sqrt, mean, log, diff
import quandl
from QuantConnect.Securities.Option import OptionPriceModels
import decimal as d
from my_calendar import last_trading_day


class MyAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2014, 2, 28)  # Set Start Date
        # self.SetStartDate(2018,10,1)  # Set Start Date
        self.SetEndDate(2019, 2, 28)  # Set End Date
        self.SetCash(100000)  # Set Strategy Cash
        self.resol = Resolution.Minute  # Set Frequency
        self.tickr = "SPY"
        self.previous_delta, self.delta_treshold = d.Decimal(0.0), d.Decimal(0.05)
        # Add underlying Equity
        self.equity = self.AddEquity(self.tickr, self.resol)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.equity_symbol = self.equity.Symbol
        # Add options
        option = self.AddOption(self.tickr, self.resol)  # Add the option corresponding to underlying stock
        self.option_symbol = option.Symbol
        self.Gamma, self.Delta = d.Decimal(0.0), d.Decimal(0.0)
        self.Hisvol = d.Decimal(0.0)
        self.lastest_expiry = datetime.min
        self.SetBenchmark(self.tickr)

        # For greeks and pricer (needs some warmup)
        option.PriceModel = OptionPriceModels.CrankNicolsonFD()  # both European & American, automatically
        # Warmup is needed for Greeks calculation
        self.SetWarmUp(TimeSpan.FromDays(5))

        self.call, self.put = None, None

        # Schedule an event to fire every trading day to close the options for a security the
        # time rule here tells it to fire 10 minutes before SPY's market close
        self.Schedule.On(self.DateRules.EveryDay(self.equity_symbol),
                         self.TimeRules.BeforeMarketClose(self.equity_symbol, 10),
                         Action(self.Rebalance))

    def close_options(self):
        """ Liquidate opts (with some value) and underlying
        """
        # check this is the last trading day
        if self.last_trading_day != self.Time.date():
            return

        self.Log("We liquidate valuable options and underlying on the last trading day")

        # liquidate options (if invested and in the money)
        for x in self.Portfolio:
            if x.Value.Invested:
                # only liquidate valuable options, otherwise let them quietly expiry
                if self.Securities[x.Key].Expiry == self.Time.date():
                    # if self.Securities[x.Key].Right == OptionRight.Call:
                    #     if self.Securities[x.Key].Strike > self.Underlying.Price:
                    #         self.Liquidate(x.Key)
                    # else:
                    #     if self.Securities[x.Key].Strike < self.Underlying.Price:
                    #         self.Liquidate(x.Key)
                    if self.Securities[x.Key].AskPrice > 0.05: self.Liquidate(x.Key)
        # if self.Portfolio[self.equity_symbol].Invested:
        #     self.Liquidate(self.equity.Symbol)

    def Rebalance(self):
        calendar = self.TradingCalendar.GetDaysByType(TradingDayType.OptionExpiration, self.Time, self.EndDate)
        expiries = [i.Date for i in calendar]
        if len(expiries) == 0: return
        self.lastest_expiry = expiries[0]

    def HistoricalVol(self, time1, time2):
        quandl.ApiConfig.api_key = 'NxTUTAQswbKs5ybBbwfK'
        spy_table = quandl.get_table('SHARADAR/SFP', date={'gte': time1, 'lte': time2}, ticker='SPY')
        r = diff(log(spy_table))
        r_mean = mean(r)
        diff_square = [(r[i] - r_mean) ** 2 for i in range(0, len(r))]
        std = sqrt(sum(diff_square) * (1.0 / (len(r) - 1)))
        self.Hisvol = std * sqrt(252)

    def ComHisIV(self, slice):
        for i in slice.OptionChains:
            chains = i.Value
            if not self.Portfolio.Invested:
                # sorted the optionchain by expiration date and choose the furthest date
                expiry = sorted(chains, key=lambda x: x.Expiry, reverse=True)[0].Expiry
                self.last_trading_day = last_trading_day(expiry)
                # filter the ATM call and put contract
                call = [i for i in chains if
                        i.Expiry == expiry and i.Right == OptionRight.Call and i.Strike >= chains.Underlying.Price]
                put = [i for i in chains if
                       i.Expiry == expiry and i.Right == OptionRight.Put and i.Strike <= chains.Underlying.Price]
                # # sorted the contracts according to their implied volatility
                # call_contracts = sorted(call,key = lambda x: x.ImpliedVolatility)
                # put_contracts = sorted(put,key = lambda x: x.ImpliedVolatility)

                unit_price = self.Securities[self.equity_symbol].Price * d.Decimal(100.0)  # share price x 100
                qnty = int(self.Portfolio.TotalPortfolioValue / unit_price)
                if len(call) == 0 or call == None:
                    return
                else:
                    for i in call:
                        self.HistoricalVol(self.Time.date(), i.Expiry)
                        if self.Hisvol < i.ImpliedVolatility:
                            self.Buy(i.Symbol, qnty)
                        else:
                            self.Sell(i.Symbol, qnty)

                if len(put) == 0 or put == None:
                    return
                elif len(put) > 0:
                    for i in put:
                        self.HistoricalVol(self.Time.date(), i.Expiry)
                        if self.Hisvol < i.ImpliedVolatility:
                            self.Buy(i.Symbol, qnty)
                        else:
                            self.Sell(i.Symbol, qnty)

    def GammaHedge(self, slice):
        for i in slice.OptionChains:
            chains_G = i.Value
            if self.Portfolio.Invested:
                # sorted the optionchain by expiration date and choose the furthest date
                expiry_G = sorted(chains_G, key=lambda x: x.Expiry, reverse=True)[0].Expiry
                self.last_trading_day_G = last_trading_day(expiry_G)
                # filter the call and put contract
                call_G = [i for i in chains_G if i.Expiry == expiry_G and i.Right == OptionRight.Call]
                call_contracts_Sell = sorted(call_G, key=lambda x: x.BidPrice, reverse=True)
                call_contracts_Buy = sorted(call_G, key=lambda x: x.AskPrice)
                if len(call_contracts_Sell) == 0 and len(call_contracts_Buy) == 0: return

                unit_price = self.Securities[self.equity_symbol].Price * d.Decimal(100.0)  # share price x 100
                qnty = int(self.Portfolio.TotalPortfolioValue / unit_price)
                if self.Gamma > 0:
                    if len(call_contracts_Sell) == 0: return
                    self.Sell(all_contracts_Sell[0].Symbol, qnty)
                elif self.Gamma < 0:
                    if len(call_contracts_Buy) == 0: return
                    self.Buy(all_contracts_Buy[0].Symbol, qnty)

    def OnData(self, slice):
        if self.IsWarmingUp: return

        if self.Time.date() == self.lastest_expiry.date():
            for x in self.Portfolio:
                if x.Key.Value != "SPY":
                    if self.Securities[x.Key].Expiry == self.Time.date():
                        self.Liquidate(x.Key)
            self.get_greeks(slice)
            if abs(self.previous_delta - self.Delta) > self.delta_treshold:
                self.SetHoldings(self.equity_symbol, self.Delta)
                self.previous_delta = self.Delta

        # 1. Compare Historical Vol and IV
        self.ComHisIV(slice)

        # 2. delta-hedged any existing option
        if self.Portfolio.Invested and self.HourMinuteIs(11, 0):
            # self.get_greeks(slice)
            # self.GammaHedge(slice)
            self.get_greeks(slice)
            if abs(self.previous_delta - self.Delta) > self.delta_treshold:
                self.SetHoldings(self.equity_symbol, self.Delta)
                self.previous_delta = self.Delta

    def get_greeks(self, slice):
        if (self.call is None) or (self.put is None): return
        for kvp in slice.OptionChains:
            if kvp.Key != self.option_symbol: continue
            chain = kvp.Value  # option contracts for each 'subscribed' symbol/key
            traded_contracts = filter(lambda x: x.Symbol == self.call.Symbol or
                                                x.Symbol == self.put.Symbol, chain)
            if not traded_contracts: return

            deltas = [i.Greeks.Delta for i in traded_contracts]
            self.Delta = sum(deltas)
            gammas = [i.Greeks.Gamma for i in traded_contracts]
            self.Gamma = sum(gammas)

    def HourMinuteIs(self, hour, minute):
        return self.Time.hour == hour and self.Time.minute == minute