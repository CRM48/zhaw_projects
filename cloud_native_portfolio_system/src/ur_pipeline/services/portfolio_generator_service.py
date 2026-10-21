import uvicorn
from fastapi import FastAPI, HTTPException

from src.common.config import UR_PORTFOLIO_GENERATOR_HOST, UR_PORTFOLIO_GENERATOR_PORT
from src.common.models import CandidatePortfolio, PortfolioGenerationRequest
from src.ur_pipeline.portfolio_generator import generate_portfolios


# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------

app = FastAPI(title="Portfolio Generator Service", version="1.0")


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "portfolio-generator"}


# ---------------------------------------------------------------------
# Portfolio generation
# ---------------------------------------------------------------------

@app.post("/generate", response_model=list[CandidatePortfolio])
def generate(request: PortfolioGenerationRequest) -> list[CandidatePortfolio]:
    """
    Generate deterministic candidate portfolios using a processed
    user signal and a fixed asset-signal snapshot.
    """

    try:
        return generate_portfolios(user_signal=request.user_signal, asset_signals=request.asset_signals)

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":

    print("Starting Portfolio Generator Service")
    uvicorn.run(app, host=UR_PORTFOLIO_GENERATOR_HOST, port=UR_PORTFOLIO_GENERATOR_PORT, access_log=False)