# AI Grounding

The AI explanation layer (`backend/intelligence/ai/`) is **optional, grounded, and
architecturally incapable of becoming the source of truth**. Its job is presentation:
turn the deterministic intelligence artifacts into a four-section plain-language
explanation.

## The contract

```
LLMs do not discover dependencies, calculate technical impact,
select regression tests, create risk signals, select incidents,
or modify verified deterministic results.

AI is optional and is restricted to grounded explanation.
```

Output contract (`IntelligenceExplanation` in `ai_models.py`): exactly four string
fields — `executive_summary`, `technical_summary`, `testing_summary`,
`release_considerations` — plus two metadata fields:

- `subject_component`: must equal the context's `changed_component` (enforced by the guard).
- `explanation_source`: `deterministic` or `ai`, set authoritatively by `service.py` —
  a provider cannot label itself. The UI badge is driven by this field, never by parsing text.

## What the AI may do

1. **Summarize** the deterministic artifacts in plain language (`executive_summary`).
2. **Explain the impact mechanics** using only the supplied dependency paths, components, and evidence (`technical_summary`).
3. **Describe what to test and why** using only the recommended tests and their rationales (`testing_summary`).
4. **Restate the risks and checklist** produced by the deterministic layers (`release_considerations`).
5. **Summarize the already-selected relevant incidents** — what failures occurred before, which are most directly related, recurring themes, release-team awareness — via three additional sections (`incident_summary`, `historical_patterns`, `release_history_considerations`).

## The 7 prohibitions

The AI (provider, system prompt, and service) is forbidden from:

1. **Introducing components** not present in the supplied context.
2. **Introducing dependencies/edges** not present in the supplied dependency paths and evidence.
3. **Introducing tests** — test ids not in the recommended tests are forbidden.
4. **Introducing tables, jobs, or evidence** not present in the context.
5. **Overriding deterministic results** — severities, impact levels, checklist items, and rationales are inputs, not suggestions.
6. **Claiming failure probabilities** or predicting outcomes.
7. **Issuing release decisions** — the AI cannot approve, block, or sign off a release.

Prohibitions 1–4 are enforced mechanically by the hallucination guard; 5–7 by the input
contract (the provider never receives the authority to decide them).

## The provider model

`IntelligenceProvider` is a two-method ABC: `name` and `explain(context)`, where
`explain` "builds an explanation using ONLY the supplied context."

| Provider | Behaviour |
|---|---|
| `DeterministicProvider` (default) | Template-built explanation over the context only. No LLM, no network, always available. Emits only context identifiers, so it always passes the guard. |
| `FakeProvider` | Fixed canned explanation for tests; interpolates only ids the supplied context contains. |
| `HttpLlmProvider` | Generic chat-completions client, configured exclusively via environment variables. **Never instantiated unless explicitly configured.** |

Selection: `get_provider()` reads `INTELLIGENCE_PROVIDER` (`deterministic` default;
`fake`; `http`). Unknown values fall back to `deterministic`. Core functionality never
depends on an API key. The HTTP provider has not been live-tested with a paid API.

## The strict input contract

`IntelligenceContext` is **everything a provider is allowed to see**: changed
component, impacted components, dependency paths, evidence, recommended tests, risk
signals, release checklist, relevant incidents. **No repository paths, no raw source
text, no unfiltered graph access.** The provider cannot reach outside this object
because `service.py` constructs it from the deterministic models and hands nothing else
to the provider.

## The hallucination guard

`guard.py` — `validate_explanation(expl, ctx)`:

1. **Subject check.** `subject_component` must equal the context's `changed_component`.
2. **Vocabulary.** Allowed identifiers = changed component + impacted components +
   recommended test ids + signal ids (+ validated incident ids).
3. **Extraction.** Regex-scans all explanation text fields for candidate component ids,
   test ids (`TC-…`), and incident ids.
4. **Validation.** Any candidate outside the vocabulary raises `HallucinationError`,
   listing every offending identifier.
5. **Pass-through.** An explanation whose candidates are all known is returned unchanged.

## Fallback behaviour

Any provider exception (network error, bad API key, malformed JSON, misconfiguration)
**or** any guard rejection yields the deterministic explanation prefixed with:

> "AI explanation unavailable. Deterministic analysis remains available."

The caller always gets a valid explanation; the deterministic analysis — impact, tests,
signals, checklist, incidents — is never gated on the AI.

## The trust boundary (explicit)

Identifier grounding is validated automatically. Natural-language interpretation may
still contain unsupported wording, therefore **AI prose is non-authoritative and
deterministic evidence remains the source of truth**. The guard validates
*identifiers*, not prose — but because the provider only ever sees deterministic
artifacts, the worst it can do is restate them loosely. The AI layer has no write path
into the deterministic artifacts.

## Configuration

`.env.example` (committed) documents the knobs; real keys live in the environment or a
local uncommitted `.env`, never in the repository. A fresh checkout has full
intelligence functionality with zero configuration.

Phase working notes: `docs/archive/ai-grounding.md`.
