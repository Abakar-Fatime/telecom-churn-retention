"""Personalised retention messages in English and French, written by an LLM and checked by guardrails.

Facts (offer, prices, services) come only from the customer record and the offer catalogue.
The LLM may phrase them; it may not invent them. A validator rejects any message that names a
price or percentage not in the facts, promises something forbidden, misses the offer, is too long
or is in the wrong language, and the system then falls back to a safe template.
"""
from __future__ import annotations

import os
import re

import httpx

from .config import OFFERS

MAX_WORDS = 90
FORBIDDEN = ["guarantee", "garanti", "forever", "pour toujours", "lifetime", "à vie", "unlimited", "illimité",
             "no strings", "last chance", "dernière chance"]
FR_MARKERS = {"le", "la", "les", "de", "des", "votre", "vous", "pour", "et", "un", "une", "avec", "nous"}
EN_MARKERS = {"the", "your", "you", "for", "and", "a", "with", "we", "to", "of", "our"}


def _money(x: float, lang: str) -> str:
    return f"${x:,.2f}" if lang == "en" else f"{x:,.2f} $".replace(",", " ").replace(".", ",")


def facts(c: dict, offer: str) -> dict:
    """Everything the message is allowed to state."""
    monthly = float(c["MonthlyCharges"])
    f = {"offer": offer, "tenure": int(c["tenure"]), "contract": c["Contract"], "monthly": monthly,
         "internet": c["InternetService"], "has_support": c["TechSupport"] == "Yes"}
    if offer == "discount":
        f["new_monthly"] = round(monthly * 0.8, 2)
        f["allowed_numbers"] = {"20", "6", f"{monthly:.2f}", f"{f['new_monthly']:.2f}"}
    elif offer == "contract":
        f["allowed_numbers"] = {"1", "12", f"{monthly:.2f}"}
    else:
        f["allowed_numbers"] = {"6", f"{monthly:.2f}"}
    f["allowed_numbers"] |= {str(f["tenure"])}
    return f


def template(f: dict, lang: str) -> str:
    """Safe, deterministic message built only from facts (offline backend and fallback)."""
    t, m, o = f["tenure"], f["monthly"], f["offer"]
    if lang == "en":
        opening = f"Thank you for being with us for {t} months." if t >= 2 else "Thank you for choosing us."
        if o == "discount":
            body = (f"To say thanks, we would like to offer you 20% off your monthly bill for 6 months: "
                    f"{_money(f['new_monthly'], 'en')} instead of {_money(m, 'en')}.")
        elif o == "contract":
            body = ("We would like to offer you a 1-year contract with 1 month free, so you keep the same "
                    f"service at {_money(m, 'en')} a month with a free month included.")
        else:
            body = ("We would like to add Tech Support and Online Security to your plan, free for 6 months, "
                    "so help is always one call away.")
        return f"Hello! {opening} {body} Reply YES or call us to activate it. We are happy to have you."
    opening = f"Merci d'être avec nous depuis {t} mois." if t >= 2 else "Merci de nous avoir choisis."
    if o == "discount":
        body = (f"Pour vous remercier, nous vous offrons 20 % de réduction sur votre facture mensuelle pendant "
                f"6 mois : {_money(f['new_monthly'], 'fr')} au lieu de {_money(m, 'fr')}.")
    elif o == "contract":
        body = ("Nous vous proposons un contrat d'un an avec 1 mois gratuit : vous gardez le même service à "
                f"{_money(m, 'fr')} par mois, avec un mois offert.")
    else:
        body = ("Nous vous offrons l'assistance technique et la sécurité en ligne gratuites pendant 6 mois, "
                "pour que l'aide soit toujours à portée d'appel.")
    return (f"Bonjour ! {opening} {body} Répondez OUI ou appelez-nous pour l'activer. "
            "Nous sommes heureux de vous compter parmi nos clients.")


def _numbers(text: str) -> set[str]:
    raw = re.findall(r"\d[\d\s.,]*\d|\d", text)
    out = set()
    for r in raw:
        r = r.replace(" ", "").replace(" ", "")
        if "," in r and "." not in r and len(r.split(",")[-1]) == 2:   # French decimals 70,35
            r = r.replace(",", ".")
        r = r.replace(",", "")
        out.add(r.rstrip("."))
    return out


