from src.common.config import (
    USER_CANDIDATE_PORTFOLIOS,
    USER_PORTFOLIO_SIZE,
    USER_TARGET_RETURN_MAX,
    USER_TARGET_RETURN_MIN,
    USER_TARGET_RISK_MAX,
    USER_TARGET_RISK_MIN,
)
from src.common.models import (
    AssetSignal,
    CandidatePortfolio,
    PortfolioHolding,
    UserSignal,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def normalise_distance(value: float, target: float, minimum: float, maximum: float) -> float:
    """
    Calculate the normalised distance between a value and target.
    """

    value_range = maximum - minimum

    if value_range <= 0:
        raise ValueError("Normalisation range must be greater than zero")

    return abs(value - target) / value_range


def calculate_asset_score(signal: AssetSignal, user_signal: UserSignal, return_emphasis: float) -> float:
    """
    Calculate a deterministic suitability score used during
    candidate generation.

    Lower scores represent assets closer to the user's target
    return and risk characteristics.
    """

    return_distance = normalise_distance(value=signal.expected_return, target=user_signal.target_return, minimum=USER_TARGET_RETURN_MIN, maximum=USER_TARGET_RETURN_MAX)

    risk_distance = normalise_distance(value=signal.risk, target=user_signal.target_risk, minimum=USER_TARGET_RISK_MIN, maximum=USER_TARGET_RISK_MAX)

    risk_emphasis = 1.0 - return_emphasis

    return (return_emphasis * return_distance + risk_emphasis * risk_distance)


def calculate_weights(holding_count: int, concentration: float) -> list[float]:
    """
    Generate deterministic portfolio weights.

    concentration = 0 produces an equal-weight portfolio.
    Higher values increasingly favour higher-ranked assets.
    """

    if holding_count <= 0:
        raise ValueError("holding_count must be greater than zero")

    if concentration == 0:
        return [1.0 / holding_count for _ in range(holding_count)]

    raw_weights = [1.0 + concentration * (holding_count - index - 1) for index in range(holding_count)]

    total = sum(raw_weights)

    return [weight / total for weight in raw_weights]


# ---------------------------------------------------------------------
# Portfolio generation
# ---------------------------------------------------------------------

def generate_portfolios(user_signal: UserSignal, asset_signals: list[AssetSignal]) -> list[CandidatePortfolio]:
    """
    Generate deterministic candidate portfolios for a user.

    Candidate portfolios vary their relative emphasis on return,
    risk and concentration while using exactly the same deterministic
    process for every architecture.
    """

    if len(asset_signals) < USER_PORTFOLIO_SIZE:
        raise ValueError("Not enough asset signals to construct a portfolio")

    if USER_CANDIDATE_PORTFOLIOS <= 0:
        raise ValueError("USER_CANDIDATE_PORTFOLIOS must be greater than zero")

    portfolios = []

    for candidate_index in range(USER_CANDIDATE_PORTFOLIOS):

        # Spread candidate portfolios across different return/risk
        # trade-offs while keeping generation completely deterministic.
        if USER_CANDIDATE_PORTFOLIOS == 1:
            candidate_position = 0.5
        else:
            candidate_position = (candidate_index / (USER_CANDIDATE_PORTFOLIOS - 1))

        # Candidates range from more risk-fit focused to more
        # return-fit focused.
        return_emphasis = (0.30 + 0.40 * candidate_position)

        scored_assets = []

        for signal in asset_signals:

            score = calculate_asset_score(signal=signal, user_signal=user_signal, return_emphasis=return_emphasis)
            scored_assets.append((score, signal.asset_id, signal))

        # asset_id provides deterministic tie-breaking.
        scored_assets.sort(key=lambda item: (item[0], item[1]))

        selected_assets = [item[2] for item in scored_assets[:USER_PORTFOLIO_SIZE]]

        # Candidate portfolios also vary from equal-weighted to
        # progressively more concentrated.
        concentration = candidate_position

        weights = calculate_weights(holding_count=len(selected_assets), concentration=concentration)

        holdings = [PortfolioHolding(asset_id=signal.asset_id, weight=weight) for signal, weight in zip(selected_assets, weights)]

        portfolio = CandidatePortfolio(
            request_id=user_signal.request_id,
            portfolio_id=(f"{user_signal.request_id}_P{candidate_index + 1:02d}"),
            holdings=holdings
        )

        portfolios.append(portfolio)

    return portfolios