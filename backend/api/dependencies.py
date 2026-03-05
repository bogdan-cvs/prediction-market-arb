from __future__ import annotations

from connectors.unified import UnifiedConnector
from scanner.opportunity_scanner import OpportunityScanner

# Singleton instances — initialized in main.py lifespan
_connector: UnifiedConnector | None = None
_scanner: OpportunityScanner | None = None
_executor = None  # Will be ExecutionEngine, set in Step 7


def init_services() -> None:
    global _connector, _scanner
    _connector = UnifiedConnector()
    _scanner = OpportunityScanner(_connector)


def get_connector() -> UnifiedConnector:
    if _connector is None:
        raise RuntimeError("Connector not initialized")
    return _connector


def get_scanner() -> OpportunityScanner:
    if _scanner is None:
        raise RuntimeError("Scanner not initialized")
    return _scanner


def set_executor(executor) -> None:
    global _executor
    _executor = executor


def get_executor():
    if _executor is None:
        raise RuntimeError("Executor not initialized")
    return _executor
