import uvicorn
from fastapi import FastAPI

from src.common.config import UR_REQUEST_PROCESSOR_HOST, UR_REQUEST_PROCESSOR_PORT
from src.common.models import UserRequest, UserSignal
from src.ur_pipeline.request_processor import process_user_request


# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------

app = FastAPI(title="User Request Processor Service", version="1.0")


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "request-processor"}


# ---------------------------------------------------------------------
# Request processing
# ---------------------------------------------------------------------

@app.post("/process", response_model=UserSignal)
def process_request(request: UserRequest) -> UserSignal:
    return process_user_request(request)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting User Request Processor Service")
    uvicorn.run(app, host=UR_REQUEST_PROCESSOR_HOST, port=UR_REQUEST_PROCESSOR_PORT, access_log=False)