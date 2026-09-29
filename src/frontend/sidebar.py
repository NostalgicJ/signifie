"""
사이드바 UI - 유저 프로필(자격 조건) 입력 패널
사전에 입력된 프로필 정보는 RAG 질의 시 컨텍스트로 활용됩니다.
"""

import streamlit as st

from src.backend.rag.profile import EMPLOYMENT_STATUSES, SIDO_ALIASES, SIGUNGU_BY_SIDO

NOT_SELECTED = "선택 안함"


def render_sidebar() -> dict:
    """사이드바를 렌더링하고 유저 프로필 딕셔너리를 반환합니다."""

    with st.sidebar:
        st.title("🔍 시니피에")
        st.caption("RAG 기반 맞춤형 지원금 AI 비서")
        st.divider()

        st.subheader("📋 내 정보 (선택입력)")
        st.caption("입력하면 더 정확한 추천을 받을 수 있어요.")

        age = st.number_input("나이", min_value=15, max_value=100, value=None, step=1)
        # 자유 입력 대신 선택형으로 받아 지역 표기 불일치(서울시/서울특별시)를 원천 차단
        sido = st.selectbox("거주지 (시/도)", options=[NOT_SELECTED, *SIDO_ALIASES.keys()], index=0)
        sigungu_options = SIGUNGU_BY_SIDO.get(sido, [])
        sigungu = NOT_SELECTED
        if sigungu_options:
            sigungu = st.selectbox("거주지 (시/군/구)", options=[NOT_SELECTED, *sigungu_options], index=0)
        employment_status = st.selectbox(
            "현재 상태",
            options=[NOT_SELECTED, *EMPLOYMENT_STATUSES],
            index=0,
        )
        income_level = st.selectbox(
            "소득 수준 (기준중위소득 %)",
            options=[NOT_SELECTED, "50% 이하", "50~100%", "100~150%", "150% 이상", "모름"],
            index=0,
        )

        st.divider()

        # 대화 초기화 버튼
        if st.button("🗑️ 대화 초기화", use_container_width=True):
            st.session_state.messages = []
            st.session_state.user_context = {}
            st.rerun()

        st.divider()
        from src.backend.llm.bedrock_client import is_mock_mode

        if is_mock_mode():
            st.caption("⚙️ 데모 모드: AWS 키 미설정 — 로컬 임베딩 + 템플릿 응답")
        else:
            st.caption("⚙️ AWS Bedrock (Claude + Titan) 연결됨")
        st.caption("© 2026 시니피에 | 고려대학교 x AWS AI Innovators Challenge")

    # 유저 프로필 딕셔너리 구성 (None이면 미입력)
    profile = {
        "age": age,
        "region_sido": sido if sido != NOT_SELECTED else None,
        "region_sigungu": sigungu if sigungu != NOT_SELECTED else None,
        "employment_status": employment_status if employment_status != NOT_SELECTED else None,
        "income_level": income_level if income_level != NOT_SELECTED else None,
    }

    return profile
