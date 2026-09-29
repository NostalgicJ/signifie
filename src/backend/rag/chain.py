"""
RAG 체인 - 프로필 병합 -> (역질문 | 메타데이터 필터 검색) -> 프롬프트 조합 -> LLM 호출 -> 응답 정형화
AWS 키가 없으면 LLM 대신 템플릿 렌더러가 같은 형식(요약 표 + 체크리스트 + 팁)으로 응답합니다.
"""

import json
import logging

from src.backend.llm.bedrock_client import invoke_llm, is_mock_mode
from src.backend.rag.profile import (
    detect_categories,
    merge_profile,
    missing_required_fields,
    normalize_region,
)
from src.backend.rag.prompts import (
    CLARIFY_TEMPLATE,
    CONTEXT_EXTRACTION_TEMPLATE,
    RAG_QUERY_TEMPLATE,
    SYSTEM_PROMPT,
)
from src.backend.rag.vectorstore import build_where_filter, get_collection, search_documents

logger = logging.getLogger(__name__)

MAX_CLARIFY_TURNS = 2
N_RESULTS = 5
TOP_DETAIL = 3

_RELAX_NOTES = {
    0: "",
    1: "소득 조건에 맞는 공고가 없어 소득 조건을 빼고 찾았어요.",
    2: "상태·소득 조건에 딱 맞는 공고가 없어 해당 조건을 완화해 찾았어요.",
    3: "연령 조건까지 맞는 공고가 없어 거주지 기준으로만 찾았어요. 자격 조건을 꼭 확인하세요.",
}


# ---------- 텍스트 구성 ----------

def _profile_summary(profile: dict) -> str:
    parts = []
    if profile.get("region_sido"):
        sido = profile["region_sido"].replace("특별시", "").replace("광역시", "").replace("특별자치도", "").replace("특별자치시", "")
        parts.append(f"{sido} {profile.get('region_sigungu') or ''}".strip())
    if profile.get("age"):
        parts.append(f"{profile['age']}세")
    if profile.get("employment_status"):
        parts.append(profile["employment_status"])
    if profile.get("income_level") and profile["income_level"] != "모름":
        parts.append(f"중위소득 {profile['income_level']}")
    return " · ".join(parts)


def _build_user_profile_text(profile: dict) -> str:
    labels = {
        "region_sido": "거주 시/도",
        "region_sigungu": "거주 시/군/구",
        "age": "나이",
        "employment_status": "현재 상태",
        "income_level": "소득 수준(기준중위소득)",
    }
    parts = [f"- {label}: {profile[key]}" for key, label in labels.items() if profile.get(key)]
    return "\n".join(parts) if parts else "- 아직 파악된 정보 없음"


def _build_conversation_context(conversation_history: list[dict], max_turns: int = 6) -> str:
    recent = conversation_history[-max_turns:]
    parts = []
    for msg in recent:
        role = "사용자" if msg["role"] == "user" else "AI"
        parts.append(f"{role}: {msg['content']}")
    return "\n".join(parts) if parts else "첫 대화입니다."


def _split(value: str) -> list[str]:
    return [v for v in (value or "").split("|") if v]


def _format_retrieved_context(search_results: dict) -> tuple[str, list[dict]]:
    documents = search_results.get("documents", [])
    metadatas = search_results.get("metadatas", [])

    if not documents:
        return "관련 공고를 찾지 못했습니다.", []

    context_parts = []
    sources = []

    for i, (doc, meta) in enumerate(zip(documents, metadatas), 1):
        docs_list = ", ".join(_split(meta.get("required_docs", "")))
        tips = " / ".join(_split(meta.get("tips", "")))
        context_parts.append(
            f"### 공고 {i}: {meta.get('title')}\n"
            f"- 담당기관: {meta.get('department', '미상')}\n"
            f"- 지역: {meta.get('region_label')} | 연령: {meta.get('age_label')} | 대상: {meta.get('target_statuses')}\n"
            f"- 소득기준: {meta.get('income_text') or '확인 필요'}\n"
            f"- 신청기간: {meta.get('deadline', '확인 필요')}\n"
            f"- 구비서류: {docs_list or '원문 확인 필요'}\n"
            f"- 신청팁: {tips or '없음'}\n"
            f"- 신청링크: {meta.get('url', '')}\n"
            f"- 본문:\n{doc}\n"
        )
        sources.append({
            "title": meta.get("title", f"공고 {i}"),
            "department": meta.get("department", ""),
            "url": meta.get("url", ""),
            "deadline": meta.get("deadline", ""),
            "required_docs": _split(meta.get("required_docs", "")),
        })

    return "\n---\n".join(context_parts), sources


