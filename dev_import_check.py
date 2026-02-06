# Dev import check for modified modules
try:
    import agents.live_market_agent as lm
    import agents.market_context_agent as mc
    print('LIVE OK:', hasattr(lm, 'start_market_feed'))
    print('MARKET OK:', hasattr(mc, 'MarketContextAgent'))
    print('DATA_BUS TYPE:', type(lm.data_bus))
except Exception as e:
    print('ERROR DURING IMPORT:', e)
    import traceback
    traceback.print_exc()