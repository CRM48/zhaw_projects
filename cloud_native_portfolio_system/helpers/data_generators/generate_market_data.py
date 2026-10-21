from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

RANDOM_SEED = 42

SMALL_ASSETS = 100
MEDIUM_ASSETS = 500
LARGE_ASSETS = 1000

NUM_PERIODS = 100

START_TIME = "2026-01-05 09:00:00"

OUTPUT_DIR = Path("data/market_data")
TEST_SET_DIR = OUTPUT_DIR / "test_sets"
INITIAL_SIGNAL_DIR = OUTPUT_DIR / "initial_signals"


# ---------------------------------------------------------------------
# Asset setup
# ---------------------------------------------------------------------

def create_assets(rng: np.random.Generator) -> pd.DataFrame:
    """
    Create the complete fixed asset universe.

    Smaller test sets are subsets of this same universe.
    """

    asset_ids = [f"ASSET_{i:04d}" for i in range(1, LARGE_ASSETS + 1)]

    initial_prices = rng.uniform(low=20.0, high=300.0, size=LARGE_ASSETS)

    # Synthetic characteristics used only to generate price changes.
    hourly_drifts = rng.uniform(low=-0.00005, high=0.00015, size=LARGE_ASSETS)
    hourly_volatilities = rng.uniform(low=0.002, high=0.008, size=LARGE_ASSETS)

    return pd.DataFrame(
        {
            "asset_id": asset_ids,
            "initial_price": initial_prices,
            "hourly_drift": hourly_drifts,
            "hourly_volatility": hourly_volatilities,
        }
    )


# ---------------------------------------------------------------------
# Initial signal store
# ---------------------------------------------------------------------

def create_initial_signals(assets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """
    Create the initial signal state used before each experiment.
    """

    return pd.DataFrame(
        {
            "asset_id": assets["asset_id"],
            "last_price": assets["initial_price"].round(4),
            "expected_return": rng.uniform(-0.001, 0.001, len(assets)),
            "risk": rng.uniform(0.005, 0.025, len(assets)),
            "updated_at": pd.Timestamp(START_TIME) - pd.Timedelta(hours=1),
        }
    )


# ---------------------------------------------------------------------
# Market-event generation
# ---------------------------------------------------------------------

def create_market_events(assets: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """
    Generate hourly market updates for the complete asset universe.

    Every asset receives exactly one update in each period before
    the next period begins.
    """

    timestamps = pd.date_range(start=START_TIME, periods=NUM_PERIODS, freq="h")
    current_prices = dict(zip(assets["asset_id"], assets["initial_price"]))
    drift = dict(zip(assets["asset_id"], assets["hourly_drift"]))
    volatility = dict(zip(assets["asset_id"], assets["hourly_volatility"]))

    events = []

    for timestamp in timestamps:

        # Every asset is updated once before moving to the next hour.
        for asset_id in assets["asset_id"]:

            hourly_return = rng.normal(loc=drift[asset_id],scale=volatility[asset_id])

            new_price = (current_prices[asset_id] * (1 + hourly_return))
            new_price = max(new_price, 1.0)

            events.append(
                {
                    "asset_id": asset_id,
                    "price": round(new_price, 4),
                    "timestamp": timestamp,
                }
            )

            current_prices[asset_id] = new_price

    return pd.DataFrame(events)


# ---------------------------------------------------------------------
# Save datasets
# ---------------------------------------------------------------------

def save_dataset(name: str, asset_count: int, events: pd.DataFrame, initial_signals: pd.DataFrame) -> None:
    """
    Save the events and initial signals for one test size.
    """

    asset_ids = set(initial_signals.iloc[:asset_count]["asset_id"])
    test_events = events[events["asset_id"].isin(asset_ids)]
    test_signals = initial_signals.iloc[:asset_count]

    test_events.to_csv(TEST_SET_DIR / f"md_{name}.csv", index=False)
    test_signals.to_csv(INITIAL_SIGNAL_DIR / f"signals_{name}.csv", index=False)


def save_datasets(events: pd.DataFrame, initial_signals: pd.DataFrame) -> None:

    TEST_SET_DIR.mkdir(parents=True, exist_ok=True)

    INITIAL_SIGNAL_DIR.mkdir(parents=True, exist_ok=True)

    save_dataset("small", SMALL_ASSETS, events, initial_signals)
    save_dataset("medium", MEDIUM_ASSETS, events, initial_signals)
    save_dataset("large", LARGE_ASSETS, events, initial_signals)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():

    rng = np.random.default_rng(RANDOM_SEED)

    assets = create_assets(rng)

    initial_signals = create_initial_signals(assets, rng)
    events = create_market_events(assets, rng)

    save_datasets(events, initial_signals)

    print("Market test data generated:")
    print(f"Small:  {SMALL_ASSETS} assets, {SMALL_ASSETS * NUM_PERIODS:,} events")
    print(f"Medium: {MEDIUM_ASSETS} assets, {MEDIUM_ASSETS * NUM_PERIODS:,} events")
    print(f"Large:  {LARGE_ASSETS} assets, {LARGE_ASSETS * NUM_PERIODS:,} events")


if __name__ == "__main__":
    main()