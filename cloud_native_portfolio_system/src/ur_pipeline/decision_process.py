from src.common.config import USER_ASSET_UNIVERSE_SIZE
from src.common.models import EvaluatedPortfolio, PortfolioResponse, UserRequest

from src.storage.market_signal_store import MarketSignalStore

from src.ur_pipeline.request_processor import process_user_request
from src.ur_pipeline.portfolio_generator import generate_portfolios
from src.ur_pipeline.portfolio_evaluator import evaluate_portfolios




# ---------------------------------------------------------------------
# Asset universe
# ---------------------------------------------------------------------

def get_user_asset_ids() -> list[str]:
    """
    Return the fixed asset universe used by the user-request pipeline.

    Keeping this universe fixed prevents changes in the market-data
    experiment asset count from changing the user-request workload.
    """

    return [f"ASSET_{index:04d}" for index in range(1, USER_ASSET_UNIVERSE_SIZE + 1)]


# ---------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------

def rank_portfolios(portfolios: list[EvaluatedPortfolio]) -> list[EvaluatedPortfolio]:
    """
    Rank evaluated portfolios from highest to lowest suitability.

    portfolio_id is used as a deterministic tie-breaker.
    """

    return sorted(portfolios, key=lambda portfolio: (-portfolio.suitability_score, portfolio.portfolio.portfolio_id))


# ---------------------------------------------------------------------
# Decision process
# ---------------------------------------------------------------------

def run_decision_process(request: UserRequest, store: MarketSignalStore) -> PortfolioResponse:
    """
    Execute the complete deterministic user-request decision flow.

    This function represents the agentic decision process during
    experiments. Every request follows exactly the same sequence.
    """

    # -------------------------------------------------------------
    # 1. Process user information
    # -------------------------------------------------------------

    user_signal = process_user_request(request)

    # -------------------------------------------------------------
    # 2. Retrieve one fixed asset-signal view
    # -------------------------------------------------------------

    asset_ids = get_user_asset_ids()

    asset_signals = store.get_signals(asset_ids)

    # -------------------------------------------------------------
    # 3. Generate candidate portfolios
    # -------------------------------------------------------------

    candidate_portfolios = generate_portfolios(user_signal=user_signal, asset_signals=asset_signals)

    # -------------------------------------------------------------
    # 4. Evaluate candidate portfolios
    # -------------------------------------------------------------

    evaluated_portfolios = evaluate_portfolios(user_signal=user_signal, portfolios=candidate_portfolios, asset_signals=asset_signals,)

    # -------------------------------------------------------------
    # 5. Rank portfolios
    # -------------------------------------------------------------

    ranked_portfolios = rank_portfolios(evaluated_portfolios)

    # -------------------------------------------------------------
    # 6. Return result
    # -------------------------------------------------------------

    return PortfolioResponse(request_id=request.request_id, ranked_portfolios=ranked_portfolios)