# ---------- 템플릿 렌더러 (키 미설정 데모 모드 / LLM 실패 시 fallback) ----------

def _render_recommendation(profile: dict, metadatas: list[dict], relax_level: int) -> str:
    if not metadatas:
        return (
            "현재 조건으로는 적재된 공고 중 맞는 지원사업을 찾지 못했어요. 😥\n\n"
            "거주지나 나이를 다시 확인해 주시거나, [온통청년](https://www.youthcenter.go.kr)에서 전체 정책을 검색해 보세요."
        )

    lines = []
    summary = _profile_summary(profile)
    lines.append(f"**{summary}** 기준으로 찾은 지원사업이에요." if summary else "조건에 맞는 지원사업이에요.")
    if _RELAX_NOTES.get(relax_level):
        lines.append(f"\n> ⚠️ {_RELAX_NOTES[relax_level]}")

    lines.append("\n| 사업명 | 지원 내용 | 대상 | 신청 기간 |\n|---|---|---|---|")
    for meta in metadatas:
        benefit = meta.get("benefit", "").replace("|", "/")
        if len(benefit) > 60:
            benefit = benefit[:60] + "…"
        lines.append(
            f"| {meta.get('title')} | {benefit} | {meta.get('region_label')} · {meta.get('age_label')} "
            f"| {meta.get('deadline', '확인 필요')} |"
        )

    for i, meta in enumerate(metadatas[:TOP_DETAIL], 1):
        lines.append(f"\n### {i}. {meta.get('title')}")
        lines.append(f"- **지원 대상**: {meta.get('target_summary') or meta.get('target_statuses')}")
        lines.append(f"- **지원 내용**: {meta.get('benefit')}")
        if meta.get("income_text"):
            lines.append(f"- **소득 기준**: {meta.get('income_text')}")
        lines.append(f"- **신청 방법**: {meta.get('how_to_apply') or '원문 확인 필요'}")
        lines.append(f"- **담당 기관**: {meta.get('department')}")

        docs = _split(meta.get("required_docs", ""))
        lines.append("\n#### 📋 필요 서류 체크리스트")
        if docs:
            lines.extend(f"- [ ] {d}" for d in docs)
        else:
            lines.append("- [ ] 원문 공고에서 확인 필요")

        tips = _split(meta.get("tips", ""))
        if tips:
            lines.append("\n#### 💡 신청 팁")
            lines.extend(f"- {t}" for t in tips)

        if meta.get("url"):
            lines.append(f"\n🔗 [신청 바로가기]({meta['url']})")

    missing = missing_required_fields(profile)
    if missing:
        lines.append(f"\n💬 {', '.join(missing)}를 알려주시면 더 정확하게 골라드릴게요.")
    lines.append("\n※ 금액·기간은 연도별로 바뀔 수 있으니 신청 전 원문 공고를 확인하세요.")
    return "\n".join(lines)


def _render_clarify(profile: dict, missing: list[str], preview_titles: list[str]) -> str:
    examples = {
        "거주지": "(예: 서울 성북구, 경기 수원시)",
        "나이": "(예: 만 25세)",
        "현재 상태": "(재학생 / 취업준비생 / 직장인 / 자영업자)",
    }
    known = _profile_summary(profile)
    lines = ["딱 맞는 지원금을 찾아드릴게요! 🙌  "]
    if known:
        lines.append(f"지금까지 **{known}**(으)로 이해했어요.  ")
    lines.append("지역·연령·상태마다 받을 수 있는 사업이 달라서, 아래 정보를 알려주세요.\n")
    lines.extend(f"{i}. **{m}** {examples.get(m, '')}" for i, m in enumerate(missing, 1))
    if preview_titles:
        lines.append(f"\n우선 전국 공통으로는 {', '.join(preview_titles)} 같은 사업이 있어요.")
    lines.append("\n_왼쪽 사이드바에 입력해 두면 다음부터는 묻지 않아요._")
    return "\n".join(lines)


