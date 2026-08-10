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


# Azure SKU series -> AWS-style category, so `instance_family` means the same
# thing on both sides. AWS's instanceFamily attribute is category-level
# ('Compute optimized', 'Memory optimized', ...), not a series code, so
# mapping straight from the Azure series letters ('D', 'NC') to that same
# vocabulary is what makes the column comparable rather than just present.
_AZURE_SERIES_TO_CATEGORY = {
    "A": "General purpose",
    "B": "General purpose",
    "D": "General purpose",
    "DC": "General purpose",
    "DS": "General purpose",
    "F": "Compute optimized",
    "FX": "Compute optimized",
    "E": "Memory optimized",
    "EC": "Memory optimized",
    "M": "Memory optimized",
    "L": "Storage optimized",
    "N": "GPU instance",
    "NC": "GPU instance",
    "ND": "GPU instance",
    "NV": "GPU instance",
    "NG": "GPU instance",
    "H": "High performance compute",
    "HB": "High performance compute",
    "HC": "High performance compute",
    "HX": "High performance compute",
}

# Azure's CpuArchitectureType values -> AWS's processorArchitecture values,
# so `architecture` means the same thing after azure_specs.py is merged in.
_AZURE_ARCH_TO_AWS = {
    "x64": "x86_64",
    "Arm64": "arm64",
}


def parse_azure_series(arm_sku_name: str):
    """
    'Standard_D4s_v5' -> 'D'. 'Standard_NC24ads_A100_v4' -> 'NC'.
    Pulls the leading letter run after 'Standard_'/'Basic_' - Azure's raw SKU
    series code. This is NOT the same kind of value as AWS's instance_family
    attribute (see parse_azure_family below); it's closer to the family
    prefix baked into an AWS instance_type ('c5', 'm5').
    """
    if not arm_sku_name:
        return None
    name = re.sub(r"^(Standard_|Basic_)", "", arm_sku_name)
    match = re.match(r"([A-Za-z]+)", name)
    return match.group(1) if match else None


def parse_azure_family(arm_sku_name: str):
    """
    Maps an Azure SKU series code to an AWS-style category
    ('D' -> 'General purpose', 'NC' -> 'GPU instance', ...), so this lines up
    with AWS's instanceFamily attribute, which is category-level rather than
    a series code. Falls back to the raw series code for anything not in the
    lookup table (e.g. newer/unmapped series) rather than returning None.
    """
    series = parse_azure_series(arm_sku_name)
    if series is None:
        return None
    return _AZURE_SERIES_TO_CATEGORY.get(series, series)


def parse_azure_os(product_name: str, sku_name: str = None):
    """
    Azure retail pricing doesn't have a dedicated OS field - it's implied by
    keywords in product_name/sku_name. Licensed distros (Windows, RHEL, SUSE)
    get their own SKUs/meters, same as AWS; unlisted Linux (Ubuntu, CentOS,
    etc.) carries no OS license line item, so it falls back to 'Linux'.
    """
    text = " ".join(filter(None, [product_name, sku_name])).lower()
    if "windows" in text:
        return "Windows"
    if "rhel" in text or "red hat" in text:
        return "RHEL"
    if "sles" in text or "suse" in text:
        return "SUSE"
    return "Linux"


def normalize_architecture(value: str):
    """Maps Azure's CpuArchitectureType values ('x64', 'Arm64') onto AWS's
    processorArchitecture vocabulary ('x86_64', 'arm64')."""
    if not value:
        return value
    return _AZURE_ARCH_TO_AWS.get(value, value)


def memory_to_vcpu_ratio(vcpu, memory_gb):
    try:
        vcpu = float(vcpu)
        memory_gb = float(memory_gb)
        if vcpu == 0:
            return None
        return round(memory_gb / vcpu, 2)
    except (TypeError, ValueError):
        return None
