import pandas as pd
import quandl
from QuantConnect.Securities.Option import OptionPriceModels
from datetime import timedelta
import decimal as d
from my_calendar import last_trading_day

class MyAlgorithm(QCAlgorithm):
    def Initialize(self):
        #self.SetStartDate(2014,1,1)  # Set Start Date
        self.SetStartDate(2016,12,1)  # Set Start Date
        self.SetEndDate(2017,12,1)    # Set End Date
        self.SetCash(100000)           # Set Strategy Cash
        self.resol = Resolution.Minute   # Set Frequency
        self.tickr = "SPY"
        self.Gamma,self.Delta=d.Decimal(0.0),d.Decimal(0.0)
        self.previous_delta, self.delta_treshold = d.Decimal(0.0), d.Decimal(0.05)
        # Add underlying Equity
        self.equity = self.AddEquity(self.tickr, self.resol)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.equity_symbol = self.equity.Symbol
        # Add options
        option = self.AddOption(self.tickr, self.resol) # Add the option corresponding to underlying stock
        self.option_symbol = option.Symbol

        self.SetBenchmark(self.tickr)

        # For greeks and pricer (needs some warmup)
        option.PriceModel = OptionPriceModels.CrankNicolsonFD()  # both European & American, automatically
        # Warmup is needed for Greeks calculation
        self.SetWarmUp(TimeSpan.FromDays(5))

        self._assignedOption = False
        self.call, self.put = None, None

        # Schedule an event to fire every trading day to close the options for a security the
        # time rule here tells it to fire 10 minutes before SPY's market close
        self.Schedule.On(self.DateRules.EveryDay(self.equity_symbol),
                         self.TimeRules.BeforeMarketClose(self.equity_symbol, 10),
                         Action(self.close_options))


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
                if self.Securities[x.Key].Expiry==self.Time.date():
                    if self.Securities[x.Key].Right == OptionRight.Call:
                        if self.Securities[x.Key].Strike > self.UnderlyingLastPrice:
                            self.Liquidate(x.Key)
                    else:
                        if self.Securities[x.Key].Strike < self.UnderlyingLastPrice:
                            self.Liquidate(x.Key)
                # if self.Securities[x.Key].AskPrice > 0.05: self.Liquidate(x.Key)


        # if self.Portfolio[self.equity_symbol].Invested:
        #     self.Liquidate(self.equity.Symbol)


    def ShortStraddle(self,slice):
        if not self.Portfolio.Invested:
            for kvp in slice.OptionChains:
                if kvp.Key != self.option_symbol: continue
                chain = kvp.Value   # option contracts for each 'subscribed' symbol/key
                spot_price = chain.Underlying.Price
                # get furthest expiry
                contracts_by_T = sorted(chain, key = lambda x: x.Expiry, reverse = True)
                if not contracts_by_T: return
                self.expiry = contracts_by_T[0].Expiry.date() # furthest expiry
                self.last_trading_day = last_trading_day(self.expiry)
                # get contracts with further expiry and sort them by strike
                slice_T = [i for i in chain if i.Expiry.date() == self.expiry]
                sorted_contracts = sorted(slice_T, key = lambda x: x.Strike, reverse = False)
                # get the ATM closest CALL to short
                calls = [i for i in sorted_contracts if i.Right == OptionRight.Call and i.Strike >= spot_price]
                self.call = calls[0] if calls else None
                # get the ATM closest put to short
                puts = [i for i in sorted_contracts if i.Right == OptionRight.Put and i.Strike <= spot_price]
                self.put = puts[-1] if puts else None

            if (not self.call) or (not self.put): return

            unit_price =  self.Securities[self.equity_symbol].Price * d.Decimal(100.0)   # share price x 100
            qnty = int(self.Portfolio.TotalPortfolioValue / unit_price)
            if self.call is not None: self.MarketOrder(self.call.Symbol, -qnty)
            if self.put is not None:  self.MarketOrder(self.put.Symbol, -qnty)

    def GammaHedge(self,slice):
        for i in slice.OptionChains:
            chains_G = i.Value
            if self.Portfolio.Invested:
                # sorted the optionchain by expiration date and choose the furthest date
                expiry_G = sorted(chains_G,key = lambda x: x.Expiry, reverse=True)[0].Expiry
                self.last_trading_day_G = last_trading_day(expiry_G)
                # filter the call and put contract
                call_G = [i for i in chains_G if i.Expiry == expiry_G and i.Right == OptionRight.Call]
                call_contracts_Sell = sorted(call_G,key = lambda x: x.BidPrice,reverse=True)
                call_contracts_Buy = sorted(call_G,key = lambda x: x.AskPrice)
                if len(call_contracts_Sell) == 0 and len(call_contracts_Buy) == 0: return

                unit_price =  self.Securities[self.equity_symbol].Price * d.Decimal(100.0)   # share price x 100
                qnty = int(self.Portfolio.TotalPortfolioValue / unit_price)
                if self.Gamma>0:
                    if len(call_contracts_Sell) ==0:return
                    self.Sell(all_contracts_Sell[0].Symbol, qnty)
                elif self.Gamma<0:
                    if len(call_contracts_Buy) ==0:return
                    self.Buy(all_contracts_Buy[0].Symbol, qnty)


    def OnData(self, slice):
        if self.IsWarmingUp: return
        # 1. Short straddle
        self.ShortStraddle(slice)
        # 2. delta-hedged any existing option
        if self.Portfolio.Invested and self.HourMinuteIs(11, 0):
            self.get_greeks(slice)
            self.GammaHedge(slice)
            self.get_greeks(slice)
            if abs(self.previous_delta - self.Delta) > self.delta_treshold:
                self.SetHoldings(self.equity_symbol, self.Delta)
                self.previous_delta = self.Delta


    def get_greeks(self, slice):
        if (self.call is None) or (self.put is None): return
        for kvp in slice.OptionChains:
            if kvp.Key != self.option_symbol: continue
            chain = kvp.Value   # option contracts for each 'subscribed' symbol/key
            traded_contracts = filter(lambda x: x.Symbol == self.call.Symbol or
                                         x.Symbol == self.put.Symbol, chain)
            if not traded_contracts: self.Log("No traded contracts"); return

            deltas = [i.Greeks.Delta for i in traded_contracts]
            self.Delta=sum(deltas)
            gammas = [i.Greeks.Gamma for i in traded_contracts]
            self.Gamma=sum(gammas)

    def HourMinuteIs(self, hour, minute):
        return self.Time.hour == hour and self.Time.minute == minute