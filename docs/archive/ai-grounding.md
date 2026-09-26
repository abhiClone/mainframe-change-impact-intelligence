# Phase 2A AI Grounding — What the AI May and May Not Do

The AI explanation layer (`backend/intelligence/ai/`) is **optional,
grounded, and architecturally incapable of becoming the source of truth**.
Its job is presentation: turn the deterministic intelligence artifacts into
a four-section plain-language explanation. This document states the exact
contract, the mechanism that enforces it, and the failure behavior.

## What the AI may do

1. **Summarize** the deterministic artifacts in plain language
   (`executive_summary` — one paragraph for non-technical readers).
2. **Explain the impact mechanics** using only the supplied dependency paths,
   components, and evidence (`technical_summary`).
3. **Describe what to test and why** using only the recommended tests and
   their rationales (`testing_summary`).
4. **Restate the risks and checklist** produced by the deterministic layers
   (`release_considerations`).

Output contract (`IntelligenceExplanation` in `ai_models.py`): exactly four
string fields — `executive_summary`, `technical_summary`,
`testing_summary`, `release_considerations` — plus two metadata fields:

- `subject_component`: the changed component the explanation is about; must
  equal the context's `changed_component` (enforced by the guard).
- `explanation_source`: `deterministic` or `ai`, set authoritatively by
  `service.py` — a provider cannot label itself.

The UI renders the badge from `explanation_source`, never from the text:
deterministic → **DETERMINISTIC SUMMARY**, validated LLM → **AI
EXPLANATION**, fallback → deterministic badge plus an explicit
AI-unavailable note.

## The 7 prohibitions

The AI (provider, system prompt, and service) is forbidden from:

1. **Introducing components** not present in the supplied context
   (changed component + impacted components).
2. **Introducing dependencies/edges** not present in the supplied
   dependency paths and evidence.
3. **Introducing tests** — test ids not in the recommended tests are
   forbidden; the AI may not invent test cases or change recommendations.
4. **Introducing tables, jobs, or evidence** not present in the context.
5. **Overriding deterministic results** — severities, impact levels,
   checklist items, and rationales are inputs, not suggestions; the AI
   cannot alter, add, or remove them.
6. **Claiming failure probabilities** or predicting outcomes — no likelihood
   estimates, no verdicts on whether the change will succeed.
7. **Issuing release decisions** — the AI cannot approve, block, or sign off
   a release; that decision stays with the release manager.

Prohibitions 1–4 are enforced mechanically by the hallucination guard;
5–7 are enforced by the input contract (the provider never receives the
authority to decide them — it receives only serialized results).

## The IntelligenceProvider abstraction

`IntelligenceProvider` (`providers.py`) is a two-method ABC: `name` and
`explain(context) -> IntelligenceExplanation`, where `explain` "builds an
explanation using ONLY the supplied context."

| Provider | Behavior |
|---|---|
| `DeterministicProvider` (default) | Template-built explanation over the context only. No LLM, no network, always available. Emits only context identifiers, so it always passes the guard. |
| `FakeProvider` | Fixed canned explanation for tests; interpolates only ids the supplied context contains, so it passes the guard. |
| `HttpLlmProvider` | Generic stdlib-`urllib` chat-completions client, configured exclusively via environment variables. **Never instantiated unless explicitly configured.** |

Selection: `get_provider()` reads `INTELLIGENCE_PROVIDER` from the
environment (`deterministic` default; `fake`; `http`). Any unknown or
missing value falls back to `deterministic` without crashing. Core
functionality never depends on an API key.

## The strict input contract

`IntelligenceContext` (`ai_models.py`) is **everything an explanation
provider is allowed to see**:

- `changed_component` (e.g. `copybook:WARRCOPY`)
- `impacted_components` (direct + transitive ids)
- `dependency_paths` (serialized `DependencyPath` entries)
- `evidence` (serialized `EvidenceRef` entries)
- `recommended_tests`, `risk_signals`, `release_checklist` (serialized)

