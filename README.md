# FinTech_OA
#### This is a strategy sample I implemented. 
##### HighVol: A long straddle strategy for high volitility market, and do delta&gamma hedge at the same time. I long straddle at the first day, and every day, I first do gamma-hedging by trade options, then do delta-hedging by trade underlying SPY. 

##### LowVol: A short straddle strategy for low volitility market, and do delta&gamma hedge at the same time. I short straddle at the first day, and every day, I first do gamma-hedging by trade options, then do delta-hedging by trade underlying SPY. 

##### IVHis: Buy options if the IV is lower than historical volatility or expected volatility, and sell if it is the opposite case. And do delta hedging at the same time. I compare the IV of the option and the Historical Vol ranging from the day I buy/sell to its expiry. Based on the comparison result, I decide whether I buy or sell the option. at the first day, and every day, I first do gamma-hedging by trade options, then do delta-hedging by trade underlying SPY.
