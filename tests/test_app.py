"""Offline checks: python -m unittest discover -s tests -v."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import types
import pymupdf
from streamlit.testing.v1 import AppTest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.document_service import extract_pdf
from services import results_service as results


def pdf_upload(text="The research uses MiniLM embeddings."):
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
        data = io.BytesIO(pdf.tobytes())
    data.name = "sample.pdf"
    return data


class DocumentTests(unittest.TestCase):
    def test_identity_and_pages(self):
        a = extract_pdf(pdf_upload())
        b = extract_pdf(pdf_upload("Different contents."))
        self.assertNotEqual(a["document_id"], b["document_id"])
        self.assertEqual(a["pages"][0]["page_number"], 1)
        self.assertIn("MiniLM", a["full_text"])

    def test_blank_and_corrupt(self):
        with self.assertRaisesRegex(ValueError, "OCR"):
            extract_pdf(pdf_upload(""))
        data = io.BytesIO(b"invalid pdf")
        data.name = "bad.pdf"
        with self.assertRaises(Exception):
            extract_pdf(data)

    def test_saved_results(self):
        self.assertEqual(len(results.load_final_metrics()), 16)
        self.assertEqual(results.get_experiment_summary()["completed_configurations"], 16)
        for loader in [results.load_robustness_degradation, results.load_sensitivity_metrics, results.load_efficiency_metrics, results.load_statistical_results]:
            self.assertFalse(loader().empty)


class PageTests(unittest.TestCase):
    def app(self, page=None):
        at = AppTest.from_file(str(ROOT / "app.py")).run()
        if page:
            at.switch_page("pages/" + page).run()
        return at

    def assert_clean(self, at):
        self.assertFalse(list(at.exception))
        self.assertFalse(list(at.error))

    def test_navigation_and_dashboard_controls(self):
        at = self.app()
        for page in ["1_Single_Retrieval.py", "2_Compare_Chunkers.py", "3_Research_Dashboard.py"]:
            at.switch_page("pages/" + page).run()
            self.assert_clean(at)
        for select in list(at.selectbox):
            if len(select.options) > 1:
                at.selectbox(key=select.key).select_index(1).run()
                self.assert_clean(at)

    def test_live_state_with_stubbed_backend(self):
        chunk = {"text": "Evidence", "token_count": 1, "source_page_ids": [1]}
        backend = types.ModuleType("services.research_backend")
        backend.create_chunks = lambda *args: [chunk]
        backend.build_retrieval_index = lambda *args: object()
        backend.search_document = lambda *args: [(0.8, chunk)]
        upload = pdf_upload()
        with patch.dict(sys.modules, {"services.research_backend": backend}), patch("services.live_ui.load_model", return_value=object()), patch("streamlit.file_uploader", return_value=upload):
            at = self.app("1_Single_Retrieval.py")
            at.button(key="single_build").click().run()
            self.assert_clean(at)
            at.text_input[0].set_value("What model?")
            at.button[-1].click().run()
            self.assertIn("results", at.session_state["single_workspace"])
            at.run()
            self.assertIn("results", at.session_state["single_workspace"])
            at.selectbox(key="single_strategy").select("semantic").run()
            self.assertNotIn("indexes", at.session_state["single_workspace"])
            at.button(key="single_build").click().run()
            at.switch_page("pages/2_Compare_Chunkers.py").run()
            at.button(key="compare_build").click().run()
            self.assertEqual(len(at.session_state["compare_workspace"]["indexes"]), 4)
            at.switch_page("pages/1_Single_Retrieval.py").run()
            self.assertEqual(at.session_state["single_workspace"]["strategy"], "semantic")
            self.assertIn("indexes", at.session_state["single_workspace"])
        with patch("streamlit.file_uploader", return_value=pdf_upload("Replacement contents.")):
            at.run()
            self.assertNotIn("indexes", at.session_state["single_workspace"])
        with patch("streamlit.file_uploader", return_value=None):
            at.button(key="single_clear").click().run()
            self.assertNotIn("document", at.session_state["single_workspace"])
            self.assert_clean(at)


if __name__ == "__main__":
    unittest.main()
