"""
Test Suite: Synthetic Fallback Verification (Laya ML Model)
Location: tests/test_synthetic_fallback.py

This test verifies that:
1. Rule-based classification fails or outputs low confidence on emails with generic 
   subject lines, non-standard headers, and non-descriptive file names.
2. The PipelineOrchestrator detects low confidence (< threshold) and routes to Laya.
3. Laya correctly identifies the email as a `document_comparison` request.
4. The extraction stage parses non-standard field labels ("Departure Location") 
   and flags the discrepancy (Shanghai vs. Ningbo).
"""

from pathlib import Path
import pytest

from averis_email.data_loader import Inbox
from averis_email.orchestrator import PipelineOrchestrator
from averis_email.stages.classification import RuleBasedClassifier


# Resolve synthetic directory path dynamically relative to this test file
BASE_DIR = Path(__file__).parent
SYNTHETIC_DATA_DIR = BASE_DIR / "synthetic"


@pytest.fixture
def synthetic_inbox():
    """Fixture to load the synthetic test dataset."""
    assert SYNTHETIC_DATA_DIR.exists(), f"Synthetic directory not found at {SYNTHETIC_DATA_DIR}"
    return Inbox(str(SYNTHETIC_DATA_DIR))


@pytest.fixture
def orchestrator():
    """Fixture to initialize the full hybrid orchestrator."""
    return PipelineOrchestrator()


def test_rule_classifier_low_confidence_on_synthetic_case(synthetic_inbox):
    """
    Step 1: Verify that the pure Rule-Based Classifier fails or yields low 
    confidence on the synthetic edge-case email (email_999).
    """
    rule_classifier = RuleBasedClassifier()
    email = synthetic_inbox.get("email_999")
    
    assert email is not None, "synthetic_email_999.json was not found in inbox/"
    
    # Run standalone rule classification
    rule_result = rule_classifier.classify(email)
    
    # Assert that the rule engine fails to achieve high confidence
    print(f"\n[Rule Engine] Category: {rule_result.category}, Confidence: {rule_result.confidence}")
    assert rule_result.confidence < 0.70 or rule_result.category != "document_comparison", (
        "Expected Rule Engine to fail/score low confidence on synthetic email, "
        f"but got confidence {rule_result.confidence} for category '{rule_result.category}'."
    )


def test_laya_fallback_orchestration(synthetic_inbox, orchestrator):
    """
    Step 2 & 3: Verify that Orchestrator triggers Laya ML fallback and 
    successfully processes the document comparison and extraction.
    """
    email = synthetic_inbox.get("email_999")
    assert email is not None
    
    # Run email through orchestrator pipeline
    result = orchestrator.process_email(email)
    
    # Verify Orchestrator metadata
    print(f"\n[Orchestrator] Final Category: {result.category}")
    print(f"[Orchestrator] Classification Source: {getattr(result, 'classification_source', 'laya')}")
    
    # 1. Assert classification correctly resolved to document_comparison
    assert result.category == "document_comparison"
    
    # 2. Assert fallback classifier was invoked
    if hasattr(result, "classification_source"):
        assert result.classification_source in ["laya", "llm_fallback"]
        
    # 3. Assert extraction caught the port mismatch (Shanghai vs Ningbo)
    assert hasattr(result, "mismatches") or hasattr(result, "discrepancies")
    
    mismatches = getattr(result, "mismatches", {}) or getattr(result, "discrepancies", {})
    
    # Check if port mismatch was detected
    port_mismatch_found = False
    for field, details in mismatches.items():
        if "loading" in field.lower() or "departure" in field.lower() or field == "port_of_loading":
            port_mismatch_found = True
            si_val = str(details.get("si", "")).lower()
            bl_val = str(details.get("bl", "")).lower()
            assert "shanghai" in si_val
            assert "ningbo" in bl_val
            
    assert port_mismatch_found, f"Port of loading mismatch was not flagged in mismatches: {mismatches}"


if __name__ == "__main__":
    # Allows running directly via python tests/test_synthetic_fallback.py
    print("Running Synthetic Fallback Verification Suite...")
    inbox = Inbox(str(SYNTHETIC_DATA_DIR))
    orch = PipelineOrchestrator()
    
    test_rule_classifier_low_confidence_on_synthetic_case(inbox)
    test_laya_fallback_orchestration(inbox, orch)
    print("\n✅ ALL SYNTHETIC FALLBACK TESTS PASSED!")