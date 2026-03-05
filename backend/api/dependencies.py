from __future__ import annotations

from connectors.unified import UnifiedConnector
from executor.execution_engine import ExecutionEngine
from scanner.opportunity_scanner import OpportunityScanner

# Singleton instances — initialized in main.py lifespan
_connector: UnifiedConnector | None = None
_scanner: OpportunityScanner | None = None
_executor: ExecutionEngine | None = None


def init_services() -> None:
    global _connector, _scanner, _executor
    _connector = UnifiedConnector()
    _scanner = OpportunityScanner(_connector)
    _executor = ExecutionEngine(_connector)


def get_connector() -> UnifiedConnector:
    if _connector is None:
        raise RuntimeError("Connector not initialized")
    return _connector


def get_scanner() -> OpportunityScanner:
    if _scanner is None:
        raise RuntimeError("Scanner not initialized")
    return _scanner


def get_executor() -> ExecutionEngine:
    if _executor is None:
        raise RuntimeError("Executor not initialized")
    return _executor
