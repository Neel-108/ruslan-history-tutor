RUSLAN v3.4 FLOWCHART

Note: Best viewed in Raw or Code view on GtHub.


┌─────────────────────────────────────────────────────────────────────┐
│                         USER SENDS MESSAGE                          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TIER-0 BACKEND CHECKS                            │
│                                                                     │
│  - /reset or system command?                                        │
│  - session limits exceeded?                                         │
│  - token cap exceeded?                                              │
│                                                                     │
│  If handled here → SEND TEMPLATE RESPONSE → END                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 TIER-1: YANDEXGPT LITE (ASYNC)                      │
│                 INTENT CLASSIFICATION ONLY                          │
│                                                                     │
│  Classify user message as one of:                                   │
│   - CASUAL                                                          │
│   - ABUSE                                                           │
│   - TEACH                                                           │
│   - CONTINUE                                                        │
│   - REVISION                                                        │
│   - MIXED (ABUSE + VALID HISTORY QUESTION)                          │
│                                                                     │
│  maxTokens: very small                                              │
│  cost: minimal                                                      │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BACKEND MODE DECISION                            │
│               (LLM HAS NO AUTHORITY HERE)                           │
└───────────────┬───────────────┬───────────────┬────────────────────-┘
                │               │               │
                ▼               ▼               ▼
        ┌────────────┐   ┌────────────┐   ┌─────────────────────────┐
        │   CASUAL   │   │ PURE ABUSE │   │ MIXED ABUSE + QUESTION  │
        └─────┬──────┘   └─────┬──────┘   └─────────────┬───────────┘
              │                │                        │
              ▼                ▼                        ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────────────┐
│ SEND TEMPLATE        │  │ SEND ABUSE TEMPLATE  │  │ SILENTLY APPLY ABUSE PENALTY     │
│ RESPONSE             │  │                      │  │ (TOKEN / SCORE DECREMENT)        │
│                      │  │ NO PRO CALL          │  │ STRIP / MASK ABUSIVE PART        │
│ NO PRO CALL          │  │ NO MEMORY UPDATE     │  │ CONTINUE TO TEACHING FLOW        │
│ NO MEMORY UPDATE     │  │ END                  │  └─────────────┬────────────────────┘
│ END                  │  └──────────────────────┘                │
└──────────────────────┘                                             ▼
                                                           ┌─────────────────────────────┐
                                                           │        TEACHING FLOW        │
                                                           └─────────────┬─────────-─────┘
                                                                         │
                                                                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│              LOAD MEMORY FROM DATABASE                              │
│                                                                     │
│  HOT STATE (ALWAYS):                                                │
│   - grade                                                           │
│   - textbook                                                        │
│   - current_topic                                                   │
│   - current_checkpoint (1–2 factual sentences)                      │
│   - mode                                                            │
│                                                                     │
│  CONTEXT WINDOW:                                                    │
│   - last 3 user–bot message pairs                                   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│        CHECK IF WARM SUMMARY SHOULD BE INJECTED                     │
│                                                                     │
│  Inject ONLY if:                                                    │
│   - user explicitly asks to revise / recall                         │
│   - user jumps backward in chronology                               │
│   - chronology conflict detected                                    │
│                                                                     │
│  Otherwise: DO NOT INCLUDE WARM SUMMARY                             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│            BUILD FINAL PROMPT FOR PRO MODEL                         │
│                                                                     │
│  Includes ONLY:                                                     │
│   - STATIC FGOS RULES                                               │
│   - HOT STATE                                                       │
│   - LAST 3 CONTEXT TURNS                                            │
│   - WARM SUMMARY (CONDITIONAL)                                      │
│                                                                     │
│  EXCLUDES:                                                          │
│   - full history                                                    │
│   - narrative memory                                                │
│   - rigid output schemas                                            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│           TIER-2: YANDEXGPT PRO 5.1 (ASYNC)                         │
│           TEACHING ONLY                                             │
│                                                                     │
│  - history explanation                                              │
│  - examples                                                         │
│  - FGOS-compliant                                                   │
│                                                                     │
│  maxTokens capped by grade                                          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  POST-PROCESSING                                    │
│                                                                     │
│  - detect lesson boundary                                           │
│  - extract new checkpoint (if any)                                  │
│  - update HOT STATE                                                 │
│  - update WARM SUMMARY (only on boundary)                           │
│  - append to COLD LOG                                               │
│  - meter tokens                                                     │
│  - apply penalties if needed                                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SEND RESPONSE TO USER                           │
│                                                                     │
│  Natural language                                                   │
│  Grade-appropriate                                                  │
│  Continuation-safe                                                  │
└─────────────────────────────────────────────────────────────────────┘



This flowchart, together with the v3.4 architecture file, is sufficient for:

implementation

QA design

cost reasoning

explaining the system to another engineer.
