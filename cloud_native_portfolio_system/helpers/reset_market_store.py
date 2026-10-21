import argparse

from src.common.config import VALID_DATASET_SIZES
from src.storage.market_signal_store import MarketSignalStore


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=("Reset the market signal store to the initial state for a selected experiment dataset."))
    parser.add_argument("--dataset-size", required=True, choices=VALID_DATASET_SIZES, help="Dataset size to initialise the signal store for.")

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:

    args = parse_args()
    store = MarketSignalStore()

    if not store.check_connection():
        raise RuntimeError("Could not connect to the market signal store.")

    store.reset_store(args.dataset_size)
    signals = store.get_all_signals()

    print("Market signal store reset.")
    print(f"Dataset size: {args.dataset_size}")
    print(f"Signals loaded: {len(signals)}")


if __name__ == "__main__":
    main()