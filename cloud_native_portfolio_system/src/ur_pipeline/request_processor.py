from src.common.config import (
    USER_TARGET_RETURN_MAX,
    USER_TARGET_RETURN_MIN,
    USER_TARGET_RISK_MAX,
    USER_TARGET_RISK_MIN,
)
from src.common.models import (UserRequest, UserSignal)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def scale_value(value: float, minimum: float, maximum: float) -> float:
    """
    Scale a normalised value between 0 and 1 into a target range.
    """
    return minimum + value * (maximum - minimum)


# ---------------------------------------------------------------------
# Request processing
# ---------------------------------------------------------------------

def process_user_request(request: UserRequest) -> UserSignal:
    """
    Transform raw user-profile information into a standardised
    user signal.

    The transformation is completely deterministic so identical
    requests always produce identical user signals.
    """

    target_return = scale_value(value=request.return_preference, minimum=USER_TARGET_RETURN_MIN, maximum=USER_TARGET_RETURN_MAX)
    target_risk = scale_value(value=request.risk_tolerance, minimum=USER_TARGET_RISK_MIN, maximum=USER_TARGET_RISK_MAX)
    diversification_target = (request.diversification_preference)

    return UserSignal(request_id=request.request_id, target_return=target_return, target_risk=target_risk, diversification_target=diversification_target)