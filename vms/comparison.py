"""
Builds the cross-cloud comparison dataset: normalizes AWS pricing and
Azure pricing+specs into one shared "lean schema" so they can be
filtered/sorted/joined together.

Lean schema columns:
    provider, region, instance_type, instance_family, vcpu, memory_gb,
    memory_to_vcpu_ratio, architecture, is_burstable, operating_system,
    hourly_price, currency, extracted_at
"""

import logging

import pandas as pd

from vms.aws_pricing import fetch_aws_pricing
from vms.azure_pricing import fetch_azure_pricing
from vms.azure_specs import fetch_azure_specs
from vms.utils import is_burstable_aws, is_burstable_azure, memory_to_vcpu_ratio

logger = logging.getLogger(__name__)

LEAN_COLUMNS = [
    "provider",
    "region",
    "instance_type",
    "instance_family",
    "vcpu",
    "memory_gb",
    "memory_to_vcpu_ratio",
    "local_storage_mb",
    "architecture",
    "is_burstable",
    "operating_system",
    "hourly_price",
    "currency",
    "extracted_at",
]


def normalize_aws(aws_df: pd.DataFrame) -> pd.DataFrame:
    df = aws_df.copy()
    df["memory_to_vcpu_ratio"] = df.apply(
        lambda r: memory_to_vcpu_ratio(r.get("vcpu"), r.get("memory_gb")), axis=1
    )
    df["is_burstable"] = df["instance_type"].apply(is_burstable_aws)
    # AWS's processor_architecture values: 'x86_64', 'arm64', 'i386'
    df["architecture"] = df["processor_architecture"]
    df["hourly_price"] = df["price"]
    # AWS only exposes local storage as a free-text description ('storage'),
    # not a comparable number - leave unset rather than guess-parsing it.
    df["local_storage_mb"] = None
    return df[LEAN_COLUMNS]


def normalize_azure(azure_pricing_df: pd.DataFrame, azure_specs_df: pd.DataFrame) -> pd.DataFrame:
    df = azure_pricing_df.merge(
        azure_specs_df[["instance_type", "region", "vcpu", "memory_gb", "architecture", "local_storage_mb"]],
        on=["instance_type", "region"],
        how="left",
        # pricing rows can have multiple meters (e.g. Windows/Linux, low-priority)
        # per SKU; specs are 1 row per SKU, so this is intentionally many-to-one
        validate="many_to_one",
    )

    unmatched = df["vcpu"].isna().sum()
    if unmatched:
        logger.warning(
            "%d/%d Azure pricing rows had no matching spec row (instance_type/region mismatch)",
            unmatched,
            len(df),
        )

    df["memory_to_vcpu_ratio"] = df.apply(
        lambda r: memory_to_vcpu_ratio(r.get("vcpu"), r.get("memory_gb")), axis=1
    )
    df["is_burstable"] = df["instance_type"].apply(is_burstable_azure)
    df["hourly_price"] = df["price"]
    return df[LEAN_COLUMNS]


def build_comparison(region_aws: str = None, region_azure: str = None) -> pd.DataFrame:
    """Fetch everything fresh and return the combined, normalized comparison DataFrame."""
    logger.info("Fetching AWS pricing...")
    aws_df = fetch_aws_pricing(location=region_aws)

    logger.info("Fetching Azure pricing...")
    azure_pricing_df = fetch_azure_pricing(region=region_azure)

    logger.info("Fetching Azure specs...")
    azure_specs_df = fetch_azure_specs(region=region_azure)

    combined = pd.concat(
        [normalize_aws(aws_df), normalize_azure(azure_pricing_df, azure_specs_df)],
        ignore_index=True,
    )
    logger.info("Comparison dataset: %d rows (%d AWS, %d Azure)",
                len(combined), (combined["provider"] == "AWS").sum(), (combined["provider"] == "Azure").sum())
    return combined


if __name__ == "__main__":
    import logging as _logging
    from vms import config

    _logging.basicConfig(level=_logging.INFO)
    df = build_comparison()
    out_path = config.OUTPUT_DIR / "vm_comparison.csv"
    df.to_csv(out_path, index=False)
    print(f"Comparison: {len(df)} rows -> {out_path}")
