import pandas as pd
import redis

from src.common.models import AssetSignal
from src.common.config import (
    INITIAL_SIGNAL_FILES,
    REDIS_DB,
    REDIS_HOST,
    REDIS_KEY_PREFIX,
    REDIS_PORT,
    VALID_DATASET_SIZES,
)

# ---------------------------------------------------------------------
# Market signal store
# ---------------------------------------------------------------------

class MarketSignalStore:

    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT, db: int = REDIS_DB, key_prefix: str = REDIS_KEY_PREFIX):
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self.key_prefix = key_prefix


    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _key(self, asset_id: str) -> str:
        return f"{self.key_prefix}:{asset_id}"


    def check_connection(self) -> bool:
        try:
            return self.redis.ping()
        except redis.ConnectionError:
            return False

    # -----------------------------------------------------------------
    # Signal operations
    # -----------------------------------------------------------------

    def get_signal(self, asset_id: str) -> AssetSignal | None:

        data = self.redis.hgetall(self._key(asset_id))

        if not data:
            return None

        return AssetSignal(
            asset_id=data["asset_id"],
            last_price=float(data["last_price"]),
            expected_return=float(data["expected_return"]),
            risk=float(data["risk"]),
            updated_at=data["updated_at"],
        )


    def update_signal(self, signal: AssetSignal) -> None:

        self.redis.hset(
            self._key(signal.asset_id),
            mapping={
                "asset_id": signal.asset_id,
                "last_price": signal.last_price,
                "expected_return": signal.expected_return,
                "risk": signal.risk,
                "updated_at": signal.updated_at.isoformat(),
            },
        )

    def get_signal_snapshot(self) -> list[AssetSignal]:
        """
        Retrieve the current asset signals in deterministic asset order.

        Redis pipelining is used to reduce network round trips when
        retrieving multiple signals.
        """

        keys = sorted(self.redis.scan_iter(match=f"{self.key_prefix}:*"))

        if not keys:
            return []

        pipeline = self.redis.pipeline(transaction=False)

        for key in keys:
            pipeline.hgetall(key)

        results = pipeline.execute()

        signals = []

        for data in results:

            if not data:
                continue

            signal = AssetSignal(
                asset_id=data["asset_id"],
                last_price=float(data["last_price"]),
                expected_return=float(data["expected_return"]),
                risk=float(data["risk"]),
                updated_at=data["updated_at"]
            )

            signals.append(signal)

        signals.sort(key=lambda signal: signal.asset_id)

        return signals


    def get_all_signals(self) -> list[AssetSignal]:
        return self.get_signal_snapshot()

    def get_signals(self, asset_ids: list[str]) -> list[AssetSignal]:
        """
        Retrieve a fixed collection of asset signals using one Redis
        pipeline.

        The returned order matches the supplied asset_id order.
        """

        if not asset_ids:
            return []

        pipeline = self.redis.pipeline(transaction=False)

        for asset_id in asset_ids:
            pipeline.hgetall(self._key(asset_id))

        results = pipeline.execute()

        signals = []

        for asset_id, data in zip(asset_ids, results):

            if not data:
                raise KeyError(f"No existing signal found for {asset_id}")

            signals.append(
                AssetSignal(
                    asset_id=data["asset_id"],
                    last_price=float(data["last_price"]),
                    expected_return=float(data["expected_return"]),
                    risk=float(data["risk"]),
                    updated_at=data["updated_at"]
                )
            )

        return signals


    # -----------------------------------------------------------------
    # Experiment reset
    # -----------------------------------------------------------------

    def clear_store(self) -> None:

        keys = list(self.redis.scan_iter(match=f"{self.key_prefix}:*"))

        if keys:
            self.redis.delete(*keys)


    def reset_store(self, dataset_size: str) -> None:

        if dataset_size not in VALID_DATASET_SIZES:
            raise ValueError(f"dataset_size must be one of: {', '.join(VALID_DATASET_SIZES)}")

        file_path = INITIAL_SIGNAL_FILES[dataset_size]

        if not file_path.exists():
            raise FileNotFoundError(f"Initial signal file not found: {file_path}")

        signals = pd.read_csv(file_path, parse_dates=["updated_at"])

        self.clear_store()

        for _, row in signals.iterrows():

            signal = AssetSignal(
                asset_id=row["asset_id"],
                last_price=float(row["last_price"]),
                expected_return=float(row["expected_return"]),
                risk=float(row["risk"]),
                updated_at=row["updated_at"].to_pydatetime(),
            )

            self.update_signal(signal)


    