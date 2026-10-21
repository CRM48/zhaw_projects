import argparse
import math

import pandas as pd

from src.common.config import (
    MARKET_TEST_SET_FILES,
    VALID_DATASET_SIZES,
)
from src.storage.market_signal_store import MarketSignalStore


# ---------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------

def verify_run(dataset_size: str) -> bool:
    """
    Verify that the market-data run completed successfully.

    Checks that:
    - the expected assets exist in the store;
    - no unexpected assets exist;
    - every asset reached its final expected timestamp;
    - every asset contains its final expected price.
    """

    file_path = MARKET_TEST_SET_FILES[dataset_size]

    if not file_path.exists():
        raise FileNotFoundError(f"Market-data test set not found: {file_path}")

    # Load the dataset that was replayed.
    events = pd.read_csv(file_path, parse_dates=["timestamp"])

    expected_event_count = len(events)

    # Get the final event for every asset.
    final_events = (events.sort_values("timestamp").groupby("asset_id", as_index=False).tail(1).set_index("asset_id"))

    expected_asset_ids = set(final_events.index)

    # Read current state from Redis.
    store = MarketSignalStore()

    if not store.check_connection():
        raise RuntimeError("Could not connect to the market signal store.")

    signals = store.get_all_signals()

    stored_signals = {signal.asset_id: signal for signal in signals}

    stored_asset_ids = set(stored_signals)

    missing_assets = (expected_asset_ids - stored_asset_ids)

    unexpected_assets = (stored_asset_ids - expected_asset_ids)

    outdated_assets = []
    incorrect_prices = []

    for asset_id in expected_asset_ids:

        signal = stored_signals.get(asset_id)

        if signal is None:
            continue

        expected_event = final_events.loc[asset_id]

        expected_timestamp = pd.Timestamp(expected_event["timestamp"])

        actual_timestamp = pd.Timestamp(signal.updated_at)

        if actual_timestamp != expected_timestamp:
            outdated_assets.append(asset_id)

        expected_price = float(expected_event["price"])

        if not math.isclose(signal.last_price, expected_price, rel_tol=0.0, abs_tol=1e-12):
            incorrect_prices.append(asset_id)

    # -----------------------------------------------------------------
    # Results
    # -----------------------------------------------------------------

    print(f"Dataset size: {dataset_size}")
    print(f"Expected events: {expected_event_count:,}")
    print(f"Expected assets: {len(expected_asset_ids):,}")
    print(f"Assets in store: {len(stored_asset_ids):,}")

    print(f"Missing assets: {len(missing_assets):,}")
    print(f"Unexpected assets: {len(unexpected_assets):,}")
    print(f"Assets with incorrect final timestamp: {len(outdated_assets):,}")
    print(f"Assets with incorrect final price: {len(incorrect_prices):,}")

    passed = (len(missing_assets) == 0 and len(unexpected_assets) == 0 and len(outdated_assets) == 0 and len(incorrect_prices) == 0)

    if passed:
        print("\nVerification PASSED")
    else:
        print("\nVerification FAILED")

    return passed


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description="Verify the final market signal store state after a market-data replay.")
    parser.add_argument("--dataset-size", required=True, choices=VALID_DATASET_SIZES, help="Dataset that was used for the completed replay.")

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> int:

    args = parse_args()

    passed = verify_run(
        args.dataset_size
    )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())