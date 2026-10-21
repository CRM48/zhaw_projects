import argparse
import asyncio

import nats
from nats.js.api import StorageType
from nats.js.errors import NotFoundError

from src.common.config import (
    NATS_STREAM,
    NATS_STREAM_STORAGE,
    NATS_SUBJECT,
    NATS_URL,
    NATS_CONNECT_TIMEOUT_SECONDS
)


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Create or reset the JetStream stream used by the "
            "market-data event-driven pipeline."
        )
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete and recreate the market-data stream. "
            "Use before a new experiment run."
        ),
    )

    return parser.parse_args()


# ---------------------------------------------------------------------
# NATS setup
# ---------------------------------------------------------------------

async def setup_nats(reset: bool) -> None:

    nc = await nats.connect(NATS_URL, connect_timeout=NATS_CONNECT_TIMEOUT_SECONDS)

    try:
        js = nc.jetstream()

        stream_exists = True

        try:
            await js.stream_info(NATS_STREAM)

        except NotFoundError:
            stream_exists = False

        # -------------------------------------------------------------
        # Optional experiment reset
        # -------------------------------------------------------------

        if reset and stream_exists:

            print(
                f"Deleting existing NATS stream: "
                f"{NATS_STREAM}"
            )

            await js.delete_stream(NATS_STREAM)

            stream_exists = False

        # -------------------------------------------------------------
        # Stream creation
        # -------------------------------------------------------------

        if not stream_exists:

            if NATS_STREAM_STORAGE == "memory":
                storage = StorageType.MEMORY
            else:
                storage = StorageType.FILE

            await js.add_stream(
                name=NATS_STREAM,
                subjects=[NATS_SUBJECT],
                storage=storage,
            )

            print("NATS stream created.")

        else:
            print("NATS stream already exists.")

        stream_info = await js.stream_info(
            NATS_STREAM
        )

        print(f"Stream: {stream_info.config.name}")
        print(
            f"Subjects: "
            f"{stream_info.config.subjects}"
        )
        print(
            f"Storage: "
            f"{stream_info.config.storage}"
        )
        print(
            f"Messages currently stored: "
            f"{stream_info.state.messages}"
        )

    finally:
        await nc.close()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:

    args = parse_args()

    asyncio.run(
        setup_nats(
            reset=args.reset,
        )
    )


if __name__ == "__main__":
    main()