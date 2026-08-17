"""
SupportPilot AI — Phase 10: Guardrails

Goal: stop unsafe or made-up answers — without any ML classifier, just
plain, readable rules, in the same spirit as Phase 5's keyword search.

Three rules, in the order run_agent() applies them:

1. Sensitive request -> escalate immediately, don't even ask Gemini.
   Account deletion, fraud, security compromise, legal threats — these
   need a human, and a deterministic rule is more trustworthy here than
   hoping the model always remembers to defer on its own.

2. KB context was retrieved but the answer doesn't cite any of it ->
   don't trust it. Replace with an honest "I'm not sure" instead of
   letting an ungrounded claim through.

3. The answer makes a commitment it's not authorized to make ("I
   guarantee...", "legally binding...") -> replace with a safer,
   hedged fallback.

Known trade-off, stated plainly: rule #2 can occasionally reject a
correct answer that was just missing its citation bracket (a formatting
slip, not a substance problem). That's an intentional choice — for this
app, refusing a good answer once in a while is a better failure mode
than ever showing an ungrounded one as if it were verified.

These rules are pattern-based on purpose: understandable, testable
without any API key, and each one earns its place by covering a real
failure mode for THIS app — not a general content-safety classifier.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from crm import create_support_ticket
from kb import KBDoc
from memory import Message

# --- Guardrail 1: sensitive requests get escalated, not answered ---

# Deliberately multi-word, specific phrases rather than single loaded
# words (e.g. "dispute this charge", not bare "dispute") — a single
# word like "stolen" would misfire on an ordinary, KB-coverable question
# like "my package was stolen off my porch."
SENSITIVE_KEYWORDS = [
    "delete my account",
    "close my account",
    "unauthorized charge",
    "unauthorized transaction",
    "fraudulent charge",
    "fraudulent transaction",
    "fraudulent purchase",
    "fraud case",
    "my account was hacked",
    "someone accessed my account",
    "security breach",
    "account compromised",
    "dispute this charge",
    "chargeback",
    "legal action",
    "lawsuit",
    "sue you",
    "identity theft",
]

CUSTOMER_ID_PATTERN = re.compile(r"CUST-\d{3}", re.IGNORECASE)


def is_sensitive_request(message: str) -> bool:
    """True if the message touches account security, fraud, or legal
    threats — requests this bot should never freelance an answer to.
    """
    lowered = message.lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def extract_customer_id(message: str) -> Optional[str]:
    """Pull a "CUST-###" id out of a single message, if present."""
    match = CUSTOMER_ID_PATTERN.search(message)
    return match.group(0).upper() if match else None


def find_customer_id(message: str, history: Optional[List[Message]] = None) -> Optional[str]:
    """Look for a customer id in the current message first, then fall
    back to scanning recent conversation history (most recent first).

    Without this, a customer who already gave their id earlier in the
    conversation (e.g. in response to check_sensitive_request() asking
    for one) would be asked to repeat it on every later sensitive
    message in the same chat — annoying, and exactly the "doesn't use
    my previous context" gap reported in practice.
    """
    customer_id = extract_customer_id(message)
    if customer_id:
        return customer_id

    for past_message in reversed(history or []):
        customer_id = extract_customer_id(past_message.content)
        if customer_id:
            return customer_id

    return None


# --- Guardrail 1b: small talk never needs KB grounding ---

# A generic support-domain phrase like "thank you." can still score
# above a similarity threshold against a small, topically-narrow KB just
# by being in the same neighborhood -- a numeric cutoff alone isn't
# reliable for catching this (confirmed in practice: MIN_RELEVANCE_SCORE
# in vector_search.py wasn't enough on its own).
#
# First attempt here was an exact-phrase list ("thank you", "ok", ...).
# That broke on "ok, Thankyou." in practice -- a compound, unspaced
# variant no fixed list of whole phrases can fully enumerate; there's
# always another typo/spacing/combination away from matching. This is a
# word-level approach instead: a message counts as small talk when
# EVERY word in it (after stripping punctuation) is a known greeting/
# thanks/acknowledgment/closing word, which naturally covers "ok,
# Thankyou.", "Thanks!!", "ok thank you so much" etc. without needing to
# enumerate each combination.
#
# Deliberately excludes common filler words ("i", "a", "the", "is",
# "do", "have", ...) -- their absence is what keeps a real question
# ("no, I don't have my customer id") from accidentally matching, since
# it will almost always contain at least one word outside this narrow
# set.
SMALLTALK_WORDS = {
    "thank", "thanks", "thankyou", "thx", "ty",
    "ok", "okay", "k",
    "no", "nope", "nah", "yes", "yeah", "yep", "sure",
    "great", "perfect", "cool", "nice", "awesome", "good",
    "sounds", "got", "it",
    "hi", "hello", "hey", "yo",
    "bye", "goodbye", "cya",
    "welcome", "you", "youre", "im",
    "thats", "all",
    "so", "much", "appreciate", "appreciated",
}


def is_smalltalk(message: str) -> bool:
    """True if EVERY word in the message is a known greeting/thanks/
    acknowledgment/closing word — caught regardless of exact phrasing,
    spacing, or punctuation, while a real question isn't, because it
    almost always contains at least one word outside this narrow set.
    """
    normalized = message.lower().replace("'", "")
    words = re.findall(r"[a-z]+", normalized)
    if not words:
        return False
    return all(word in SMALLTALK_WORDS for word in words)


# --- Guardrail 2: KB-grounded answers must actually cite what they used ---


def has_required_citation(response_text: str, retrieved_docs: List[KBDoc]) -> bool:
    """True if the response cites at least one of the KB docs that were
    actually retrieved for it.

    Only meaningful when retrieved_docs is non-empty — call sites (see
    check_response() below) skip this check when nothing was retrieved,
    since a general/off-KB question is fine to answer without a citation.
    """
    return any(f"[{doc.doc_id}]" in response_text for doc in retrieved_docs)


# --- Guardrail 3: no commitments the bot isn't authorized to make ---

UNSUPPORTED_COMMITMENT_PHRASES = [
    "i guarantee",
    "we guarantee",
    "i promise",
    "we promise",
    "i certify",
    "legally binding",
    "legally entitled",
    "100% guaranteed",
]


def contains_unsupported_commitment(response_text: str) -> bool:
    """True if the response makes a promise or legal claim this bot has
    no business making on the company's behalf.
    """
    lowered = response_text.lower()
    return any(phrase in lowered for phrase in UNSUPPORTED_COMMITMENT_PHRASES)


# --- Fallback messages shown when a guardrail overrides the answer ---

CITATION_FALLBACK = (
    "I don't have a confident, documented answer for that. I don't want "
    "to guess, so let me connect you with our support team to get you an "
    "accurate answer."
)

COMMITMENT_FALLBACK = (
    "I'm not able to make that kind of guarantee or commitment myself. "
    "Let me connect you with our support team, who can give you a "
    "confirmed answer."
)


@dataclass
class GuardrailResult:
    """What a guardrail check decided, and why.

    triggered is None when nothing fired, or one of:
    "sensitive_escalation", "missing_citation", "unsupported_commitment".
    """
    triggered: Optional[str]
    response: Optional[str] = None


def check_sensitive_request(message: str, history: Optional[List[Message]] = None) -> GuardrailResult:
    """Guardrail 1 — checked BEFORE Gemini is ever called.

    If a customer id is present in this message OR earlier in the
    conversation (see find_customer_id()), opens a real support ticket
    immediately. If not, asks for one instead of guessing — creating a
    ticket against the wrong (or a made-up) customer would be worse than
    asking one follow-up question.
    """
    if not is_sensitive_request(message):
        return GuardrailResult(triggered=None)

    customer_id = find_customer_id(message, history)

    if customer_id:
        ticket = create_support_ticket(
            customer_id=customer_id,
            subject="Escalated: sensitive request",
            description=message,
        )
        response = (
            f"This needs a closer look from our support team, so I've "
            f"opened ticket #{ticket['ticket_id']} for you and flagged it "
            f"as high priority. Someone will follow up with you directly."
        )
    else:
        response = (
            "This needs a closer look from our support team rather than "
            "me handling it directly. Could you share your customer id "
            "(like CUST-001) so I can open a ticket and get this to them?"
        )

    return GuardrailResult(triggered="sensitive_escalation", response=response)


def check_response(
    response_text: str,
    retrieved_docs: List[KBDoc],
    tool_calls: Optional[List[dict]] = None,
) -> GuardrailResult:
    """Guardrails 2 and 3 — checked AFTER Gemini has answered, before the
    answer is shown to the customer.

    tool_calls skips the citation check (guardrail 2) when the model took
    a concrete action instead of asserting a KB fact — "I've opened
    ticket #4 for you" doesn't need a [doc_id] citation. It's a report of
    something that actually happened (verifiable by checking the ticket
    itself), not a claim sourced from the knowledge base. Without this,
    a correct tool-call response gets wrongly replaced any time KB search
    also happened to return something for the same message.
    """
    tool_calls = tool_calls or []

    if retrieved_docs and not tool_calls and not has_required_citation(response_text, retrieved_docs):
        return GuardrailResult(triggered="missing_citation", response=CITATION_FALLBACK)

    if contains_unsupported_commitment(response_text):
        return GuardrailResult(triggered="unsupported_commitment", response=COMMITMENT_FALLBACK)

    return GuardrailResult(triggered=None)
