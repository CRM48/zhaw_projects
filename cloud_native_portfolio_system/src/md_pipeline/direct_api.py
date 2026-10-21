import uvicorn
from fastapi import FastAPI, HTTPException

from src.common.models import AssetSignal, MarketEvent
from src.md_pipeline.processor import process_market_event
from src.storage.market_signal_store import MarketSignalStore
from src.common.config import (
    DIRECT_API_HOST,
    DIRECT_API_PORT,
    SYNTHETIC_WORKLOAD_ITERATIONS,
    SYNTHETIC_WORKLOAD_PROFILE,
)


# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------

app = FastAPI(title="Market Data Direct Processor", version="1.0")


# ---------------------------------------------------------------------
# Signal store
# ---------------------------------------------------------------------

store = MarketSignalStore()


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.get("/health")
def health_check():

    if not store.check_connection():
        raise HTTPException(status_code=503, detail="Signal store unavailable")

    return {
        "status": "healthy",
        "workload_profile": SYNTHETIC_WORKLOAD_PROFILE,
        "workload_iterations": SYNTHETIC_WORKLOAD_ITERATIONS,
    }


# ---------------------------------------------------------------------
# Market-data endpoint
# ---------------------------------------------------------------------

@app.post("/market-event", response_model=AssetSignal)
def receive_market_event(event: MarketEvent) -> AssetSignal:
    """
    Receive one market event and process it synchronously.

    The request is not completed until the asset signal has been
    processed and written to the signal store.
    """

    try:
        return process_market_event(event, store)

    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

if __name__ == "__main__":

    print("Starting Market Data Direct Processor")
    print(f"Synthetic workload: {SYNTHETIC_WORKLOAD_PROFILE}")
    print(f"Synthetic iterations: {SYNTHETIC_WORKLOAD_ITERATIONS:,}")

    uvicorn.run(app, host=DIRECT_API_HOST, port=DIRECT_API_PORT, access_log=False)