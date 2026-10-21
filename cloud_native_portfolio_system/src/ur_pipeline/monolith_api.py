import uvicorn
from fastapi import FastAPI, HTTPException

from src.common.config import (
    UR_MONOLITH_API_HOST,
    UR_MONOLITH_API_PORT,
    USER_ASSET_UNIVERSE_SIZE,
    USER_CANDIDATE_PORTFOLIOS,
    USER_PORTFOLIO_SIZE,
)

from src.common.models import PortfolioResponse, UserRequest
from src.storage.market_signal_store import MarketSignalStore
from src.ur_pipeline.decision_process import run_decision_process


# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------

app = FastAPI(title="User Request Monolith", version="1.0")


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
        raise HTTPException(status_code=503, detail="Market signal store unavailable")

    return {
        "status": "healthy",
        "architecture": "monolith",
        "asset_universe_size": USER_ASSET_UNIVERSE_SIZE,
        "portfolio_size": USER_PORTFOLIO_SIZE,
        "candidate_portfolios": USER_CANDIDATE_PORTFOLIOS,
    }


# ---------------------------------------------------------------------
# Portfolio request
# ---------------------------------------------------------------------

@app.post("/portfolio", response_model=PortfolioResponse)
def create_portfolio(request: UserRequest) -> PortfolioResponse:
    """
    Process one user portfolio request through the complete
    deterministic monolithic decision pipeline.
    """

    try:
        return run_decision_process(request=request, store=store)

    except KeyError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":

    print("Starting User Request Monolith")
    print(f"Asset universe: {USER_ASSET_UNIVERSE_SIZE}")
    print(f"Portfolio size: {USER_PORTFOLIO_SIZE}")
    print(f"Candidate portfolios: {USER_CANDIDATE_PORTFOLIOS}")

    uvicorn.run(app, host=UR_MONOLITH_API_HOST, port=UR_MONOLITH_API_PORT, access_log=False)