"""
Azure VM retail pricing extraction (Retail Prices API).

`priceType eq 'Consumption'` is applied deliberately so this stays
comparable to the AWS OnDemand-only extraction - without it, `Items`
includes Reservation and DevTestConsumption rows mixed in with on-demand.

Note: this API does not return vCPU/memory per SKU (unlike AWS). If you
need specs joined in, that has to come from a second source keyed on
`armSkuName` (e.g. Azure's `resourceSkus` API or a static VM-series table).
"""

import logging

import pandas as pd

from vms import config
from vms.utils import get_retrying_session, parse_azure_family, parse_azure_os, utc_timestamp

logger = logging.getLogger(__name__)

BASE_URL = "https://prices.azure.com/api/retail/prices"


def fetch_azure_pricing(region: str = None, currency: str = None) -> pd.DataFrame:
    """Fetch all Azure Virtual Machines retail prices for a given region/currency."""
    region = region or config.AZURE_REGION
    currency = currency or config.AZURE_CURRENCY
    extracted_at = utc_timestamp()

    url = (
        f"{BASE_URL}?$filter=serviceName eq 'Virtual Machines' "
        f"and armRegionName eq '{region}' "
        f"and priceType eq 'Consumption'"
        f"&currencyCode={currency}"
    )

    session = get_retrying_session()
    products = []
    page = 0

    while url:
        page += 1
        logger.info("Azure page %d: %s", page, url)

        response = session.get(url, timeout=config.REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()

        for item in data.get("Items", []):
            arm_sku_name = item.get("armSkuName")
            product_name = item.get("productName")
            sku_name = item.get("skuName")

            products.append(
                {
                    "provider": "Azure",
                    "region": item.get("armRegionName"),
                    "location": item.get("location"),
                    "instance_type": arm_sku_name,
                    "instance_family": parse_azure_family(arm_sku_name),
                    "vcpu": None,
                    "memory_gb": None,
                    "storage": None,
                    "processor": None,
                    "processor_architecture": None,
                    "operating_system": parse_azure_os(product_name, sku_name),
                    "tenancy": None,
                    "pricing_model": "Consumption",
                    "price": item.get("retailPrice"),
                    "currency": item.get("currencyCode"),
                    "unit": item.get("unitOfMeasure"),
                    "sku_id": item.get("skuId"),
                    "meter_id": item.get("meterId"),
                    "product_name": product_name,
                    "description": None,
                    "effective_start_date": item.get("effectiveStartDate"),
                    "sku_name": sku_name,
                    "meter_name": item.get("meterName"),
                    "service_name": item.get("serviceName"),
                    "service_family": item.get("serviceFamily"),
                    "price_type": item.get("type"),
                    "unit_price": item.get("unitPrice"),
                    "product_id": item.get("productId"),
                    "service_id": item.get("serviceId"),
                    "is_primary_meter_region": item.get("isPrimaryMeterRegion"),
                    "reservation_term": item.get("reservationTerm"),
                    "extracted_at": extracted_at,
                    "network_performance": None,
                    "usage_type": None,
                    "operation": None,
                    "license_model": None,
                    "preinstalled_software": None,
                    "capacity_status": None,
                }
            )

        logger.info("Azure page %d fetched, %d rows so far", page, len(products))
        url = data.get("NextPageLink")

    df = pd.DataFrame(products).drop_duplicates()
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = fetch_azure_pricing()
    out_path = config.OUTPUT_DIR / "azure_vm_pricing.csv"
    df.to_csv(out_path, index=False)
    print(f"Azure: {len(df)} rows -> {out_path}")
