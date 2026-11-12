# KRX official daily gold quote integration

The backend now fetches the **KRX gold 99.99_1kg** daily close (issue code
`04020000`) through the KRX OPEN API, replacing Naver as the domestic quote
source for the gold premium calculation.

## Setup

1. Apply for and get approval for **금시장 일별매매정보** on the KRX OPEN API portal.
2. Add `KRX_API_KEY=<your private key>` to `backend/.env` locally and to
   the backend hosting provider's secret environment variables. **Never commit
   the key.** The existing `.gitignore` excludes `.env`.
3. Start the backend as usual.

## Characteristics and limitations

- The endpoint `/svc/apis/gen/gold_bydd_trd` returns **daily** prices, not
  intraday quotes. No intraday or weekend pricing is implied.
- The provider checks dates from the current Korean date backwards up to
  seven days to find a valid trading day (holiday/weekend handling).
- Missing credentials, malformed JSON, unexpected schema, invalid prices, and
  upstream HTTP failures do **not** silently fall back to arbitrary values or
  the old Naver source.
- The gold premium API preserves the existing UI fields, and additionally
  returns `domestic_gold_source`, `domestic_gold_date`,
  `domestic_gold_is_realtime=false`, and `price_alignment_warning`.
- **Important:** the international gold price and exchange rate are still
  retrieved from the existing integrations, at potentially different times.
  Until timestamp-aligned international spot and FX data are implemented, the
  calculated premium is **indicative, not a contemporaneous executable spread**.
  Do not treat the result as a trade-ready signal.
- KRX API availability does not necessarily imply permission to redistribute
  prices publicly or commercially. Confirm license terms before production use.

## Run tests (offline)

From the repository root:

```sh
python -m unittest discover -s backend/tests -v
```

The unit tests use fake HTTP responses and do not require an API key or network.
