from datetime import datetime

from pydantic import BaseModel, Field


class MarketEvent(BaseModel):
    asset_id: str
    price: float = Field(gt=0)
    timestamp: datetime

class AssetSignal(BaseModel):
    asset_id: str
    last_price: float = Field(gt=0)
    expected_return: float
    risk: float = Field(ge=0)
    updated_at: datetime


class UserRequest(BaseModel):
    request_id: str
    risk_tolerance: float = Field(ge=0.0, le=1.0,)
    return_preference: float = Field(ge=0.0, le=1.0,)
    diversification_preference: float = Field(ge=0.0, le=1.0,)

class UserSignal(BaseModel):
    request_id: str
    target_return: float
    target_risk: float = Field(ge=0.0)
    diversification_target: float = Field(ge=0.0, le=1.0,)


class PortfolioHolding(BaseModel):
    asset_id: str
    weight: float = Field(ge=0.0, le=1.0,)

class CandidatePortfolio(BaseModel):
    request_id: str
    portfolio_id: str
    holdings: list[PortfolioHolding]


class EvaluatedPortfolio(BaseModel):
    portfolio: CandidatePortfolio

    expected_return: float
    risk: float = Field(ge=0.0)
    diversification: float = Field(ge=0.0, le=1.0)

    return_score: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    diversification_score: float = Field(ge=0.0, le=1.0)
    suitability_score: float = Field(ge=0.0, le=1.0,)


class PortfolioResponse(BaseModel):
    request_id: str
    ranked_portfolios: list[EvaluatedPortfolio]


class PortfolioGenerationRequest(BaseModel):
    user_signal: UserSignal
    asset_signals: list[AssetSignal]

class PortfolioEvaluationRequest(BaseModel):
    user_signal: UserSignal
    portfolios: list[CandidatePortfolio]
    asset_signals: list[AssetSignal]

class MarketProcessingMetric(BaseModel):
    asset_id: str
    cycle_timestamp: datetime
    worker_id: str

    stream_sequence: int
    delivery_count: int

    success: bool

    processing_latency_ms: float = Field(ge=0.0)
    event_update_latency_ms: float | None = Field(default=None, ge=0.0)
    signal_staleness_ms: float | None = Field(default=None, ge=0.0)
    error: str = ""
    