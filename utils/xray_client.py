"""
xray_client.py
==============
Jira Xray REST API client for uploading pytest/Behave test results.

Parses JUnit XML produced by pytest (--junitxml) and pushes execution
results to Jira Xray, automatically linking tests to requirements.

Author : Rakesh Aragodi
"""

from __future__ import annotations
import os
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import requests

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

XRAY_BASE_URL   = os.getenv("JIRA_BASE_URL", "https://your-jira.atlassian.net")
XRAY_CLIENT_ID  = os.getenv("XRAY_CLIENT_ID", "")
XRAY_CLIENT_SECRET = os.getenv("XRAY_CLIENT_SECRET", "")
JIRA_PROJECT    = os.getenv("JIRA_PROJECT_KEY", "BCM")


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    """Single test result to be uploaded."""
    test_key:    str           # Jira Xray test issue key  e.g. "BCM-101"
    status:      str           # "PASS" | "FAIL" | "ABORTED"
    comment:     str = ""
    duration_ms: int = 0
    evidence:    list[dict] = field(default_factory=list)  # screenshots / logs


@dataclass
class ExecutionPayload:
    """Xray test execution payload."""
    plan_key:    str           # Jira test plan key e.g. "BCM-50"
    summary:     str
    results:     list[TestResult]
    started_at:  str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ──────────────────────────────────────────────────────────────────────
# Xray client
# ──────────────────────────────────────────────────────────────────────

class XrayClient:
    """
    Jira Xray Cloud REST API v2 client.

    Example usage:
        client = XrayClient()
        results = XrayClient.parse_junit_xml("reports/results.xml")
        execution_key = client.upload_results(
            plan_key="BCM-50",
            summary="Nightly BCM Regression — 2024-11-28",
            results=results,
        )
        print(f"Execution created: {execution_key}")
    """

    _AUTH_URL = "https://xray.cloud.getxray.app/api/v2/authenticate"
    _IMPORT_URL = "https://xray.cloud.getxray.app/api/v2/import/execution"

    def __init__(
        self,
        client_id: str = XRAY_CLIENT_ID,
        client_secret: str = XRAY_CLIENT_SECRET,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: Optional[str] = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> str:
        """Obtain a Bearer token from Xray Cloud."""
        if self._token:
            return self._token

        response = requests.post(
            self._AUTH_URL,
            json={"client_id": self._client_id, "client_secret": self._client_secret},
            timeout=30,
        )
        response.raise_for_status()
        self._token = response.json()
        logger.info("Xray authentication successful")
        return self._token

    # ------------------------------------------------------------------
    # Upload results
    # ------------------------------------------------------------------

    def upload_results(
        self,
        plan_key: str,
        summary: str,
        results: list[TestResult],
    ) -> str:
        """
        Upload test results to Xray and return the new execution issue key.

        Args:
            plan_key: Jira test plan key (e.g. "BCM-50")
            summary:  Human-readable execution summary
            results:  List of TestResult objects

        Returns:
            Created Jira test execution key (e.g. "BCM-123")
        """
        token = self._authenticate()
        payload = self._build_payload(plan_key, summary, results)

        response = requests.post(
            self._IMPORT_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        execution_key = response.json().get("key", "UNKNOWN")
        logger.info("Xray execution created: %s (%d results)", execution_key, len(results))
        return execution_key

    def upload_junit_xml(self, xml_path: str, plan_key: str, summary: str) -> str:
        """
        Convenience method — parse a JUnit XML file and upload directly.

        Args:
            xml_path: Path to pytest --junitxml output file
            plan_key: Jira test plan key
            summary:  Execution summary string
        """
        results = self.parse_junit_xml(xml_path)
        logger.info("Parsed %d results from %s", len(results), xml_path)
        return self.upload_results(plan_key, summary, results)

    # ------------------------------------------------------------------
    # JUnit XML parser
    # ------------------------------------------------------------------

    @staticmethod
    def parse_junit_xml(xml_path: str) -> list[TestResult]:
        """
        Parse a pytest JUnit XML file into a list of TestResult objects.

        Mapping:
            pytest test name → Xray test key via [XRAY:BCM-XXX] tag in docstring
            passed  → PASS
            failed  → FAIL
            error   → ABORTED
            skipped → ABORTED
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()
        results: list[TestResult] = []

        for testcase in root.iter("testcase"):
            name       = testcase.get("name", "")
            classname  = testcase.get("classname", "")
            duration   = float(testcase.get("time", "0")) * 1000  # → ms

            # Extract Xray test key from docstring property
            # Convention: add [XRAY:BCM-101] anywhere in the test docstring
            test_key = _extract_xray_key(testcase) or f"{JIRA_PROJECT}-UNMAPPED"

            # Determine status
            if testcase.find("failure") is not None:
                status  = "FAIL"
                comment = testcase.find("failure").get("message", "")[:500]
            elif testcase.find("error") is not None:
                status  = "ABORTED"
                comment = testcase.find("error").get("message", "")[:500]
            elif testcase.find("skipped") is not None:
                status  = "ABORTED"
                comment = "Test skipped"
            else:
                status  = "PASS"
                comment = ""

            results.append(TestResult(
                test_key=test_key,
                status=status,
                comment=comment,
                duration_ms=int(duration),
            ))

            logger.debug("Parsed: %s.%s → %s [%s]", classname, name, test_key, status)

        return results

    # ------------------------------------------------------------------
    # Payload builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_payload(
        plan_key: str, summary: str, results: list[TestResult]
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "info": {
                "project":  {"key": JIRA_PROJECT},
                "summary":  summary,
                "startDate": now,
                "finishDate": now,
                "testPlanKey": plan_key,
            },
            "tests": [
                {
                    "testKey": r.test_key,
                    "status":  r.status,
                    "comment": r.comment,
                    "executedOn": now,
                    "duration":  r.duration_ms,
                    **({"evidence": r.evidence} if r.evidence else {}),
                }
                for r in results
            ],
        }


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _extract_xray_key(testcase_element: ET.Element) -> Optional[str]:
    """
    Extract Xray test key from the JUnit XML testcase element.
    Looks for a <property name="xray_test_key" value="BCM-101"/> property.
    """
    for prop in testcase_element.iter("property"):
        if prop.get("name") == "xray_test_key":
            return prop.get("value")
    return None
