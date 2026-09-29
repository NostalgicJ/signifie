"""
대화형 채팅 UI - Streamlit의 chat_message 기반 인터페이스
역질문 흐름과 RAG 응답을 자연스럽게 표시합니다.
"""

import streamlit as st
from src.backend.rag.chain import get_rag_response


# ----- 세션 상태 초기화 -----
def _init_session_state():
    """Streamlit 세션 상태를 초기화합니다."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "user_context" not in st.session_state:
        # 대화 중 수집된 유저 정보 (역질문으로 확보한 컨텍스트)
        st.session_state.user_context = {}


def _format_source(source: dict) -> str:
    return f"- [{source['title']}]({source.get('url') or '#'}) · {source.get('department', '')}"


_EXAMPLE_QUESTIONS = [
    "성북구 사는 25살 취준생인데 받을 수 있는 지원금 있어?",
    "경기도 사는 28살 직장인인데 목돈 모을 수 있는 통장 있어?",
    "월세 지원 받고 싶어",
]


def render_chat_interface(user_profile: dict):
    """메인 채팅 인터페이스를 렌더링합니다."""

    _init_session_state()

    # 헤더
    st.title("💬 시니피에와 대화하기")
    st.caption("지원금, 자격 조건, 제출 서류 등 무엇이든 물어보세요!")

    # 기존 메시지 렌더링
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # 출처 정보가 있으면 expander로 표시
            if msg.get("sources"):
                with st.expander("📎 원본 출처 보기"):
                    for source in msg["sources"]:
                        st.markdown(_format_source(source))

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
        # 유저 메시지 추가 & 표시
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # AI 응답 생성
        with st.chat_message("assistant"):
            with st.spinner("관련 지원사업을 검색하고 있어요..."):
                response = get_rag_response(
                    query=user_input,
                    user_profile=user_profile,
                    conversation_history=st.session_state.messages[:-1],
                    user_context=st.session_state.user_context,
                )

            # 응답 표시
            st.markdown(response["answer"])

            # 출처가 있으면 표시
            if response.get("sources"):
                with st.expander("📎 원본 출처 보기"):
                    for source in response["sources"]:
                        st.markdown(_format_source(source))

        # 어시스턴트 메시지 저장
        st.session_state.messages.append({
            "role": "assistant",
            "content": response["answer"],
            "sources": response.get("sources", []),
        })

        # 대화 중 수집된 유저 컨텍스트 업데이트
        if response.get("extracted_context"):
            st.session_state.user_context.update(response["extracted_context"])
