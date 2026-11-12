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
