"""
Central config, loaded from a .env file (or real env vars) via python-dotenv.

Nothing in here is required for the Azure script (it's a public API), but
AWS credentials are picked up here so they never get typed into the
provider modules directly. If AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are
left unset, boto3 falls back to its normal credential chain (profile,
IAM role, etc.) - that's the recommended path for anything beyond local dev.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of current working directory
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# ---- AWS ----
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")  # optional, may be None
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")  # optional, may be None
AWS_REGION = os.getenv("AWS_PRICING_API_REGION", "us-east-1")  # pricing API endpoint region, NOT the priced region
AWS_LOCATION_FILTER = os.getenv("AWS_LOCATION_FILTER", "US East (N. Virginia)")

# ---- Azure ----
AZURE_REGION = os.getenv("AZURE_REGION", "eastus")
AZURE_CURRENCY = os.getenv("AZURE_CURRENCY", "USD")

# Required only for azure_specs.py (resourceSkus API needs an authenticated
# ARM call - the Retail Prices API used by azure_pricing.py does not).
# Create a service principal with Reader on the subscription:
#   az ad sp create-for-rbac --role Reader --scopes /subscriptions/<sub-id>
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
AZURE_SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID")

# ---- Shared ----
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", ROOT_DIR / "output"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
