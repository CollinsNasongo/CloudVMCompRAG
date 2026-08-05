"""Small shared helpers used by both provider modules."""

import re
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter, Retry

from vms import config


def get_retrying_session() -> requests.Session:
    """
    A requests.Session with exponential backoff on connection errors,
    5xx responses, and throttling (429). Used by the Azure module directly;
    boto3 gets its own retry config since it doesn't use `requests`.
    """
    session = requests.Session()
    retries = Retry(
        total=config.MAX_RETRIES,
        backoff_factor=1.5,  # 0s, 1.5s, 3s, 6s, 12s...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session


def parse_memory_to_gb(memory_str):
    """'8 GiB' -> 8.0. Returns None if memory_str is missing/unparseable."""
    if not memory_str:
        return None
    match = re.search(r"([\d.]+)", memory_str)
    if match:
        return float(match.group(1))
    return None


def utc_timestamp() -> str:
    """ISO-8601 UTC timestamp, stamped onto every row for historical snapshots."""
    return datetime.now(timezone.utc).isoformat()


# ---- Lean-schema derivation helpers ----

# AWS burstable families are unambiguous by instance-type prefix.
_AWS_BURSTABLE_PREFIXES = ("t1.", "t2.", "t3.", "t3a.", "t4g.")

# Azure burstable is the B-series. armSkuName looks like "Standard_B2s".
_AZURE_BURSTABLE_PREFIX = "Standard_B"


def is_burstable_aws(instance_type: str) -> bool:
    if not instance_type:
        return False
    return instance_type.lower().startswith(_AWS_BURSTABLE_PREFIXES)


def is_burstable_azure(arm_sku_name: str) -> bool:
    if not arm_sku_name:
        return False
    return arm_sku_name.startswith(_AZURE_BURSTABLE_PREFIX)


def parse_azure_family(arm_sku_name: str):
    """
    'Standard_D4s_v5' -> 'D'. 'Standard_NC24ads_A100_v4' -> 'NC'.
    Pulls the leading letter run after 'Standard_'/'Basic_', which is the
    closest Azure equivalent to AWS's instance_family (e.g. 'm5', 'c6g').
    """
    if not arm_sku_name:
        return None
    name = re.sub(r"^(Standard_|Basic_)", "", arm_sku_name)
    match = re.match(r"([A-Za-z]+)", name)
    return match.group(1) if match else None


def parse_azure_os(product_name: str, sku_name: str = None):
    """
    Azure retail pricing doesn't have a dedicated OS field - it's implied by
    absence/presence of 'Windows' in product_name/sku_name. No 'Windows' in
    either usually means Linux (Azure's default, unlisted explicitly).
    """
    text = " ".join(filter(None, [product_name, sku_name]))
    return "Windows" if "windows" in text.lower() else "Linux"


def memory_to_vcpu_ratio(vcpu, memory_gb):
    try:
        vcpu = float(vcpu)
        memory_gb = float(memory_gb)
        if vcpu == 0:
            return None
        return round(memory_gb / vcpu, 2)
    except (TypeError, ValueError):
        return None
