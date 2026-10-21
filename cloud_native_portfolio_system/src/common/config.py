import os
import math
from pathlib import Path


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MARKET_DATA_DIR = PROJECT_ROOT / "data" / "market_data"

MARKET_TEST_SET_DIR = MARKET_DATA_DIR / "test_sets"
INITIAL_SIGNAL_DIR = MARKET_DATA_DIR / "initial_signals"

VALID_DATASET_SIZES = (
    "small",
    "medium",
    "large",
)

INITIAL_SIGNAL_FILES = {
    "small": INITIAL_SIGNAL_DIR / "signals_small.csv",
    "medium": INITIAL_SIGNAL_DIR / "signals_medium.csv",
    "large": INITIAL_SIGNAL_DIR / "signals_large.csv",
}

MARKET_TEST_SET_FILES = {
    "small": MARKET_TEST_SET_DIR / "md_small.csv",
    "medium": MARKET_TEST_SET_DIR / "md_medium.csv",
    "large": MARKET_TEST_SET_DIR / "md_large.csv",
}


# ---------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------

REDIS_HOST = os.getenv("MD_REDIS_HOST", "localhost") #Checks env var MD_REDIS_HOST, if none use localhost
REDIS_PORT = int(os.getenv("MD_REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("MD_REDIS_DB", "0"))
REDIS_KEY_PREFIX = os.getenv("MD_REDIS_KEY_PREFIX", "md:signal")


# ---------------------------------------------------------------------
# Signal processing
# ---------------------------------------------------------------------

EWMA_ALPHA = float(os.getenv("MD_EWMA_ALPHA", "0.10"))

SYNTHETIC_WORKLOADS = {
    "light": 1_000,
    "medium": 5_000,
    "heavy": 20_000,
}

SYNTHETIC_WORKLOAD_PROFILE = os.getenv("MD_SYNTHETIC_WORKLOAD", "medium").lower()

if SYNTHETIC_WORKLOAD_PROFILE not in SYNTHETIC_WORKLOADS:
    raise ValueError("MD_SYNTHETIC_WORKLOAD must be 'light', 'medium', or 'heavy'")

SYNTHETIC_WORKLOAD_ITERATIONS = (SYNTHETIC_WORKLOADS[SYNTHETIC_WORKLOAD_PROFILE])


# ---------------------------------------------------------------------
# Direct API
# ---------------------------------------------------------------------

DIRECT_API_HOST = os.getenv("MD_DIRECT_API_HOST", "0.0.0.0")
DIRECT_API_PORT = int(os.getenv("MD_DIRECT_API_PORT", "8000"))

# Used by the external market replayer.
DIRECT_API_URL = os.getenv("MD_DIRECT_API_URL", "http://127.0.0.1:8000/market-event")
DIRECT_API_TIMEOUT_SECONDS = float(os.getenv("MD_DIRECT_API_TIMEOUT_SECONDS", "30"))


# ---------------------------------------------------------------------
# NATS / event-driven architecture
# ---------------------------------------------------------------------

NATS_URL = os.getenv("MD_NATS_URL", "nats://localhost:4222")
NATS_STREAM = os.getenv("MD_NATS_STREAM", "MARKET_DATA")
NATS_SUBJECT = os.getenv("MD_NATS_SUBJECT", "market.events")
NATS_CONSUMER = os.getenv("MD_NATS_CONSUMER", "signal-processor")

NATS_STREAM_STORAGE = os.getenv("MD_NATS_STREAM_STORAGE", "memory").lower()
if NATS_STREAM_STORAGE not in ("memory", "file"):
    raise ValueError("MD_NATS_STREAM_STORAGE must be 'memory' or 'file'")

NATS_FETCH_BATCH_SIZE = int(os.getenv("MD_NATS_FETCH_BATCH_SIZE", "1"))
NATS_FETCH_TIMEOUT_SECONDS = float(os.getenv("MD_NATS_FETCH_TIMEOUT_SECONDS", "1.0"))

NATS_ACK_WAIT_SECONDS = float(os.getenv("MD_NATS_ACK_WAIT_SECONDS", "60"))
NATS_MAX_ACK_PENDING = int(os.getenv("MD_NATS_MAX_ACK_PENDING", "1000"))

NATS_CONNECT_TIMEOUT_SECONDS = float(os.getenv("MD_NATS_CONNECT_TIMEOUT_SECONDS", "5"))
NATS_CYCLE_POLL_INTERVAL_SECONDS = float(os.getenv("MD_NATS_CYCLE_POLL_INTERVAL_SECONDS", "0.05"))
NATS_CYCLE_COMPLETION_TIMEOUT_SECONDS = float(os.getenv("MD_NATS_CYCLE_COMPLETION_TIMEOUT_SECONDS", "120"))

NATS_METRICS_SUBJECT = os.getenv("MD_NATS_METRICS_SUBJECT", "market.metrics.processing")
NATS_HEADER_CYCLE_START_NS = "VT-Cycle-Start-Ns"
NATS_HEADER_PUBLISHED_AT_NS = "VT-Published-At-Ns"


# ---------------------------------------------------------------------
# User-request processing
# ---------------------------------------------------------------------

USER_REQUEST_DATA_DIR = PROJECT_ROOT / "data" / "user_request_data"
USER_REQUEST_FILE = (USER_REQUEST_DATA_DIR / "user_requests.csv")

USER_TARGET_RETURN_MIN = float(os.getenv("USER_TARGET_RETURN_MIN","-0.0")) # return signals min/max
USER_TARGET_RETURN_MAX = float(os.getenv("USER_TARGET_RETURN_MAX", "0.003"))

USER_TARGET_RISK_MIN = float(os.getenv("USER_TARGET_RISK_MIN", "0.005")) # risk signals min/max
USER_TARGET_RISK_MAX = float(os.getenv("USER_TARGET_RISK_MAX", "0.025"))

# ---------------------------------------------------------------------
# User portfolio generation
# ---------------------------------------------------------------------

USER_ASSET_UNIVERSE_SIZE = int(os.getenv("USER_ASSET_UNIVERSE_SIZE", "100")) # number of assets to choose from
USER_PORTFOLIO_SIZE = int(os.getenv("USER_PORTFOLIO_SIZE", "10")) # number of assets in each portfolio
USER_CANDIDATE_PORTFOLIOS = int(os.getenv("USER_CANDIDATE_PORTFOLIOS", "10")) # number of portfolios produced


# ---------------------------------------------------------------------
# Portfolio evaluation
# ---------------------------------------------------------------------

USER_RETURN_SCORE_WEIGHT = float(os.getenv("USER_RETURN_SCORE_WEIGHT", "0.35"))
USER_RISK_SCORE_WEIGHT = float(os.getenv("USER_RISK_SCORE_WEIGHT", "0.45"))
USER_DIVERSIFICATION_SCORE_WEIGHT = float(os.getenv("USER_DIVERSIFICATION_SCORE_WEIGHT", "0.20"))
USER_EVALUATION_WEIGHT_TOTAL = (USER_RETURN_SCORE_WEIGHT + USER_RISK_SCORE_WEIGHT + USER_DIVERSIFICATION_SCORE_WEIGHT)

if not math.isclose(USER_EVALUATION_WEIGHT_TOTAL, 1.0, abs_tol=1e-9,):
    raise ValueError("Portfolio evaluation weights must sum to 1.0")


# ---------------------------------------------------------------------
# User-request monolith API
# ---------------------------------------------------------------------

UR_MONOLITH_API_HOST = os.getenv("UR_MONOLITH_API_HOST", "0.0.0.0")
UR_MONOLITH_API_PORT = int(os.getenv("UR_MONOLITH_API_PORT", "8100"))
# Used later by the external user-request load generator.
UR_MONOLITH_API_URL = os.getenv("UR_MONOLITH_API_URL", "http://127.0.0.1:8100/portfolio")

UR_API_TIMEOUT_SECONDS = float(os.getenv("UR_API_TIMEOUT_SECONDS", "30"))


# ---------------------------------------------------------------------
# User-request microservices
# ---------------------------------------------------------------------

UR_COORDINATOR_HOST = os.getenv("UR_COORDINATOR_HOST", "0.0.0.0")
UR_COORDINATOR_PORT = int(os.getenv("UR_COORDINATOR_PORT", "8200"))
UR_COORDINATOR_URL = os.getenv("UR_COORDINATOR_URL", "http://127.0.0.1:8200/portfolio")

UR_SERVICE_TIMEOUT_SECONDS = float(os.getenv("UR_SERVICE_TIMEOUT_SECONDS", "30"))
UR_SERVICE_MAX_CONNECTIONS = int(os.getenv("UR_SERVICE_MAX_CONNECTIONS", "100"))
UR_SERVICE_MAX_KEEPALIVE_CONNECTIONS = int(os.getenv("UR_SERVICE_MAX_KEEPALIVE_CONNECTIONS", "20"))

UR_REQUEST_PROCESSOR_HOST = os.getenv("UR_REQUEST_PROCESSOR_HOST", "0.0.0.0")
UR_REQUEST_PROCESSOR_PORT = int(os.getenv("UR_REQUEST_PROCESSOR_PORT", "8201"))
UR_REQUEST_PROCESSOR_URL = os.getenv("UR_REQUEST_PROCESSOR_URL", "http://127.0.0.1:8201/process")

UR_PORTFOLIO_GENERATOR_HOST = os.getenv("UR_PORTFOLIO_GENERATOR_HOST", "0.0.0.0")
UR_PORTFOLIO_GENERATOR_PORT = int(os.getenv("UR_PORTFOLIO_GENERATOR_PORT", "8202"))
UR_PORTFOLIO_GENERATOR_URL = os.getenv("UR_PORTFOLIO_GENERATOR_URL", "http://127.0.0.1:8202/generate")

UR_PORTFOLIO_EVALUATOR_HOST = os.getenv("UR_PORTFOLIO_EVALUATOR_HOST", "0.0.0.0")
UR_PORTFOLIO_EVALUATOR_PORT = int(os.getenv("UR_PORTFOLIO_EVALUATOR_PORT", "8203"))
UR_PORTFOLIO_EVALUATOR_URL = os.getenv("UR_PORTFOLIO_EVALUATOR_URL", "http://127.0.0.1:8203/evaluate")


# ---------------------------------------------------------------------
# User-request load generator
# ---------------------------------------------------------------------

UR_LOAD_DEFAULT_REQUESTS = int(os.getenv("UR_LOAD_DEFAULT_REQUESTS", "100"))
UR_LOAD_DEFAULT_CONCURRENCY = int(os.getenv("UR_LOAD_DEFAULT_CONCURRENCY", "1"))


# ---------------------------------------------------------------------
# Experiment 4 data
# ---------------------------------------------------------------------

EXPERIMENT_4_DATA_DIR = (PROJECT_ROOT / "data" / "experiment_4")
EVALUATOR_REQUEST_FILE = (EXPERIMENT_4_DATA_DIR / "portfolio_evaluator_request.json")

# ---------------------------------------------------------------------
# Experiment 4 workload
# ---------------------------------------------------------------------

EXPERIMENT_4_IDLE_SECONDS = float(os.getenv("EXP4_IDLE_SECONDS", "5"))
EXPERIMENT_4_BURST_REQUESTS = int(os.getenv("EXP4_BURST_REQUESTS", "100"))
EXPERIMENT_4_BURST_CONCURRENCY = int(os.getenv("EXP4_BURST_CONCURRENCY", "10"))
EXPERIMENT_4_BURSTS = int(os.getenv("EXP4_BURSTS", "2"))

# ---------------------------------------------------------------------
# Experiment results
# ---------------------------------------------------------------------

EXPERIMENT_RESULTS_DIR = (PROJECT_ROOT / "results" / "experiments")
