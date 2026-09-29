"""
시니피에(Signifié) - 메인 Streamlit 앱 엔트리포인트
실행: streamlit run app.py
"""

import streamlit as st

from scripts.seed_sample_data import ensure_seeded, seed_file_hash
from src.frontend.chat_ui import render_chat_interface
from src.frontend.sidebar import render_sidebar


@st.cache_resource(show_spinner="지원사업 데이터를 불러오는 중...")
def _prepare_vectorstore(data_version: str) -> bool:
    """Vector DB가 비어 있거나 시드 데이터가 바뀌면 적재 (data_version이 바뀌면 캐시도 무효화)"""
    ensure_seeded()
    return True


_CUSTOM_CSS = """
<style>
.block-container {max-width: 920px; padding-top: 2.2rem;}
.sg-hero {padding: 28px 30px; border-radius: 16px; margin-bottom: 18px;
  background: linear-gradient(135deg, rgba(27,107,71,.12), rgba(27,107,71,.03));
  border: 1px solid rgba(27,107,71,.22);}
.sg-hero h1 {font-size: 1.9rem; line-height: 1.3; margin: 6px 0 8px; padding: 0; letter-spacing: -.02em;}
.sg-hero p {opacity: .85; margin: 0 0 14px; font-size: 1.02rem;}
.sg-eyebrow {font-size: .82rem; font-weight: 700; color: #1B6B47; letter-spacing: .04em;}
.sg-chips {display: flex; flex-wrap: wrap; gap: 8px;}
.sg-chips span {font-size: .85rem; padding: 4px 11px; border-radius: 999px;
  background: rgba(27,107,71,.10); border: 1px solid rgba(27,107,71,.18);}
@media (prefers-color-scheme: dark) { .sg-eyebrow {color: #63CE97;} }
[data-testid="stChatMessage"] table {font-size: .9rem;}
/* 우측 상단 툴바(Fork·GitHub·메뉴) 숨김 - 사이드바 여는 버튼이 있는 헤더 자체는 유지 */
[data-testid="stToolbar"] {display: none !important;}
[data-testid="stHeader"] {background: transparent;}
</style>
"""


def main():
    st.set_page_config(
        page_title="시니피에 | 맞춤형 지원금 AI 비서",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="auto",  # 데스크톱은 펼침, 모바일은 접힘
    )

    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
    _prepare_vectorstore(seed_file_hash())

    # 사이드바: 유저 프로필 입력 & 설정
    user_profile = render_sidebar()

    # 메인 영역: 대화형 RAG 인터페이스
    render_chat_interface(user_profile)


if __name__ == "__main__":
    main()