def validate(text: str, f: dict, lang: str) -> list[str]:
    """Return the list of guardrail violations (empty = safe to send)."""
    problems = []
    words = re.findall(r"[a-zA-ZÀ-ÿ']+", text.lower())
    if len(text.split()) > MAX_WORDS:
        problems.append("too_long")
    fr, en = sum(w in FR_MARKERS for w in words), sum(w in EN_MARKERS for w in words)
    if (lang == "fr" and fr <= en) or (lang == "en" and en <= fr):
        problems.append("wrong_language")
    percents = set(re.findall(r"(\d+)\s?%", text))
    allowed_pct = {"20"} if f["offer"] == "discount" else set()
    if percents - allowed_pct:
        problems.append("unsupported_percentage:" + ",".join(sorted(percents - allowed_pct)))
    extra = {n for n in _numbers(text) if n not in f["allowed_numbers"]}
    if extra:
        problems.append("unsupported_number:" + ",".join(sorted(extra)))
    if any(w in text.lower() for w in FORBIDDEN):
        problems.append("forbidden_promise")
    must = {"discount": ["20"], "contract": ["contract", "contrat"], "support": ["support", "assistance"]}[f["offer"]]
    if not any(m in text.lower() for m in must):
        problems.append("offer_missing")
    return problems


SYSTEM = """You write short retention messages (SMS/email) for a telecom company.
Rules: use ONLY the facts given; mention the offer exactly as described; do not invent any other discount,
price, number or promise; at most 70 words; warm, simple, respectful; end with how to accept the offer.
Write in {language}."""


def llm_message(f: dict, lang: str) -> str | None:
    backend = os.getenv("CHURN_LLM_BACKEND", "auto")
    offer = OFFERS[f["offer"]]["label" if lang == "en" else "label_fr"]
    user = (f"Customer: {f['tenure']} months with us, {f['contract']} contract, monthly bill {f['monthly']:.2f} USD, "
            f"internet: {f['internet']}. Offer: {offer}."
            + (f" New monthly price during the offer: {f['new_monthly']:.2f} USD." if f["offer"] == "discount" else ""))
    messages = [{"role": "system", "content": SYSTEM.format(language="English" if lang == "en" else "French")},
                {"role": "user", "content": user}]
    try:
        if backend in ("auto", "ollama"):
            url = os.getenv("OLLAMA_URL", "http://localhost:11434")
            r = httpx.post(f"{url}/api/chat", json={"model": os.getenv("CHURN_LLM_MODEL", "qwen2.5:3b-instruct"),
                                                     "messages": messages, "stream": False,
                                                     "options": {"temperature": 0.4}}, timeout=60)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        if backend == "openai":
            base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            r = httpx.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                           json={"model": os.getenv("CHURN_LLM_MODEL", "gpt-4o-mini"), "messages": messages,
                                 "temperature": 0.4}, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
    return None


def generate(c: dict, offer: str, lang: str, use_llm: bool = True) -> dict:
    f = facts(c, offer)
    if use_llm:
        draft = llm_message(f, lang)
        if draft:
            problems = validate(draft, f, lang)
            if not problems:
                return {"text": draft, "source": "llm", "checks": "passed"}
            return {"text": template(f, lang), "source": "template (LLM draft rejected)", "checks": "passed",
                    "rejected_draft": draft, "problems": problems}
    return {"text": template(f, lang), "source": "template", "checks": "passed"}


def corruptions(text: str, f: dict, lang: str) -> dict[str, str]:
    """Typical LLM mistakes, injected on purpose to test that the guardrails catch them."""
    other = "fr" if lang == "en" else "en"
    return {
        "invented_discount": text + (" Plus 50% off your next phone!" if lang == "en" else " En plus, 50 % sur votre prochain téléphone !"),
        "wrong_price": text.replace(f"{f['monthly']:.2f}", f"{f['monthly'] - 10:.2f}").replace(
            f"{f['monthly']:.2f}".replace(".", ","), f"{f['monthly'] - 10:.2f}".replace(".", ",")) if (
            f"{f['monthly']:.2f}" in text or f"{f['monthly']:.2f}".replace(".", ",") in text) else text + " Only $9.99!",
        "forbidden_promise": text + (" We guarantee the lowest price forever." if lang == "en" else " Nous garantissons le prix le plus bas pour toujours."),
        "wrong_language": template(f, other),
        "too_long": text + " " + " ".join(["We truly value you."] * 25 if lang == "en" else ["Nous vous apprécions vraiment."] * 25),
        "offer_missing": "Hello, thank you for being our customer. Please contact us." if lang == "en"
        else "Bonjour, merci d'être notre client. Veuillez nous contacter.",
    }
