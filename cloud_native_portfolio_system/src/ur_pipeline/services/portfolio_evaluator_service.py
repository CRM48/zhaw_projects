import uvicorn
from fastapi import FastAPI, HTTPException

from src.common.config import UR_PORTFOLIO_EVALUATOR_HOST, UR_PORTFOLIO_EVALUATOR_PORT
from src.common.models import EvaluatedPortfolio, PortfolioEvaluationRequest
from src.ur_pipeline.portfolio_evaluator import evaluate_portfolios


# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------

app = FastAPI(title="Portfolio Evaluator Service", version="1.0")


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "portfolio-evaluator"}


# ---------------------------------------------------------------------
# Portfolio evaluation
# ---------------------------------------------------------------------

@app.post("/evaluate", response_model=list[EvaluatedPortfolio])
def evaluate(request: PortfolioEvaluationRequest) -> list[EvaluatedPortfolio]:
    """
    Evaluate candidate portfolios against a processed user signal
    using the supplied asset-signal snapshot.
    """

    try:
        return evaluate_portfolios(user_signal=request.user_signal, portfolios=request.portfolios, asset_signals=request.asset_signals)

    except KeyError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting Portfolio Evaluator Service")
    uvicorn.run(app, host=UR_PORTFOLIO_EVALUATOR_HOST, port=UR_PORTFOLIO_EVALUATOR_PORT, access_log=False)
    