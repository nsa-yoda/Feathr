"""Reviewer-facing command line entry points."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from typing import Any, cast

from pymongo import AsyncMongoClient

from event_platform.core.logging import configure_logging
from event_platform.core.settings import ServiceSettings, SettingsStartupError, load_settings
from event_platform.search.rebuild import main as rebuild_main
from event_platform.storage.bootstrap import (
    StorageCollections,
    StorageDatabase,
    StorageSchemaError,
    bootstrap_storage,
    verify_storage,
)

logger = logging.getLogger("event_platform.storage.bootstrap")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="event_platform")
    subparsers = parser.add_subparsers(dest="domain", required=True)
    search = subparsers.add_parser("search")
    search_subparsers = search.add_subparsers(dest="command", required=True)
    rebuild = search_subparsers.add_parser("rebuild")
    rebuild.add_argument("--confirm", action="store_true")
    status = search_subparsers.add_parser("rebuild-status")
    status.add_argument("--rebuild-id")
    storage = subparsers.add_parser("storage")
    storage_subparsers = storage.add_subparsers(dest="command", required=True)
    storage_subparsers.add_parser("bootstrap")
    storage_subparsers.add_parser("verify")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.domain == "storage":
        return storage_main(args.command)
    if args.command == "rebuild":
        rebuild_args = ["run"] + (["--confirm"] if args.confirm else [])
    else:
        rebuild_args = ["status"]
        if args.rebuild_id:
            rebuild_args.extend(["--rebuild-id", args.rebuild_id])
    return rebuild_main(rebuild_args)


def storage_main(operation: str) -> int:
    try:
        settings = load_settings()
    except SettingsStartupError:
        configure_logging("INFO")
        logger.error(
            "storage command configuration failed",
            extra={
                "event": "storage.configuration_failed",
                "classification": "configuration_invalid",
            },
        )
        return 2
    configure_logging(settings.log_level)
    if settings.mongo_url is None:
        logger.error(
            "storage command requires canonical MongoDB",
            extra={
                "event": "storage.configuration_failed",
                "classification": "mongo_url_missing",
            },
        )
        return 2
    return asyncio.run(_run_storage_operation(operation, settings))


async def _run_storage_operation(operation: str, settings: ServiceSettings) -> int:
    timeout_ms = int(settings.dependency_timeout_seconds * 1000)
    client: AsyncMongoClient[Any] = AsyncMongoClient(
        settings.mongo_url,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=timeout_ms,
    )
    try:
        database = client[settings.mongo_database]
        storage_database = cast(StorageDatabase, database)
        collections = StorageCollections(events=settings.mongo_collection)
        if operation == "bootstrap":
            result = await bootstrap_storage(
                storage_database,
                collections=collections,
            )
        elif operation == "verify":
            result = await verify_storage(storage_database, collections=collections)
        else:
            raise ValueError("unsupported storage operation")
    except StorageSchemaError as error:
        logger.error(
            "storage operation failed",
            extra={
                "event": "storage.operation_failed",
                "operation": operation,
                "classification": error.classification,
                "collection": error.collection,
                "index": error.index,
            },
        )
        return 1
    finally:
        await client.close()
    logger.info(
        "storage operation complete",
        extra={
            "event": "storage.operation_complete",
            "operation": operation,
            "schema_version": result.schema_version,
            "manifest_fingerprint": result.manifest_fingerprint,
            "verified_indexes": result.verified_indexes,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
