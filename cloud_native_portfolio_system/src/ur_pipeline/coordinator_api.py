from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException

from src.common.config import (
    UR_COORDINATOR_HOST,
    UR_COORDINATOR_PORT,
    UR_PORTFOLIO_EVALUATOR_URL,
    UR_PORTFOLIO_GENERATOR_URL,
    UR_REQUEST_PROCESSOR_URL,
    UR_SERVICE_MAX_CONNECTIONS,
    UR_SERVICE_MAX_KEEPALIVE_CONNECTIONS,
    UR_SERVICE_TIMEOUT_SECONDS,
    USER_ASSET_UNIVERSE_SIZE,
    USER_CANDIDATE_PORTFOLIOS,
    USER_PORTFOLIO_SIZE,
)
from src.common.models import (
    CandidatePortfolio,
    EvaluatedPortfolio,
    PortfolioEvaluationRequest,
    PortfolioGenerationRequest,
    PortfolioResponse,
    UserRequest,
    UserSignal,
)
from src.storage.market_signal_store import MarketSignalStore
from src.ur_pipeline.decision_process import get_user_asset_ids, rank_portfolios


# ---------------------------------------------------------------------
# Signal store
# ---------------------------------------------------------------------

store = MarketSignalStore()


# ---------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):

    app.state.http_client = httpx.Client(timeout=UR_SERVICE_TIMEOUT_SECONDS, limits=httpx.Limits(max_connections=UR_SERVICE_MAX_CONNECTIONS, max_keepalive_connections=UR_SERVICE_MAX_KEEPALIVE_CONNECTIONS))

    yield

    app.state.http_client.close()


# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------

app = FastAPI(title="User Request Microservice Coordinator", version="1.0", lifespan=lifespan)


# ---------------------------------------------------------------------
# Internal service communication
# ---------------------------------------------------------------------

def post_to_service(url: str, payload: dict, service_name: str):
    """
    Send one request to an internal user-pipeline microservice.

    Converts communication failures into errors returned by the
    coordinator API.
    """

    client: httpx.Client = (app.state.http_client)

    try:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail=(f"{service_name} timed out")) from error

    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=(f"{service_name} returned HTTP {error.response.status_code}")) from error

    except httpx.RequestError as error:
        raise HTTPException(status_code=502, detail=(f"Could not communicate with {service_name}")) from error


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.get("/health")
def health_check():

    if not store.check_connection():
        raise HTTPException(status_code=503, detail="Market signal store unavailable")

    return {
        "status": "healthy",
        "architecture": "microservices",
        "asset_universe_size": USER_ASSET_UNIVERSE_SIZE,
        "portfolio_size": USER_PORTFOLIO_SIZE,
        "candidate_portfolios": USER_CANDIDATE_PORTFOLIOS
    }


# ---------------------------------------------------------------------
# Portfolio request
# ---------------------------------------------------------------------

@app.post("/portfolio", response_model=PortfolioResponse)
def create_portfolio(request: UserRequest) -> PortfolioResponse:
    """
    Execute the complete deterministic user-request workflow through
    independently deployed microservices.
    """

    # -------------------------------------------------------------
    # 1. Request Processor service
    # -------------------------------------------------------------

    user_signal_data = post_to_service(url=UR_REQUEST_PROCESSOR_URL, payload=request.model_dump(mode="json"), service_name="Request Processor")
    user_signal = UserSignal.model_validate(user_signal_data)

    # -------------------------------------------------------------
    # 2. Retrieve fixed asset-signal snapshot
    # -------------------------------------------------------------

    try:
        asset_ids = get_user_asset_ids()
        asset_signals = store.get_signals(asset_ids)

    except KeyError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    # -------------------------------------------------------------
    # 3. Portfolio Generator service
    # -------------------------------------------------------------

    generation_request = (PortfolioGenerationRequest(user_signal=user_signal, asset_signals=asset_signals))
    portfolio_data = post_to_service(url=UR_PORTFOLIO_GENERATOR_URL, payload=generation_request.model_dump(mode="json"), service_name="Portfolio Generator")
    candidate_portfolios = [CandidatePortfolio.model_validate(portfolio) for portfolio in portfolio_data]

    # -------------------------------------------------------------
    # 4. Portfolio Evaluator service
    # -------------------------------------------------------------

    evaluation_request = (PortfolioEvaluationRequest(user_signal=user_signal, portfolios=candidate_portfolios, asset_signals=asset_signals))
    evaluation_data = post_to_service(url=UR_PORTFOLIO_EVALUATOR_URL, payload=evaluation_request.model_dump(mode="json"), service_name="Portfolio Evaluator")
    evaluated_portfolios = [EvaluatedPortfolio.model_validate(portfolio) for portfolio in evaluation_data]

    # -------------------------------------------------------------
    # 5. Deterministic ranking
    # -------------------------------------------------------------

    ranked_portfolios = rank_portfolios(evaluated_portfolios)

    # -------------------------------------------------------------
    # 6. Response
    # -------------------------------------------------------------

    return PortfolioResponse(request_id=request.request_id, ranked_portfolios=ranked_portfolios)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":

    print("Starting User Request Microservice Coordinator")
    print(f"Request Processor: {UR_REQUEST_PROCESSOR_URL}")
    print(f"Portfolio Generator: {UR_PORTFOLIO_GENERATOR_URL}")
    print(f"Portfolio Evaluator: {UR_PORTFOLIO_EVALUATOR_URL}")

    uvicorn.run(app, host=UR_COORDINATOR_HOST, port=UR_COORDINATOR_PORT, access_log=False)