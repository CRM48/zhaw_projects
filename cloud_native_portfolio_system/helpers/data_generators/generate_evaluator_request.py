import json

from src.common.config import (
    EVALUATOR_REQUEST_FILE,
    INITIAL_SIGNAL_FILES,
    USER_ASSET_UNIVERSE_SIZE,
)
from src.common.models import AssetSignal, PortfolioEvaluationRequest, UserRequest
from src.ur_pipeline.portfolio_generator import generate_portfolios
from src.ur_pipeline.request_processor import process_user_request

import pandas as pd


# ---------------------------------------------------------------------
# Fixed Experiment 4 user
# ---------------------------------------------------------------------

EXPERIMENT_4_USER = UserRequest(request_id="EXP4_REQUEST", risk_tolerance=0.4, return_preference=0.7, diversification_preference=0.8)


# ---------------------------------------------------------------------
# Load fixed asset signals
# ---------------------------------------------------------------------

def load_asset_signals() -> list[AssetSignal]:
    """
    Load the first fixed user-asset universe from the deterministic
    small initial-signal dataset.
    """

    data = pd.read_csv(INITIAL_SIGNAL_FILES["small"], parse_dates=["updated_at"])
    data = data.iloc[:USER_ASSET_UNIVERSE_SIZE]

    return [
        AssetSignal(
            asset_id=row["asset_id"],
            last_price=float(row["last_price"]),
            expected_return=float(row["expected_return"]),
            risk=float(row["risk"]),
            updated_at=(row["updated_at"].to_pydatetime())
        )
        for _, row in data.iterrows()
    ]


# ---------------------------------------------------------------------
# Generate request
# ---------------------------------------------------------------------

def generate_request() -> PortfolioEvaluationRequest:
    """
    Create one deterministic Portfolio Evaluator request.
    """
    asset_signals = load_asset_signals()
    user_signal = process_user_request(EXPERIMENT_4_USER)
    portfolios = generate_portfolios(user_signal=user_signal, asset_signals=asset_signals)

    return PortfolioEvaluationRequest(user_signal=user_signal, portfolios=portfolios, asset_signals=asset_signals)


# ---------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------

def main() -> None:
    request = generate_request()

    EVALUATOR_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EVALUATOR_REQUEST_FILE.open("w", encoding="utf-8") as file: json.dump(request.model_dump(mode="json"), file, indent=2)

    print("Experiment 4 evaluator request created")
    print(f"File: {EVALUATOR_REQUEST_FILE}")
    print(f"Asset signals: {len(request.asset_signals)}")
    print(f"Candidate portfolios: {len(request.portfolios)}")

if __name__ == "__main__":
    main()