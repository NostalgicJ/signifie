"""
시니피에(Signifié) - 메인 Streamlit 앱 엔트리포인트
실행: streamlit run app.py
"""

import streamlit as st

from scripts.seed_sample_data import ensure_seeded
from src.frontend.chat_ui import render_chat_interface
from src.frontend.sidebar import render_sidebar


@st.cache_resource(show_spinner="지원사업 데이터를 불러오는 중...")
def _prepare_vectorstore() -> bool:
    """배포 환경 첫 실행 시 Vector DB가 비어 있으면 시드 데이터를 적재"""
    ensure_seeded()
    return True


def main():
    st.set_page_config(
        page_title="시니피에 | 맞춤형 지원금 AI 비서",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _prepare_vectorstore()

    # 사이드바: 유저 프로필 입력 & 설정
    user_profile = render_sidebar()

    # 메인 영역: 대화형 RAG 인터페이스
    render_chat_interface(user_profile)


if __name__ == "__main__":
    main()
