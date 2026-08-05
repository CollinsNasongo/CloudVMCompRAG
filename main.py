"""
Fetch AWS + Azure VM pricing and write both CSVs to OUTPUT_DIR.

Usage:
    python main.py               # both providers, raw pricing only
    python main.py --aws         # AWS pricing only
    python main.py --azure       # Azure pricing only
    python main.py --specs       # Azure specs only (resourceSkus)
    python main.py --compare     # full normalized comparison (pricing + specs, both clouds)
"""

import argparse
import logging

from vms import config
from vms.aws_pricing import fetch_aws_pricing
from vms.azure_pricing import fetch_azure_pricing
from vms.azure_specs import fetch_azure_specs
from vms.comparison import build_comparison

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run(fetch_aws: bool, fetch_azure: bool, fetch_specs: bool, compare: bool):
    if compare:
        df = build_comparison()
        out_path = config.OUTPUT_DIR / "vm_comparison.csv"
        df.to_csv(out_path, index=False)
        logger.info("Comparison: %d rows -> %s", len(df), out_path)
        return

    if fetch_aws:
        logger.info("Fetching AWS pricing...")
        aws_df = fetch_aws_pricing()
        aws_path = config.OUTPUT_DIR / "aws_vm_pricing.csv"
        aws_df.to_csv(aws_path, index=False)
        logger.info("AWS: %d rows -> %s", len(aws_df), aws_path)

    if fetch_azure:
        logger.info("Fetching Azure pricing...")
        azure_df = fetch_azure_pricing()
        azure_path = config.OUTPUT_DIR / "azure_vm_pricing.csv"
        azure_df.to_csv(azure_path, index=False)
        logger.info("Azure: %d rows -> %s", len(azure_df), azure_path)

    if fetch_specs:
        logger.info("Fetching Azure specs...")
        specs_df = fetch_azure_specs()
        specs_path = config.OUTPUT_DIR / "azure_vm_specs.csv"
        specs_df.to_csv(specs_path, index=False)
        logger.info("Azure specs: %d rows -> %s", len(specs_df), specs_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch cloud VM pricing/specs.")
    parser.add_argument("--aws", action="store_true", help="Fetch AWS pricing only")
    parser.add_argument("--azure", action="store_true", help="Fetch Azure pricing only")
    parser.add_argument("--specs", action="store_true", help="Fetch Azure specs only")
    parser.add_argument("--compare", action="store_true", help="Build the full normalized comparison dataset")
    args = parser.parse_args()

    any_flag = args.aws or args.azure or args.specs or args.compare

    run(
        fetch_aws=args.aws or not any_flag,
        fetch_azure=args.azure or not any_flag,
        fetch_specs=args.specs,  # not included in default run - needs Azure SP creds
        compare=args.compare,
    )
