"""
Azure VM spec extraction (Compute resourceSkus API).

Unlike azure_pricing.py, this hits an authenticated ARM management endpoint -
the Retail Prices API has no concept of vCPU/memory. Requires a service
principal with at least Reader on the subscription (see config.py / .env.example
for the az CLI command to create one).

Returns one row per (armSkuName, region) with vcpu/memory/architecture pulled
out of the SKU's `capabilities` list, which is a flat list of {name, value}
pairs rather than a fixed schema - so most of this module is just picking the
capability names we care about out of that list.
"""

import logging

import pandas as pd
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient

from vms import config
from vms.utils import utc_timestamp

logger = logging.getLogger(__name__)

# The capability list per SKU can have 30+ entries; we only care about these.
_WANTED_CAPABILITIES = {
    "vCPUs": "vcpu",
    "MemoryGB": "memory_gb",
    "CpuArchitectureType": "architecture",
    "MaxResourceVolumeMB": "local_storage_mb",
    "MaxDataDiskCount": "max_data_disks",
    "MaxNetworkInterfaces": "max_nics",
    "PremiumIO": "premium_storage_supported",
    "AcceleratedNetworkingEnabled": "accelerated_networking_supported",
}


def _get_client() -> ComputeManagementClient:
    missing = [
        name
        for name, val in [
            ("AZURE_TENANT_ID", config.AZURE_TENANT_ID),
            ("AZURE_CLIENT_ID", config.AZURE_CLIENT_ID),
            ("AZURE_CLIENT_SECRET", config.AZURE_CLIENT_SECRET),
            ("AZURE_SUBSCRIPTION_ID", config.AZURE_SUBSCRIPTION_ID),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            "Azure spec lookup needs a service principal. Missing from .env: "
            + ", ".join(missing)
        )

    credential = ClientSecretCredential(
        tenant_id=config.AZURE_TENANT_ID,
        client_id=config.AZURE_CLIENT_ID,
        client_secret=config.AZURE_CLIENT_SECRET,
    )
    return ComputeManagementClient(credential, config.AZURE_SUBSCRIPTION_ID)


def _extract_capabilities(sku) -> dict:
    row = {v: None for v in _WANTED_CAPABILITIES.values()}
    for cap in sku.capabilities or []:
        field = _WANTED_CAPABILITIES.get(cap.name)
        if field:
            row[field] = cap.value
    return row


def fetch_azure_specs(region: str = None) -> pd.DataFrame:
    """
    Fetch vCPU/memory/architecture/etc. for every VM SKU available in `region`.
    One row per armSkuName - this is meant to be joined onto azure_pricing.py's
    output on (instance_type, region).
    """
    region = region or config.AZURE_REGION
    client = _get_client()
    extracted_at = utc_timestamp()

    rows = []
    # resourceSkus is subscription-wide; filter to the region we priced, and
    # to VM SKUs only (the endpoint also returns disks, availability sets, etc.)
    skus = client.resource_skus.list(filter=f"location eq '{region}'")

    for sku in skus:
        if sku.resource_type != "virtualMachines":
            continue

        # Skus restricted/unavailable in this region for the caller's subscription
        # (quota, offer type, etc.) still show up - skip anything explicitly restricted.
        if sku.restrictions:
            restricted_here = any(
                region in (r.restriction_info.locations or [])
                for r in sku.restrictions
                if r.restriction_info
            )
            if restricted_here:
                continue

        capabilities = _extract_capabilities(sku)

        rows.append(
            {
                "instance_type": sku.name,  # armSkuName, matches azure_pricing.py's instance_type
                "region": region,
                "family": sku.family,
                **capabilities,
                "extracted_at": extracted_at,
            }
        )

    df = pd.DataFrame(rows).drop_duplicates(subset=["instance_type", "region"])
    logger.info("Azure specs: %d SKUs fetched for %s", len(df), region)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = fetch_azure_specs()
    out_path = config.OUTPUT_DIR / "azure_vm_specs.csv"
    df.to_csv(out_path, index=False)
    print(f"Azure specs: {len(df)} rows -> {out_path}")
