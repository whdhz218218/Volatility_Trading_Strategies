# ------------------------------------------------------------------------------
# Business days
# ------------------------------------------------------------------------------
from datetime import timedelta  # , date
from pandas.tseries.holiday import (AbstractHolidayCalendar,  # inherit from this to create your calendar
                                    Holiday, nearest_workday,  # to custom some holidays
                                    USMartinLutherKingJr,  # already defined holidays
                                    USPresidentsDay,  # "     "   "   "   "   "
                                    GoodFriday,
                                    USMemorialDay,  # "     "   "   "   "   "
                                    USLaborDay,
                                    USThanksgivingDay  # "     "   "   "   "   "
                                    )


class USTradingCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday('NewYearsDay', month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday('USIndependenceDay', month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday('Christmas', month=12, day=25, observance=nearest_workday)
    ]


def last_trading_day(expiry):
    # American options cease trading on the third Friday, at the close of business
    # - Weekly options expire the same day as their last trading day, which will usually be a Friday (PM-settled), [or Mondays? & Wednesdays?]
    # SPX cash index options (and other cash index options) expire on the Saturday following the third Friday of the expiration month.
    # However, the last trading day is the Thursday before that third Friday. Settlement price Friday morning opening (AM-settled).
    # http://www.daytradingbias.com/?p=84847

    dd = expiry  # option.ID.Date.date()

    # if expiry on a Saturday (standard options), then last trading day is 1d earlier
    if dd.weekday() == 5:
        dd -= timedelta(days=1)  # dd -= 1 * BDay()

    # check that Friday is not an holiday (e.g. Good Friday) and loop back
    while USTradingCalendar().holidays(dd, dd).tolist():  # if list empty (dd is not an holiday) -> False
        dd -= timedelta(days=1)

    return dd