# ---------- 메인 파이프라인 ----------

def _with_extra(where: dict | None, extra: list[dict]) -> dict | None:
    clauses = ([] if where is None else where.get("$and", [where])) + extra
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _search_with_relaxation(query: str, profile: dict) -> tuple[dict, int]:
    """
    조건을 단계적으로 완화하며 검색. 지역 조건은 절대 제거하지 않습니다.
    질문에 분야 키워드(월세·통장 등)가 있으면 해당 분야 공고를 먼저 채우고, 모자라면 전체 분야로 보충합니다.
    신규 모집이 종료된 사업은 사용자가 이름으로 직접 묻지 않는 한 제외합니다.
    """
    search_query = " ".join(filter(None, [query, profile.get("employment_status")]))
    categories = detect_categories(query)
    base_extra = [] if "내일채움" in query else [{"is_open": {"$eq": True}}]

    results: dict = {"documents": [], "metadatas": [], "distances": []}
    for level in range(4):
        where = build_where_filter(profile, level=level)
        merged = {"documents": [], "metadatas": [], "distances": []}
        seen: set[str] = set()

        passes = []
        if categories:
            passes.append(base_extra + [{"category": {"$in": categories}}])
        passes.append(base_extra)

        for extra in passes:
            if len(merged["documents"]) >= N_RESULTS:
                break
            found = search_documents(query=search_query, n_results=N_RESULTS, where_filter=_with_extra(where, extra))
            for doc, meta, dist in zip(found["documents"], found["metadatas"], found["distances"]):
                if meta["title"] in seen or len(merged["documents"]) >= N_RESULTS:
                    continue
                seen.add(meta["title"])
                merged["documents"].append(doc)
                merged["metadatas"].append(meta)
                merged["distances"].append(dist)

        logger.info(f"[RAG] level={level} where={where} categories={categories} -> {len(merged['documents'])}건")
        if merged["documents"]:
            return merged, level
        results = merged
    return results, 3


def _llm_extract_context(conversation_history: list[dict]) -> dict:
    """(Bedrock 모드) 대화에서 규칙으로 못 잡은 정보를 LLM으로 보완 추출"""
    if is_mock_mode() or len(conversation_history) < 4:
        return {}
    conversation_text = _build_conversation_context(conversation_history, max_turns=10)
    prompt = CONTEXT_EXTRACTION_TEMPLATE.format(conversation=conversation_text)
    try:
        raw = json.loads(invoke_llm(prompt, temperature=0.0, max_tokens=512))
    except Exception as e:  # noqa: BLE001 - 추출 실패는 무시하고 진행
        logger.warning(f"컨텍스트 추출 실패 (무시): {e}")
        return {}

    extracted = {}
    if raw.get("region"):
        sido, sigungu = normalize_region(raw["region"])
        if sido:
            extracted["region_sido"], extracted["region_sigungu"] = sido, sigungu
    if isinstance(raw.get("age"), int):
        extracted["age"] = raw["age"]
    if raw.get("employment_status"):
        extracted["employment_status"] = raw["employment_status"]
    return extracted


