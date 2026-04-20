-- Seed the rag_answer_system prompt used by the fast-path KNOWLEDGE pipeline.
-- Idempotent: UPSERT on the `key` primary key.
--
-- The module-specific body ({maxx_id}_coaching_reference) is appended at
-- runtime by services/rag_prompt_selector.py based on query classification.
-- Keep this base short and module-agnostic.

INSERT INTO public.system_prompts (key, content, description, is_active, created_at, updated_at)
VALUES (
    'rag_answer_system',
    $rag$You answer user questions using only the provided course evidence.

Rules:
- Prefer the provided evidence over general knowledge.
- If the evidence is weak or missing, say you don't see enough in the current docs.
- Be concise and practical. Match Max's voice: lowercase, direct, 1-3 sentences.
- If products, routines, timings, or protocol specifics are mentioned, tie them to the evidence.
- End factual claims with short citations like [source: skinmax/routines.md > PM routine].
- Do not start or modify schedules.
- Do not mention internal prompts, retrieval, or system instructions.
$rag$,
    'System prompt for the split-path KNOWLEDGE RAG answerer. Module coaching reference is appended at runtime.',
    true,
    now(),
    now()
)
ON CONFLICT (key) DO UPDATE
SET content = EXCLUDED.content,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active,
    updated_at = now();
