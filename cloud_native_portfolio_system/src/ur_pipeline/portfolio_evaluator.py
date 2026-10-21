import math

from src.common.config import (
    USER_DIVERSIFICATION_SCORE_WEIGHT,
    USER_RETURN_SCORE_WEIGHT,
    USER_RISK_SCORE_WEIGHT,
    USER_TARGET_RETURN_MAX,
    USER_TARGET_RETURN_MIN,
    USER_TARGET_RISK_MAX,
    USER_TARGET_RISK_MIN,
)

from src.common.models import (
    AssetSignal,
    UserSignal,
    CandidatePortfolio,
    EvaluatedPortfolio,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def calculate_fit_score(value: float, target: float, minimum: float, maximum: float) -> float:
    """
    Calculate how closely a value matches a target.

    A score of 1 represents an exact match.
    A score of 0 represents a difference equal to or greater than
    the configured comparison range.
    """

    value_range = maximum - minimum

    if value_range <= 0:
        raise ValueError("Evaluation range must be greater than zero")

    distance = abs(value - target) / value_range

    return max(0.0, 1.0 - distance)


def calculate_diversification(weights: list[float]) -> float:
    """
    Calculate a normalised diversification score based on portfolio
    concentration.

    1.0 represents equal weighting across all holdings.
    Lower values represent increasingly concentrated portfolios.
    """

    holding_count = len(weights)

    if holding_count <= 1:
        return 0.0

    concentration = sum(weight ** 2 for weight in weights)

    raw_diversification = (1.0 - concentration)

    maximum_diversification = (1.0 - (1.0 / holding_count))

    diversification = (raw_diversification / maximum_diversification)

    return max(0.0, min(1.0, diversification),)


# ---------------------------------------------------------------------
# Portfolio evaluation
# ---------------------------------------------------------------------

def evaluate_portfolio(user_signal: UserSignal, portfolio: CandidatePortfolio, asset_signals: list[AssetSignal]) -> EvaluatedPortfolio:
    """
    Evaluate one candidate portfolio against the user's processed
    preference signal.
    """

    signal_lookup = {signal.asset_id: signal for signal in asset_signals}

    total_weight = sum(holding.weight for holding in portfolio.holdings)

    if not math.isclose(total_weight, 1.0, abs_tol=1e-9,):
        raise ValueError(f"Portfolio {portfolio.portfolio_id} weights must sum to 1.0")

    expected_return = 0.0
    risk = 0.0

    weights = []

    for holding in portfolio.holdings:

        signal = signal_lookup.get(holding.asset_id)

        if signal is None:
            raise KeyError(f"No asset signal found for {holding.asset_id}")

        expected_return += (holding.weight * signal.expected_return)

        # Deterministic portfolio-risk proxy.
        #
        # This is deliberately a weighted asset-risk measure rather
        # than a full covariance-based financial risk model.
        risk += (holding.weight * signal.risk)

        weights.append(holding.weight)

    diversification = (calculate_diversification(weights))

    # -------------------------------------------------------------
    # User fit
    # -------------------------------------------------------------

    return_score = calculate_fit_score(value=expected_return, target=user_signal.target_return, minimum=USER_TARGET_RETURN_MIN, maximum=USER_TARGET_RETURN_MAX)
    risk_score = calculate_fit_score(value=risk, target=user_signal.target_risk, minimum=USER_TARGET_RISK_MIN, maximum=USER_TARGET_RISK_MAX)
    diversification_score = max(0.0, 1.0 - abs( diversification - user_signal.diversification_target))

    suitability_score = (USER_RETURN_SCORE_WEIGHT * return_score + USER_RISK_SCORE_WEIGHT * risk_score + USER_DIVERSIFICATION_SCORE_WEIGHT * diversification_score)

    return EvaluatedPortfolio(portfolio=portfolio, expected_return=expected_return, risk=risk, diversification=diversification, return_score=return_score, risk_score=risk_score, diversification_score=diversification_score, suitability_score=suitability_score)


# ---------------------------------------------------------------------
# Candidate evaluation
# ---------------------------------------------------------------------

def evaluate_portfolios(user_signal: UserSignal, portfolios: list[CandidatePortfolio], asset_signals: list[AssetSignal]) -> list[EvaluatedPortfolio]:
    """
    Evaluate every candidate portfolio using the same asset-signal
    snapshot and user signal.
    """
    return [evaluate_portfolio(user_signal=user_signal, portfolio=portfolio, asset_signals=asset_signals) for portfolio in portfolios]