def get_rag_response(
    query: str,
    user_profile: dict,
    conversation_history: list[dict],
    user_context: dict,
) -> dict:
    """
    RAG 파이프라인 메인 함수

    Returns:
        {"answer": str, "sources": list[dict], "extracted_context": dict, "mode": "clarify"|"recommend"}
        extracted_context는 세션에 저장되어 다음 턴의 프로필로 이어집니다.
    """
    # Step 1: 사이드바 + 이전 대화 + 이번 질문을 하나의 프로필로 병합
    profile = merge_profile(user_profile, user_context, query)
    clarify_count = int(user_context.get("_clarify_count", 0))
    missing = missing_required_fields(profile)
    logger.info(f"[RAG] profile={profile} missing={missing} clarify_count={clarify_count}")

    context_to_save = {k: v for k, v in profile.items() if k in ("region_sido", "region_sigungu", "age", "employment_status")}

    # Step 2: 거주지/나이를 모르면 역질문 (최대 2회, 이후에는 확보한 정보로 추천)
    needs_clarify = ("거주지" in missing or "나이" in missing) and clarify_count < MAX_CLARIFY_TURNS
    if needs_clarify:
        preview = search_documents(query=query, n_results=3, where_filter={"region_sido": "전국"})
        preview_titles = [m["title"] for m in preview.get("metadatas", [])][:2]

        answer = ""
        if not is_mock_mode():
            answer = invoke_llm(
                prompt=CLARIFY_TEMPLATE.format(
                    query=query,
                    user_profile=_build_user_profile_text(profile),
                    missing=", ".join(missing),
                    preview=", ".join(preview_titles) or "없음",
                ),
                system_prompt=SYSTEM_PROMPT,
                max_tokens=512,
                temperature=0.3,
            )
        if not answer:
            answer = _render_clarify(profile, missing, preview_titles)

        known = _profile_summary(profile)
        return {
            "answer": answer,
            "sources": [],
            "extracted_context": {**context_to_save, "_clarify_count": clarify_count + 1},
            "mode": "clarify",
            "trace": {
                "summary": f"🧭 추천 전에 {', '.join(missing)} 정보가 필요해요",
                "steps": [
                    f"질문에서 파악한 조건: {known or '없음'}",
                    f"부족한 정보: {', '.join(missing)} → 되묻기 ({clarify_count + 1}/{MAX_CLARIFY_TURNS}회)",
                ],
            },
        }

    # Step 3: 메타데이터 필터 + 유사도 검색 (지역은 끝까지 유지하며 조건 완화)
    search_results, relax_level = _search_with_relaxation(query, profile)
    context_text, sources = _format_retrieved_context(search_results)
    logger.info(f"[RAG] 검색 결과 {len(sources)}건 (완화 단계 {relax_level})")

    # Step 4: LLM 답변 생성 (실패하거나 키가 없으면 템플릿 렌더링)
    answer = ""
    used_llm = False
    if not is_mock_mode() and sources:
        answer = invoke_llm(
            prompt=RAG_QUERY_TEMPLATE.format(
                context=context_text,
                user_profile=_build_user_profile_text(profile),
                filter_note=_RELAX_NOTES.get(relax_level) or "모든 조건(지역·연령·상태·소득)을 만족하는 공고입니다.",
                conversation_context=_build_conversation_context(conversation_history),
                query=query,
            ),
            system_prompt=SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.3,
        )
        used_llm = bool(answer)
    if not answer:
        answer = _render_recommendation(profile, search_results.get("metadatas", []), relax_level)

    # Step 5: (Bedrock 모드) 대화 기반 추가 정보 추출
    llm_context = _llm_extract_context(conversation_history + [{"role": "user", "content": query}])
    for key, value in llm_context.items():
        context_to_save.setdefault(key, value)

    return {
        "answer": answer,
        "sources": sources,
        "extracted_context": {**context_to_save, "_clarify_count": clarify_count},
        "mode": "recommend",
        "trace": _build_trace(profile, query, relax_level, len(sources), used_llm),
    }


def _build_trace(profile: dict, query: str, relax_level: int, found: int, used_llm: bool) -> dict:
    """답변이 어떻게 만들어졌는지 UI에 보여줄 검색 과정 요약"""
    summary_profile = _profile_summary(profile) or "조건 미입력"
    total = get_collection().count()

    filters = []
    if profile.get("region_sido"):
        filters.append(f"지역(전국 + {profile['region_sido']})")
    if profile.get("age") and relax_level <= 2:
        filters.append(f"연령({profile['age']}세 포함)")
    if profile.get("employment_status") and relax_level <= 1:
        filters.append(f"대상({profile['employment_status']})")
    if profile.get("income_level") and relax_level == 0:
        filters.append(f"소득({profile['income_level']})")
    categories = detect_categories(query)

    steps = [
        f"조건 파악: {summary_profile}",
        f"메타데이터 필터: {' · '.join(filters) if filters else '없음 (전체 검색)'}",
    ]
    if categories:
        steps.append(f"관심 분야 우선: {', '.join(categories)}")
    if _RELAX_NOTES.get(relax_level):
        steps.append(f"조건 완화: {_RELAX_NOTES[relax_level]}")
    steps.append(f"유사도 검색: 전체 {total}건 중 {found}건 선택")
    steps.append("답변 생성: AWS Bedrock Claude" if used_llm else "답변 생성: 검색 결과 템플릿 (데모 모드)")

    return {"summary": f"🔎 {summary_profile} 조건으로 {total}건 중 {found}건을 찾았어요", "steps": steps}
