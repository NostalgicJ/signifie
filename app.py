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
.block-container {max-width: 900px; padding-top: 2rem;}

/* 첫 화면 히어로 - 대회 포스터 톤 (네이비 → 블루) */
.sg-hero {padding: 34px 34px 30px; border-radius: 20px; margin-bottom: 22px; color: #fff;
  background: linear-gradient(125deg, #050B1F 0%, #0B2170 45%, #1D4ED8 80%, #22B8E6 100%);
  box-shadow: 0 14px 40px rgba(11, 33, 112, .25);}
.sg-hero h1 {color: #fff; font-size: 2.1rem; line-height: 1.25; margin: 8px 0 12px; padding: 0;
  font-weight: 800; letter-spacing: -.02em;}
.sg-hero p {color: rgba(255,255,255,.86); margin: 0 0 18px; font-size: 1.02rem; line-height: 1.6;}
.sg-hero b {color: #fff;}
.sg-eyebrow {font-size: .8rem; font-weight: 700; letter-spacing: .08em; color: #8FD3FF; text-transform: uppercase;}
.sg-chips {display: flex; flex-wrap: wrap; gap: 8px;}
.sg-chips span {font-size: .84rem; padding: 5px 12px; border-radius: 999px; color: #fff;
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25);}
.sg-examples-title {font-weight: 700; margin: 4px 0 8px; color: #0B1736;}

/* 대화: 질문과 답변을 한눈에 구분 */
[data-testid="stChatMessage"] {border-radius: 16px; padding: 14px 18px; margin-bottom: 10px; scroll-margin-top: 72px;}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: #E3ECFF; border: 1px solid #C9D8FB; margin-top: 26px;}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
  background: #FFFFFF; border: 1px solid #DCE4F5; box-shadow: 0 4px 16px rgba(11, 23, 54, .05);}
.sg-turn {font-size: .75rem; font-weight: 800; color: #2563EB; letter-spacing: .06em; margin-bottom: 2px;}
[data-testid="stChatMessage"] table {font-size: .88rem;}
[data-testid="stChatMessage"] h3 {font-size: 1.15rem; margin-top: 1.2rem; padding-top: .6rem;
  border-top: 1px dashed #D5DEF2;}

/* 사이드바 입력 박스 대비 */
[data-testid="stSidebar"] [data-testid="stAlert"] {background: #14295C; color: #E6ECFF;}

/* 우측 상단 Fork·GitHub·메뉴만 숨김 - 같은 툴바 안의 사이드바 열기 버튼(stExpandSidebarButton)은 유지 */
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {display: none !important;}
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
