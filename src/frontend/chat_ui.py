"""
대화형 채팅 UI - Streamlit의 chat_message 기반 인터페이스
역질문 흐름과 RAG 응답을 자연스럽게 표시하고, 추천 사업별 서류 준비 현황을 체크할 수 있습니다.
"""

import streamlit as st

from src.backend.rag.chain import get_rag_response

TRACKER_TOP_N = 3

_EXAMPLE_QUESTIONS = [
    "성북구 사는 25살 취준생인데 받을 수 있는 지원금 있어?",
    "경기도 사는 28살 직장인인데 목돈 모을 수 있는 통장 있어?",
    "월세 지원 받고 싶어",
]


# ----- 세션 상태 초기화 -----
def _init_session_state():
    """Streamlit 세션 상태를 초기화합니다."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "user_context" not in st.session_state:
        # 대화 중 수집된 유저 정보 (역질문으로 확보한 컨텍스트)
        st.session_state.user_context = {}


def _render_hero():
    st.markdown(
        """
        <div class="sg-hero">
          <div class="sg-eyebrow">청년 · 지자체 지원금 AI 비서</div>
          <h1>한 문장으로 묻고, 서류까지 챙기세요</h1>
          <p>거주지·나이·상태를 말하면 받을 수 있는 지원사업만 골라
          <b>구비서류 체크리스트</b>와 신청 팁까지 정리해 드려요.</p>
          <div class="sg-chips">
            <span>📚 청년 지원사업 38건</span><span>🗺️ 전국 + 7개 광역</span><span>✅ 서류 체크리스트</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sources(sources: list[dict]):
    with st.expander("📎 원본 출처 보기"):
        for source in sources:
            st.markdown(f"- [{source['title']}]({source.get('url') or '#'}) · {source.get('department', '')}")


def _render_doc_tracker(sources: list[dict], msg_idx: int):
    """추천 상위 사업의 구비서류를 실제로 체크하며 준비 현황을 확인하는 트래커"""
    programs = [s for s in sources[:TRACKER_TOP_N] if s.get("required_docs")]
    if not programs:
        return

    total = sum(len(p["required_docs"]) for p in programs)
    done = sum(
        bool(st.session_state.get(f"doc_{msg_idx}_{i}_{j}"))
        for i, p in enumerate(programs)
        for j in range(len(p["required_docs"]))
    )

    # 제목에 진행률을 넣으면 체크할 때마다 expander가 새로 그려져 접히므로 제목은 고정
    with st.expander("✅ 서류 준비 체크하기", expanded=False):
        st.progress(done / total if total else 0.0, text=f"준비 완료 {done}/{total}")
        cols = st.columns(len(programs))
        for i, (col, program) in enumerate(zip(cols, programs)):
            with col:
                st.markdown(f"**{program['title']}**")
                for j, doc in enumerate(program["required_docs"]):
                    st.checkbox(doc, key=f"doc_{msg_idx}_{i}_{j}")
                if program.get("url"):
                    st.markdown(f"[신청 바로가기 →]({program['url']})")


def _render_assistant_extras(msg: dict, msg_idx: int):
    if msg.get("sources"):
        _render_doc_tracker(msg["sources"], msg_idx)
        _render_sources(msg["sources"])


def render_chat_interface(user_profile: dict):
    """메인 채팅 인터페이스를 렌더링합니다."""

    _init_session_state()

    if not st.session_state.messages:
        _render_hero()
    else:
        st.markdown("#### 💬 시니피에와 대화하기")

    # 기존 메시지 렌더링
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                _render_assistant_extras(msg, idx)

    # 첫 화면: 예시 질문 버튼
    clicked_example = None
    if not st.session_state.messages:
        st.markdown("**이렇게 물어보세요 👇**")
        cols = st.columns(len(_EXAMPLE_QUESTIONS))
        for col, example in zip(cols, _EXAMPLE_QUESTIONS):
            if col.button(example, use_container_width=True):
                clicked_example = example

    # 유저 입력
    typed_input = st.chat_input("예: 성북구 사는 취준생인데 받을 수 있는 지원금 있어?")
    if user_input := (typed_input or clicked_example):
        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.spinner("조건에 맞는 지원사업을 찾고 있어요..."):
            response = get_rag_response(
                query=user_input,
                user_profile=user_profile,
                conversation_history=st.session_state.messages[:-1],
                user_context=st.session_state.user_context,
            )

        st.session_state.messages.append({
            "role": "assistant",
            "content": response["answer"],
            "sources": response.get("sources", []),
        })

        # 대화 중 수집된 유저 컨텍스트 업데이트
        if response.get("extracted_context"):
            st.session_state.user_context.update(response["extracted_context"])

        # 새 메시지를 히스토리 렌더링 경로로 다시 그려 체크박스 상태가 유지되게 함
        st.rerun()
