import numpy as np
import pandas as pd

from src.common.config import USER_REQUEST_FILE


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

RANDOM_SEED = 42

NUM_REQUESTS = 10_000


# ---------------------------------------------------------------------
# User-request generation
# ---------------------------------------------------------------------

def create_user_requests(rng: np.random.Generator) -> pd.DataFrame:
    """
    Create a fixed set of synthetic user portfolio requests.

    Preference values span the complete normalised range from
    0 to 1. Each preference dimension is shuffled independently
    so the generated profiles contain varied combinations while
    remaining completely reproducible.
    """

    request_ids = [f"REQUEST_{index:05d}" for index in range(1, NUM_REQUESTS + 1)]

    # Generate an evenly distributed range of preference values.
    #
    # Each dimension receives the same overall distribution but is
    # independently shuffled to create different user profiles.
    preference_values = np.linspace(0.0, 1.0, NUM_REQUESTS)

    risk_tolerance = (preference_values.copy())
    return_preference = (preference_values.copy())
    diversification_preference = (preference_values.copy())

    rng.shuffle(risk_tolerance)
    rng.shuffle(return_preference)
    rng.shuffle(diversification_preference)

    return pd.DataFrame({"request_id": request_ids, "risk_tolerance": risk_tolerance, "return_preference": return_preference, "diversification_preference": diversification_preference})


# ---------------------------------------------------------------------
# Save dataset
# ---------------------------------------------------------------------

def save_requests(requests: pd.DataFrame) -> None:
    """
    Save the fixed user-request dataset.
    """

    USER_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    requests.to_csv(USER_REQUEST_FILE, index=False)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:

    rng = np.random.default_rng(RANDOM_SEED)
    requests = create_user_requests(rng)
    save_requests(requests)

    print("User-request test data generated:")
    print(f"Requests: {len(requests):,}")
    print(f"Output: {USER_REQUEST_FILE}")
    print("\nExample requests:")
    print(requests.head())


if __name__ == "__main__":
    main()