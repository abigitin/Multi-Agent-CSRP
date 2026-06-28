from backend.core.config import get_settings


def generate_resolution(query: str, context_chunks: list[str]) -> str:
    settings = get_settings()
    fallback = _fallback_resolution(query, context_chunks)
    if not settings.groq_api_key:
        return fallback
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.groq_model,
            temperature=0.2,
        )
        context = "\n\n".join(context_chunks) or "No matching context."
        response = llm.invoke(
            [
                (
                    "system",
                    "Draft concise customer support resolutions using only provided context. Use plain text only. Do not use Markdown, bold markers, bullet dashes, or numbered lists.",
                ),
                (
                    "user",
                    f"Customer issue:\n{query}\n\nContext:\n{context}\n\nDraft the resolution with short paragraphs for issue summary, recommended resolution, validation, and sources.",
                ),
            ]
        )
        content = str(response.content).strip()
        if not content:
            raise RuntimeError("Groq-compatible LLM returned an empty response.")
        return content
    except Exception as exc:
        raise RuntimeError(f"Groq-compatible LLM request failed: {exc}") from exc


def generate_incident_chat_answer(question: str, incident_context: str, knowledge_context: list[str]) -> str:
    settings = get_settings()
    fallback = _fallback_chat_answer(question, incident_context, knowledge_context)
    if not settings.groq_api_key:
        return fallback
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.groq_model,
            temperature=0.1,
        )
        sources = "\n\n".join(knowledge_context) or "No source-of-truth documents found."
        response = llm.invoke(
            [
                (
                    "system",
                    "Answer operator questions about one support incident using only the incident, draft, citations, and source context provided. Be direct and cite source titles when relevant.",
                ),
                (
                    "user",
                    f"Incident context:\n{incident_context}\n\nSource context:\n{sources}\n\nQuestion:\n{question}",
                ),
            ]
        )
        content = str(response.content).strip()
        if not content:
            raise RuntimeError("Groq-compatible LLM returned an empty chat response.")
        return content
    except Exception as exc:
        raise RuntimeError(f"Groq-compatible LLM chat request failed: {exc}") from exc


def _fallback_resolution(query: str, context_chunks: list[str]) -> str:
    context = context_chunks[0] if context_chunks else "No matching runbook was found."
    return (
        f"Issue summary: We reviewed the reported issue: {query}\n\n"
        f"Recommended resolution: {context}\n\n"
        "Validation: Apply the recommended step, then confirm whether the issue is resolved."
    )


def _fallback_chat_answer(question: str, incident_context: str, knowledge_context: list[str]) -> str:
    sources = "\n".join(f"- {item}" for item in knowledge_context[:3]) or "- No source context found."
    return (
        f"Question: {question}\n\n"
        f"Incident and resolution context:\n{incident_context}\n\n"
        f"Relevant source context:\n{sources}"
    )
