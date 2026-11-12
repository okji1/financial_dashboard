# Domestic commodity futures: safe configuration

The previous `101X12` / `101Y02` generated codes were based on index futures
examples, **not verified gold futures**. They must not be reported as gold.
The API now returns no gold contracts by default instead of probing invented
symbols. As a result, existing futures/pressure endpoints may return 404
until verified commodity contract codes are supplied.

Before enabling the feature, download the **상품선물옵션** master contract file
from the [KIS API Portal](https://apiportal.koreainvestment.com/apiservice-category)
and validate the current, actually listed gold contracts, instrument availability,
market code and the endpoint response with KIS documentation.

Once validated, add comma-separated contract codes in the *Render backend*
environment as `KIS_GOLD_FUTURES_SYMBOLS` (never add guessed examples).

The query market code is `CF` (commodity futures) rather than `F`
(index futures). Quote/asking-price TR IDs should be confirmed on actual
eligible contracts before considering the feature production ready.

Missing or zero orderbook quantities are now **unavailable**, not a balanced
buy/sell pressure signal.

## Verification

```bash
python -m unittest discover -s backend/tests -v
```

These tests use mock/stub values; they do not prove that a particular contract
is valid or that real market quotes can be retrieved.

## 2026-11-12 master verification and optional automatic candidates

The current official `fo_com_code.mst.zip` uses underlying **KGD**, even though
an older KIS C header lists GLD. The parser supports both identifiers and admits
only commodity normal-futures records (`31`) whose name is `금 F YYYYMM`.
Spreads (`32`) and other assets are excluded. The actual latest master yielded
A88611, A88612, A88702, A88704, A88706, A88708 and A88710. These are observations
of this dated master, not codes to generate for later contracts.

Set `KIS_GOLD_FUTURES_MASTER_PATH` to a locally downloaded official `.mst` or ZIP
to use that source instead of manual `KIS_GOLD_FUTURES_SYMBOLS`. No path is set by
default. Inspect candidates before enabling the feature:

```sh
curl --fail --show-error --max-time 30 \
  https://new.real.download.dws.co.kr/common/master/fo_com_code.mst.zip \
  -o /tmp/kis-commodity-master.zip
cd /workspace/financial_dashboard/backend
venv/bin/python gold_master.py /tmp/kis-commodity-master.zip
```

Refresh at least daily through a controlled download job. Files older than 36
hours are rejected. Download to a temporary file, parse it, then atomically
replace the configured file; do not overwrite a valid master with a partial
response. Never disable TLS verification. The master does not supply an exact
expiry day through this parser; only the contract month is populated.

Live quote support is still unverified: this cloud's request to KIS port 9443
received an Envoy upstream connection-timeout 503, using an existing cached
token without issuing a new token. A read-only request through the deployed
Render pressure endpoint with A88612 returned 404. Neither result proves that
gold/CF is unsupported or that a particular contract has no trading activity.
