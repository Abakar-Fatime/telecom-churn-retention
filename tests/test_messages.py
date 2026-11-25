import json

from churnlab import messages as M
from churnlab.config import RESULTS_DIR
from churnlab.data import load

C = load().query("churn == 0").iloc[10].to_dict()


def test_templates_pass_guardrails_in_both_languages():
    for offer in ("discount", "contract", "support"):
        for lang in ("en", "fr"):
            f = M.facts(C, offer)
            assert M.validate(M.template(f, lang), f, lang) == []


def test_every_injected_error_is_caught():
    for offer in ("discount", "contract", "support"):
        for lang in ("en", "fr"):
            f = M.facts(C, offer)
            for name, bad in M.corruptions(M.template(f, lang), f, lang).items():
                assert M.validate(bad, f, lang), name


def test_percentage_matching_tenure_is_still_caught():
    c = dict(C, tenure=50)
    f = M.facts(c, "support")
    assert any(p.startswith("unsupported_percentage") for p in M.validate(M.template(f, "en") + " Plus 50% off!", f, "en"))


def test_unreachable_llm_falls_back_to_safe_template(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")
    out = M.generate(C, "discount", "fr")
    assert out["source"].startswith("template") and "20 %" in out["text"]


def test_evaluation_results():
    ev = json.loads((RESULTS_DIR / "messages_eval.json").read_text())
    assert ev["clean_pass_rate"] == 1.0 and ev["caught_rate"] == 1.0
