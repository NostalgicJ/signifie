"""
대화형 채팅 UI - Streamlit의 chat_message 기반 인터페이스
- 질문을 보내면 검색 과정(조건 파악 → 필터 → 검색)을 단계별로 보여준 뒤 답변을 타이핑하듯 출력
- 새 답변이 오면 방금 한 질문 위치로 스크롤해 답변을 처음부터 읽을 수 있게 함
- 추천 사업별 서류 준비 현황을 체크할 수 있는 트래커 제공
"""

import time

import streamlit as st

from src.backend.rag.chain import get_rag_response

TRACKER_TOP_N = 3
STREAM_SECONDS = 1.2  # 답변 전체를 타이핑하듯 보여주는 시간

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
          <div class="sg-eyebrow">Signifié · 청년 지원금 AI 비서</div>
          <h1>한 문장으로 묻고,<br>서류까지 챙기세요</h1>
          <p>거주지·나이·상태를 말하면 받을 수 있는 지원사업만 골라
          <b>구비서류 체크리스트</b>와 신청 팁까지 정리해 드려요.</p>
          <div class="sg-chips">
            <span>청년 지원사업 38건</span><span>전국 + 7개 광역</span><span>서류 체크리스트</span>
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


def _render_trace(trace: dict | None):
    """답변이 어떻게 만들어졌는지 한 줄 요약 + 펼치면 단계별 과정"""
    if not trace:
        return
    with st.expander(trace["summary"], expanded=False):
        for i, step in enumerate(trace.get("steps", []), 1):
            st.markdown(f"{i}. {step}")


def _render_user(msg: dict, turn: int):
    with st.chat_message("user"):
        st.markdown(f'<div class="sg-turn">질문 {turn}</div>', unsafe_allow_html=True)
        st.markdown(msg["content"])


def _render_assistant(msg: dict, msg_idx: int):
    with st.chat_message("assistant"):
        _render_trace(msg.get("trace"))
        st.markdown(msg["content"])
        if msg.get("sources"):
            _render_doc_tracker(msg["sources"], msg_idx)
            _render_sources(msg["sources"])


def _stream_words(text: str):
    """답변을 조금씩 흘려보내 타이핑되는 것처럼 보여줌 (전체 약 STREAM_SECONDS초)"""
    chunks = text.split(" ")
    delay = STREAM_SECONDS / max(len(chunks), 1)
    for chunk in chunks:
        yield chunk + " "
        time.sleep(delay)


def _scroll_to_latest_question():
    """새 답변이 오면 방금 한 질문으로 스크롤 (긴 답변의 끝이 아니라 처음부터 읽도록)"""
    # 같은 위치의 st.html은 재사용되어 스크립트가 다시 실행되지 않으므로, 메시지 수로 키를 바꿔 매번 새로 그림
    st.container(key=f"scroll_{len(st.session_state.messages)}").html(
        f"""
        <script>
        // Streamlit 채팅은 "맨 아래로 붙기" 스크롤을 쓰므로, 휠 이벤트로 붙기를 해제한 뒤 방금 한 질문으로 이동.
        // 렌더링 타이밍이 환경마다 달라 2.5초 동안 위치를 확인하며 맞추고, 사용자가 직접 스크롤하면 즉시 멈춤.
        (() => {{
          const container = document.querySelector('[data-testid="stAppScrollToBottomContainer"]');
          let userMoved = false;
          const stop = (e) => {{ if (e.isTrusted) userMoved = true; }};
          ['wheel', 'touchmove', 'keydown'].forEach((t) => window.addEventListener(t, stop, {{capture: true, once: true}}));

          const target = () => {{
            const turns = document.querySelectorAll('.sg-turn');
            const last = turns[turns.length - 1];
            return last ? last.closest('[data-testid="stChatMessage"]') : null;
          }};
          const align = () => {{
            const el = target();
            if (!el || !container) return;
            const offset = el.getBoundingClientRect().top - container.getBoundingClientRect().top;
            if (Math.abs(offset - 72) < 8) return;
            container.dispatchEvent(new WheelEvent('wheel', {{deltaY: -200, bubbles: true}}));
            setTimeout(() => el.scrollIntoView({{block: 'start'}}), 60);
          }};

          const started = Date.now();
          const timer = setInterval(() => {{
            if (userMoved || Date.now() - started > 2500) return clearInterval(timer);
            align();
          }}, 250);
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def render_chat_interface(user_profile: dict):
    """메인 채팅 인터페이스를 렌더링합니다."""

    _init_session_state()
    messages = st.session_state.messages

    if not messages:
        _render_hero()

    # 기존 메시지 렌더링
    turn = 0
    for idx, msg in enumerate(messages):
        if msg["role"] == "user":
            turn += 1
            _render_user(msg, turn)
        else:
            _render_assistant(msg, idx)

    if st.session_state.pop("scroll_to_latest", False):
        _scroll_to_latest_question()

    # 첫 화면: 예시 질문 버튼
    clicked_example = None
    if not messages:
        st.markdown('<div class="sg-examples-title">이렇게 물어보세요</div>', unsafe_allow_html=True)
        cols = st.columns(len(_EXAMPLE_QUESTIONS))
        for col, example in zip(cols, _EXAMPLE_QUESTIONS):
            if col.button(example, use_container_width=True):
                clicked_example = example

    # 유저 입력
    typed_input = st.chat_input("예: 성북구 사는 취준생인데 받을 수 있는 지원금 있어?")
    user_input = typed_input or clicked_example
    if not user_input:
        return

    messages.append({"role": "user", "content": user_input})
    _render_user(messages[-1], turn + 1)

    with st.chat_message("assistant"):
        with st.status("질문을 이해하고 있어요...", expanded=True) as status:
            st.write("① 질문과 사이드바에서 거주지·나이·상태를 파악하는 중")
            response = get_rag_response(
                query=user_input,
                user_profile=user_profile,
                conversation_history=messages[:-1],
                user_context=st.session_state.user_context,
            )
            for step in response.get("trace", {}).get("steps", [])[1:]:
                st.write(f"✓ {step}")
            status.update(label=response.get("trace", {}).get("summary", "완료"), state="complete", expanded=False)
        st.write_stream(_stream_words(response["answer"]))

    messages.append({
        "role": "assistant",
        "content": response["answer"],
        "sources": response.get("sources", []),
        "trace": response.get("trace"),
    })

    # 대화 중 수집된 유저 컨텍스트 업데이트
    if response.get("extracted_context"):
        st.session_state.user_context.update(response["extracted_context"])

    # 히스토리 렌더링 경로로 다시 그려 체크리스트 트래커를 붙이고, 방금 질문 위치로 스크롤
    st.session_state.scroll_to_latest = True
    st.rerun()
