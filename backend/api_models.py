"""Public contracts. Finite numbers and nullable unavailable measurements."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated
from typing import Literal
from datetime import date, datetime

Number = Annotated[float, Field(allow_inf_nan=False, strict=True)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='allow')


class Premium(ContractModel):
    london_gold_usd: Number
    london_gold_krw: Number
    domestic_gold_price: Number
    premium_percentage: Number
    premium_grade: str
    exchange_rate: Number
    active_contract: str
    cached: bool
    timestamp: str


class Signal(ContractModel):
    type: str
    message: str
    strength: str


class Strategy(ContractModel):
    premium_grade: str
    premium_percentage: Number
    signals: list[Signal]
    recommendation: str


class Candidate(ContractModel):
    symbol: str
    description: str
    year: int | None = None
    month: int | None = None
    expiry_date: str | None = None


class Candidates(ContractModel):
    candidates: list[Candidate]
    count: int


class ActiveContract(ContractModel):
    symbol: str
    description: str
    current_price: Annotated[Number, Field(gt=0)]
    volume: Annotated[int, Field(gt=0, strict=True)]
    open_interest: int | None = None
    expiry_year: int | None = None
    expiry_month: int | None = None
    updated_at: str


class Pressure(ContractModel):
    symbol: str
    pressure_signal: str
    buy_pressure: Annotated[Number, Field(ge=0, le=100)]
    sell_pressure: Annotated[Number, Field(ge=0, le=100)]
    recommendation: str
    timestamp: str


class MarketOverview(ContractModel):
    london_gold_usd: Number
    london_gold_krw: Number
    domestic_gold_price: Number
    premium_percentage: Number


class PremiumGrade(ContractModel):
    grade: str
    description: str


class Risk(ContractModel):
    premium_grade: PremiumGrade
    market_volatility: str
    liquidity_score: Number | None


class TradingSignal(ContractModel):
    type: str
    strength: str
    reason: str


class Analysis(ContractModel):
    timestamp: str
    market_overview: MarketOverview
    risk_assessment: Risk
    trading_signals: list[TradingSignal]
    recommendations: list[str]


class Orderbook(ContractModel):
    symbol: str
    contract_name: str
    current_price: str | Number
    volume: str | int
    pressure_analysis: dict
    orderbook: dict
    price_info: dict
    last_update_time: str
    analysis_time: str


class Update(ContractModel):
    message: str
    contract: ActiveContract
    refresh_requested: bool


class TokenStatus(BaseModel):
    cache_hit: bool


class KRXGoldItem(BaseModel):
    symbol: str
    name: str
    close: Number | None
    change: Number | None
    change_rate: Number | None
    open: Number | None
    high: Number | None
    low: Number | None
    volume_grams: Annotated[int, Field(ge=0, strict=True)]
    trading_value_krw: Annotated[int, Field(ge=0, strict=True)]


class KRXGoldDaily(BaseModel):
    source: Literal['KRX_OPEN_API']
    trade_date: date
    fetched_at: datetime
    refresh_state: Literal['ok', 'delayed']
    items: Annotated[list[KRXGoldItem], Field(min_length=1)]


class KRXHistoryItem(KRXGoldItem):
    trade_date: date


class KRXHistory(BaseModel):
    source: Literal['KRX_OPEN_API']
    symbol: Literal['04020000','04020100']
    days: Literal[30,90]
    checked_days: int
    total_days: int
    items: list[KRXHistoryItem]


class SystemEvent(BaseModel):
    id: str
    source: Literal['gold','futures','krx','collector']
    status: Literal['error','recovered']
    occurred_at: datetime
    message: str


class SystemAlerts(BaseModel):
    events: list[SystemEvent]
    snapshot_age_seconds: Number | None
    checked_at: datetime
