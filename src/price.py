from decimal import Decimal

def calc_price(buy_price, buy_currency, fx_usdkrw, margin_pct, target_currency):
    buy = Decimal(str(buy_price))
    if buy_currency == 'USD' and target_currency == 'KRW':
        base = buy * Decimal(str(fx_usdkrw))
    elif buy_currency == 'KRW' and target_currency == 'USD':
        base = buy / Decimal(str(fx_usdkrw))
    else:
        base = buy
    sell = (base * (Decimal('1') + Decimal(str(margin_pct))/Decimal('100')))
    return round(sell, 2)
