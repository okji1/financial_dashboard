"""KRX OPEN API daily gold market quote provider.

This endpoint returns daily trading data, NOT a live intraday quote.
"""
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

KRX_GOLD_API_URL = "https://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd"
KRX_GOLD_1KG_CODE = "04020000"
KST = ZoneInfo("Asia/Seoul")


class KRXGoldError(Exception):
    """KRX quote could not be retrieved or validated."""


def get_krx_gold_quote(base_date=None, *, session=None, lookback_days=7):
    """Return the latest available daily close on or before base_date.

    base_date can be a date or YYYYMMDD string. Empty trading days (weekends
    and holidays) are skipped, without substituting a fabricated price.
    HTTP/authentication and unexpected schema errors fail closed.
    """
    api_key = os.getenv("KRX_API_KEY")
    if not api_key:
        raise KRXGoldError("KRX_API_KEY environment variable is missing")

    if base_date is None:
        day = datetime.now(KST).date()
    elif isinstance(base_date, str):
        day = datetime.strptime(base_date, "%Y%m%d").date()
    elif isinstance(base_date, date):
        day = base_date
    else:
        raise ValueError("base_date must be a date or YYYYMMDD string")

    if not isinstance(lookback_days, int) or not 0 <= lookback_days <= 30:
        raise ValueError("lookback_days must be an integer between 0 and 30")

    client = session if session is not None else requests
    for offset in range(lookback_days + 1):
        requested_date = (day - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            response = client.get(
                KRX_GOLD_API_URL,
                headers={"AUTH_KEY": api_key},
                params={"basDd": requested_date},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise KRXGoldError("KRX API request or JSON decoding failed") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("OutBlock_1"), list):
            raise KRXGoldError("Unexpected KRX response structure")

        for item in payload["OutBlock_1"]:
            if not isinstance(item, dict) or item.get("ISU_CD") != KRX_GOLD_1KG_CODE:
                continue
            try:
                close = float(str(item["TDD_CLSPRC"]).replace(",", ""))
                trade_date = item["BAS_DD"]
                datetime.strptime(trade_date, "%Y%m%d")
                if trade_date != requested_date or not 0 < close < 10_000_000:
                    raise ValueError("Invalid KRX quote or date")
            except (KeyError, TypeError, ValueError) as exc:
                raise KRXGoldError("Invalid KRX gold close price or trade date") from exc

            return {
                "source": "KRX_OPEN_API",
                "symbol": KRX_GOLD_1KG_CODE,
                "trade_date": trade_date,
                "close_krw_per_g": close,
                "collected_at": datetime.now(KST).isoformat(),
                "is_realtime": False,
            }

    raise KRXGoldError("No KRX gold 1kg daily quote in requested date range")