**No repository paths, no raw source text, no unfiltered graph access.**
The provider cannot reach outside this object because `service.py`
(`explain_change`) constructs it from the sibling Phase 2A models and hands
nothing else to the provider. The HTTP provider's system instruction repeats
the prohibition in natural language: *"You may explain ONLY the supplied
information. Do not introduce components, dependencies, tests, tables, jobs
or evidence not present in the context."*

## The hallucination guard mechanism

`guard.py` — `validate_explanation(expl, ctx)`:

1. **Subject check.** The explanation's `subject_component` must equal the
   context's `changed_component`; a mismatch raises `HallucinationError`.
2. **Vocabulary.** Builds the allowed vocabulary from the context:
   `changed_component` + `impacted_components` + every `test_id` from
   `recommended_tests` + every signal `id` from `risk_signals`.
3. **Extraction.** Regex-scans all four explanation text fields for
   candidate identifiers:
   - component ids: `\b(?:program|job|proc|copybook|table):[A-Za-z0-9_#.\-]+\b`
   - test ids: `\bTC-[A-Za-z0-9\-]+\b`
4. **Validation.** Any candidate outside the vocabulary raises
   `HallucinationError`, listing every offending identifier.
5. **Pass-through.** An explanation whose candidates are all known is
   returned unchanged.

## The trust boundary (explicit)

Identifier grounding is validated automatically. Natural-language
interpretation may still contain unsupported wording, therefore AI prose is
non-authoritative and deterministic evidence remains the source of truth.

What this means in practice:

- The guard validates *identifiers*, not prose. It cannot catch a provider
  inventing a plausible-sounding sentence about a known component.
- Because the provider only ever sees deterministic artifacts, the worst it
  can do is restate them loosely. It cannot smuggle in new components,
  tests, tables, jobs, or evidence — the facts a release decision would act
  on.
- The AI layer has no write path into the deterministic artifacts:
  `explain_change()` never mutates the `ImpactContext`, recommendations,
  signals, or checklist it was given.
- `explanation_source` is set authoritatively by `service.py`
  (`deterministic` for the deterministic provider and the fallback, `ai`
  for a validated LLM-path provider). A provider cannot mislabel itself,
  and the UI badge is driven by this field, not by parsing the text.

## Fallback mode behavior

`explain_change()` in `service.py`:

```python
try:
    active_provider = provider if provider is not None else get_provider()
    explanation = active_provider.explain(context)
    explanation = validate_explanation(explanation, context)
    explanation.explanation_source = (
        ExplanationSource.DETERMINISTIC
        if isinstance(active_provider, DeterministicProvider)
        else ExplanationSource.AI
    )
    return explanation
except (HallucinationError, Exception):
    fallback = DeterministicProvider().explain(context)
    fallback.executive_summary = _FALLBACK_PREFIX + fallback.executive_summary
    return fallback
```

Any provider exception (network error, bad API key, malformed JSON,
`HttpLlmProvider` misconfiguration raising `ValueError` for missing env
vars) **or** any guard rejection yields the deterministic explanation with
the prefix:

> "AI explanation unavailable. Deterministic analysis remains available. "

The caller always gets a valid four-section explanation; the deterministic
analysis — impact, tests, signals, checklist — is never gated on the AI.

## Configuration and no-keys-in-repo policy

`.env.example` (committed) documents the knobs:

```
INTELLIGENCE_PROVIDER=deterministic          # default; no credentials needed
# INTELLIGENCE_PROVIDER=http
# INTELLIGENCE_LLM_ENDPOINT=https://your-llm-host/v1/chat/completions
# INTELLIGENCE_LLM_API_KEY=<redacted>        # NEVER commit real keys
# INTELLIGENCE_LLM_MODEL=
```

- The only way to activate a remote LLM is `INTELLIGENCE_PROVIDER=http`
  plus the three `INTELLIGENCE_LLM_*` variables; all other values degrade
  to `deterministic` silently.
- Real API keys live in the environment (or a local, uncommitted `.env`),
  never in the repository.
- Because the default provider needs no credentials and the fallback needs
  no network, a fresh checkout of this repo has full intelligence
  functionality with zero configuration.
