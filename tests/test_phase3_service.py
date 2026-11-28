import hashlib
import hmac
import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import phase3_service


class KnowledgeServiceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(phase3_service.app)
        self.addCleanup(self.client.close)
        env = patch.dict(os.environ, {"PHASE3_SERVICE_SECRET": "unit-test-only"})
        env.start()
        self.addCleanup(env.stop)
        self.question = {
            "operation": "answer_question",
            "question": "Who approves production changes?",
            "evidence": [{"chunk_id": "p-1", "document_id": "policy", "revision": "v1",
                          "location": "Page 1", "text": "The change board approves all production changes."}],
        }

    def post(self, payload, path="answer", timestamp=None, sign_payload=None):
        stamp = str(int(time.time()) if timestamp is None else timestamp)
        raw = json.dumps(payload).encode()
        signed = raw if sign_payload is None else json.dumps(sign_payload).encode()
        signature = hmac.new(b"unit-test-only", stamp.encode() + b"." + signed, hashlib.sha256).hexdigest()
        return self.client.post(f"/internal/knowledge/{path}", content=raw, headers={
            "X-Knowledge-Timestamp": stamp, "X-Knowledge-Signature": signature,
            "Content-Type": "application/json",
        })

    def message(self, paragraphs=None, missing=None, suggestions=None):
        return SimpleNamespace(content=json.dumps({
            "paragraphs": paragraphs or [], "missing_information": missing or [],
            "suggestions": suggestions or [],
        }), usage_metadata={"input_tokens": 12, "output_tokens": 8})

    def test_signature_required_and_request_body_protected(self):
        self.assertEqual(self.client.post("/internal/knowledge/answer", json=self.question).status_code, 401)
        self.assertEqual(self.post(self.question, timestamp=int(time.time()) - 121).status_code, 401)
        self.assertEqual(self.post(self.question, sign_payload={}).status_code, 401)
        with patch.dict(os.environ, {"PHASE3_SERVICE_SECRET": ""}):
            self.assertEqual(self.post(self.question).status_code, 503)

    def test_rejects_ambiguous_and_misrouted_envelopes(self):
        mixed = dict(self.question, texts=["a"], purpose="query")
        for path in ("answer", "embed"):
            self.assertEqual(self.post(mixed, path).status_code, 422)
        self.assertEqual(self.post(self.question, "embed").status_code, 422)
        self.assertEqual(self.post({"purpose": "document", "texts": ["x"]}).status_code, 422)

    @patch("phase3_engine.generate")
    def test_approved_faq_hit_has_known_zero_generation_cost(self, generate):
        self.question["faq"] = {"answer": "The change board.", "citation_ids": ["p-1"]}
        response = self.post(self.question)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["text"], "The change board.")
        self.assertEqual(data["route"], "verified_faq")
        self.assertEqual(data["citation_ids"], ["p-1"])
        self.assertEqual(data["usage"], {"input_tokens": 0, "output_tokens": 0})
        generate.assert_not_called()

    @patch("phase3_engine.generate")
    def test_faq_with_missing_dependency_is_not_exposed_to_provider(self, generate):
        self.question["faq"] = {"answer": "Revoked fact", "citation_ids": ["p-1", "revoked"]}
        generate.return_value = self.message(missing=["Which authorized policy provides sign-off?"])
        data = self.post(self.question).json()
        self.assertEqual(data["route"], "insufficient_evidence")
        self.assertNotIn("Revoked fact", json.dumps(generate.call_args.args))

    @patch("phase3_engine.generate")
    def test_no_evidence_abstains_before_calling_provider(self, generate):
        self.question["evidence"] = []
        self.question["history"] = [{"role": "assistant", "content": "An old answer"}]
        data = self.post(self.question).json()
        self.assertEqual(data["route"], "insufficient_evidence")
        self.assertTrue(data["missing_information"])
        generate.assert_not_called()

    @patch("phase3_engine.generate")
    def test_compound_editor_requirement_keeps_gap_and_citations(self, generate):
        self.question.update(operation="draft_response", question="Who approves and how long are records kept?",
                             faq={"answer": "Change board", "citation_ids": ["p-1"]})
        generate.return_value = self.message([{
            "text": "The change board approves production changes.",
            "sources": [{"chunk_id": "p-1", "quote": "The change board approves"}],
        }], ["What is the record retention period?"])
        data = self.post(self.question).json()
        self.assertEqual(data["route"], "hybrid")
        self.assertEqual(data["citation_ids"], ["p-1"])
        self.assertEqual(data["usage"], {"input_tokens": 12, "output_tokens": 8})
        self.assertIn("retention period", data["missing_information"][0])
        self.assertIn("Change board", generate.call_args.args[0][1][1])

    @patch("phase3_engine.generate")
    def test_unknown_citation_or_invented_quote_abstains(self, generate):
        for source in ({"chunk_id": "p-2", "quote": "The change board"},
                       {"chunk_id": "p-1", "quote": "we retain records for five years"}):
            generate.return_value = self.message([{"text": "Unsafe unsupported text.", "sources": [source]}])
            data = self.post(self.question).json()
            self.assertEqual(data["route"], "insufficient_evidence")
            self.assertEqual(data["citation_ids"], [])
            self.assertNotIn("Unsafe", data["text"])

    @patch("phase3_engine.generate")
    def test_brainstorming_explicit_and_separate_from_editor(self, generate):
        self.question.update(brainstorming=True, evidence=[])
        generate.return_value = self.message(suggestions=["Consider a peer review checklist."])
        data = self.post(self.question).json()
        self.assertIn("Brainstorming suggestions", data["text"])
        self.assertEqual(data["route"], "brainstorm")
        self.assertEqual(data["citation_ids"], [])
        self.question["operation"] = "draft_response"
        self.assertEqual(self.post(self.question).status_code, 422)

    @patch("phase3_engine.generate")
    def test_upstream_error_does_not_echo_text(self, generate):
        generate.side_effect = RuntimeError("sensitive error detail")
        response = self.post(self.question)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("sensitive", response.text)

    @patch("phase3_engine._embedding_clients")
    def test_embeddings_use_retrieval_task_and_unit_norm(self, clients):
        client = Mock()
        client.embed_documents.return_value = [[3.0, 4.0] + [0.0] * 766]
        clients.return_value = [client]
        for purpose, task in (("query", "RETRIEVAL_QUERY"), ("document", "RETRIEVAL_DOCUMENT")):
            response = self.post({"purpose": purpose, "texts": ["private text"]}, "embed")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["vectors"][0][:2], [0.6, 0.8])
            self.assertEqual(len(response.json()["vectors"][0]), 768)
            client.embed_documents.assert_called_with(["private text"], task_type=task)
        client.embed_documents.return_value = [[0.0] * 768]
        self.assertEqual(self.post({"purpose": "query", "texts": ["sample"]}, "embed").status_code, 503)


if __name__ == "__main__":
    unittest.main()
