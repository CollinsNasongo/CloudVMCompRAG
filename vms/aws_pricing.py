"""
AWS EC2 on-demand pricing extraction (Pricing API, us-east-1 endpoint).

Only OnDemand terms are collected on purpose - this mirrors the
`priceType eq 'Consumption'` filter applied on the Azure side, so the two
CSVs stay comparable rather than silently mixing on-demand with reserved
pricing.
"""

import json
import logging

import boto3
import pandas as pd
from botocore.config import Config as BotoConfig

from vms import config
from vms.utils import parse_memory_to_gb, utc_timestamp

logger = logging.getLogger(__name__)


def _make_client():
    # Only pass explicit keys if they're actually set; otherwise let boto3
    # fall back to its default credential chain (env, profile, IAM role).
    kwargs = {
        "region_name": config.AWS_REGION,
        "config": BotoConfig(retries={"max_attempts": config.MAX_RETRIES, "mode": "adaptive"}),
    }
    if config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = config.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = config.AWS_SECRET_ACCESS_KEY

    return boto3.client("pricing", **kwargs)


def fetch_aws_pricing(location: str = None) -> pd.DataFrame:
    """Fetch all AWS EC2 on-demand pricing rows for a given `location` filter value."""
    location = location or config.AWS_LOCATION_FILTER
    client = _make_client()
    extracted_at = utc_timestamp()

    products = []
    next_token = None
    page = 0

    while True:
        page += 1
        params = {
            "ServiceCode": "AmazonEC2",
            "Filters": [
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Compute Instance"},
            ],
            "MaxResults": 100,
        }
        if next_token:
            params["NextToken"] = next_token

        response = client.get_products(**params)

        for item in response.get("PriceList", []):
            product = json.loads(item)
            product_info = product.get("product", {})
            attributes = product_info.get("attributes", {})
            terms = product.get("terms", {}).get("OnDemand", {})

            for term_data in terms.values():
                for dimension in term_data.get("priceDimensions", {}).values():
                    price_per_unit = dimension.get("pricePerUnit", {})
                    price = price_per_unit.get("USD")

                    if price is None or price == "":
                        continue

                    products.append(
                        {
                            "provider": "AWS",
                            "region": attributes.get("location"),
                            "location": attributes.get("location"),
                            "instance_type": attributes.get("instanceType"),
                            "instance_family": attributes.get("instanceFamily"),
                            "vcpu": attributes.get("vcpu"),
                            "memory_gb": parse_memory_to_gb(attributes.get("memory")),
                            "storage": attributes.get("storage"),
                            "processor": attributes.get("physicalProcessor"),
                            "processor_architecture": attributes.get("processorArchitecture"),
                            "operating_system": attributes.get("operatingSystem"),
                            "tenancy": attributes.get("tenancy"),
                            "pricing_model": "OnDemand",
                            "price": float(price),
                            "currency": "USD",
                            "unit": dimension.get("unit"),
                            "sku_id": product_info.get("sku"),
                            "meter_id": None,
                            "product_name": None,
                            "description": dimension.get("description"),
                            "effective_start_date": None,
                            "sku_name": None,
                            "meter_name": None,
                            "service_name": "AmazonEC2",
                            "service_family": product_info.get("productFamily"),
                            "price_type": None,
                            "unit_price": None,
                            "product_id": None,
                            "service_id": None,
                            "is_primary_meter_region": None,
                            "reservation_term": None,
                            "extracted_at": extracted_at,
                            "network_performance": attributes.get("networkPerformance"),
                            "usage_type": attributes.get("usageType"),
                            "operation": attributes.get("operation"),
                            "license_model": attributes.get("licenseModel"),
                            "preinstalled_software": attributes.get("preInstalledSw"),
                            "capacity_status": attributes.get("capacitystatus"),
                        }
                    )

        logger.info("AWS page %d fetched, %d rows so far", page, len(products))

        next_token = response.get("NextToken")
        if not next_token:
            break

    df = pd.DataFrame(products).drop_duplicates()
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = fetch_aws_pricing()
    out_path = config.OUTPUT_DIR / "aws_vm_pricing.csv"
    df.to_csv(out_path, index=False)
    print(f"AWS: {len(df)} rows -> {out_path}")