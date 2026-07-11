import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock


os.environ.setdefault("DATABASE_URL", "sqlite:///./checkmate-test.db")

from app.schemas.documents import LaborContract, Registry, RegistryRight
from app.services.labor_rules import LaborRuleEngine
from app.services.pii import PiiService
from app.services.rag import RAGService
from app.services.rule_engine import RuleEngine


class RagRoutingTests(unittest.TestCase):
    def test_labor_categories_resolve_to_configured_indexes(self):
        service = RAGService.__new__(RAGService)
        service._generate_embedding = Mock(return_value=[0.1])
        service._search_index = Mock(return_value=["evidence"])

        self.assertEqual(service.search_category("labor_laws", "query"), ["evidence"])
        self.assertEqual(service.search_category("labor_cases", "query"), ["evidence"])

        called_indexes = [call.args[0] for call in service._search_index.call_args_list]
        self.assertIn("labor-laws-index", called_indexes)
        self.assertIn("labor-cases-index", called_indexes)

    def test_unavailable_search_never_returns_fabricated_evidence(self):
        service = RAGService.__new__(RAGService)
        service._get_client = Mock(return_value=None)

        self.assertEqual(service._search_index("missing", "query", "노동법령"), [])


class RuleStateTests(unittest.TestCase):
    def _labor_contract(self, **overrides):
        data = {
            "employer_name": "회사",
            "employee_name": "근로자",
            "start_date": "2026-01-01",
            "salary": 0,
            "work_hours": "",
        }
        data.update(overrides)
        return LaborContract(**data)

    def _registry(self, **overrides):
        data = {
            "property_address": "서울시 중구",
            "owner_name": "소유자",
            "issue_date": datetime.now().date().isoformat(),
        }
        data.update(overrides)
        return Registry(**data)

    def test_missing_salary_and_hours_are_unknown(self):
        contract = self._labor_contract()

        self.assertEqual(LaborRuleEngine._check_min_wage(contract).status, "UNKNOWN")
        self.assertEqual(LaborRuleEngine._check_work_hours(contract).status, "UNKNOWN")

    def test_dangerous_registry_right_is_detected_from_schema_object(self):
        right = RegistryRight(
            type="근저당권",
            rank=1,
            amount=100000000,
            holder_name="은행",
            date="2026-01-01",
        )

        self.assertEqual(RuleEngine._check_prior_rights(self._registry(rights=[right])).status, "FAIL")
        self.assertEqual(RuleEngine._check_prior_rights(self._registry(rights=[])).status, "UNKNOWN")

    def test_issue_date_is_not_passed_when_missing_invalid_or_stale(self):
        stale = (datetime.now().date() - timedelta(days=8)).isoformat()

        self.assertEqual(RuleEngine._check_issue_date(self._registry(issue_date="")).status, "UNKNOWN")
        self.assertEqual(RuleEngine._check_issue_date(self._registry(issue_date="not-a-date")).status, "UNKNOWN")
        self.assertEqual(RuleEngine._check_issue_date(self._registry(issue_date=stale)).status, "FAIL")
        self.assertEqual(RuleEngine._check_issue_date(self._registry()).status, "PASS")

    def test_missing_building_usage_is_unknown(self):
        self.assertEqual(RuleEngine._check_building_usage(None, self._registry()).status, "UNKNOWN")


class PiiMaskingTests(unittest.TestCase):
    def test_pretrimmed_name_box_is_marked_to_avoid_second_trim(self):
        service = PiiService.__new__(PiiService)
        entities = service._find_all_names("홍길동", {"홍길동"})

        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["text"], "길동")
        self.assertTrue(entities[0]["partial_masked"])

        pages = [{"width": 3, "height": 1}]
        text_map = [
            (0, 3, {"page_idx": 0, "polygon": [0, 0, 3, 0, 3, 1, 0, 1]})
        ]
        boxes = service.map_pii_to_boxes(entities, pages, text_map)

        self.assertEqual(len(boxes), 1)
        self.assertTrue(boxes[0]["partial_masked"])
        self.assertGreater(boxes[0]["box_norm"][0], 0)


class PrivacyArtifactTests(unittest.TestCase):
    def test_runtime_sources_do_not_reintroduce_raw_pii_debug_sinks(self):
        backend_root = Path(__file__).resolve().parents[1]
        source_paths = [
            backend_root / "app" / "api" / "endpoints" / "analysis.py",
            backend_root / "app" / "services" / "history_service.py",
            backend_root / "app" / "services" / "llm.py",
            backend_root / "app" / "services" / "pii.py",
            backend_root / "app" / "services" / "visualizer.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)

        forbidden_fragments = [
            "debug_translation.txt",
            "Context Lessor:",
            "Context Owner:",
            "Text sample:",
            "Failed to delete blob for url",
            "pii.get('text', '')[:30]",
        ]
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, source)

    def test_local_runtime_artifacts_are_not_present(self):
        backend_root = Path(__file__).resolve().parents[1]

        self.assertFalse((backend_root / "test.db").exists())
        self.assertFalse((backend_root / "debug_translation.txt").exists())
        self.assertFalse((backend_root / "app" / "services" / "_temp_foreign_names.py").exists())


if __name__ == "__main__":
    unittest.main()
