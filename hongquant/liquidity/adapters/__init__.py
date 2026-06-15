"""LRM-specific data adapters.

Reliable free sources (treasury, defillama) are implemented; the fragile
sources (fedwatch, finra, akshare_cn, mof_jp, nyfed) are graceful stubs that
return empty so composites drop-and-renormalize until they land in pass 2.
The bulk of the series come from the shared ``hongquant.data.adapters.fred``
and ``hongquant.data.adapters.yfinance_`` adapters.
"""
