# app.py
import html
import random
import re
import time

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from streamlit_mic_recorder import mic_recorder

# -----------------------------
# Config
# -----------------------------
st.set_page_config(page_title="음성 구구단 카드 게임", layout="wide")
FLIP_DELAY_SEC = 0.25


# -----------------------------
# Utils
# -----------------------------
def make_problems(n=16):
    probs = []
    for _ in range(n):
        a = random.randint(2, 9)
        b = random.randint(2, 9)
        probs.append({"a": a, "b": b, "ans": a * b})
    return probs


def parse_int_from_text(txt: str):
    if not txt:
        return None
    m = re.search(r"(\d+)", txt)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def time_limit_for_level(level: int) -> int:
    return max(3, 11 - level)


# -----------------------------
# Card UI (Responsive + Flip + Timer + Hint on Top)
# -----------------------------
def render_cards_html(
    problems,
    revealed,
    results,
    current_idx,
    remain_sec,
    just_flipped_idx=None,
):
    css = """
<style>
.gugu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  padding: 8px;
}
@media (min-width: 900px) {
  .gugu-grid { grid-template-columns: repeat(4, minmax(140px, 1fr)); }
}

.gugu-card { height: 110px; perspective: 1000px; }
.gugu-card-inner {
  position: relative; width: 100%; height: 100%;
  transform-style: preserve-3d;
  transition: transform 520ms cubic-bezier(.2,.8,.2,1);
}
.gugu-card.is-flipped .gugu-card-inner { transform: rotateY(180deg); }
.gugu-card.just-flipped .gugu-card-inner { animation: flipIn 520ms cubic-bezier(.2,.8,.2,1); }
@keyframes flipIn { from { transform: rotateY(0); } to { transform: rotateY(180deg); } }

.gugu-face {
  position: absolute; inset: 0;
  border-radius: 16px;
  backface-visibility: hidden;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  font-weight: 800;
  user-select: none;
  box-shadow: 0 10px 24px rgba(0,0,0,.12);
  border: 1px solid rgba(0,0,0,.08);
}

.gugu-back {
  background: linear-gradient(135deg, rgba(30,144,255,.15), rgba(0,0,0,.04));
}

.gugu-front {
  transform: rotateY(180deg);
  background: rgba(255,255,255,.95);
  padding: 8px;
}

.gugu-hint {
  position: absolute;
  top: 8px;
  left: 10px;
  font-size: 12px;
  font-weight: 900;
  color: #1e88e5;
}

.gugu-title {
  font-size: 22px;
  font-weight: 950;
  color: #0f172a;
}

.gugu-timer {
  position: absolute;
  bottom: 8px;
  right: 8px;
  font-size: 13px;
  font-weight: 900;
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(255,255,255,.92);
  border: 1px solid rgba(0,0,0,.10);
}
.gugu-timer.safe { color: #1e7f43; }
.gugu-timer.warn { color: #b26a00; }
.gugu-timer.danger { color: #c62828; animation: blink .8s infinite alternate; }
@keyframes blink { from {opacity:1;} to {opacity:.45;} }

.gugu-badge {
  position: absolute;
  top: 6px;
  right: 8px;
  font-size: 16px;
}
</style>
"""

    parts = [css, '<div class="gugu-grid">']

    for i, p in enumerate(problems):
        is_rev = revealed[i]
        res = results[i]

        classes = ["gugu-card"]
        if is_rev:
            classes.append("is-flipped")
        if just_flipped_idx == i:
            classes.append("just-flipped")

        # Front main text
        if not is_rev:
            main = ""
            hint = ""
        else:
            a, b = p["a"], p["b"]
            if res is None:
                main = f"{a} × {b} = ?"
                hint = "🎤 말로 정답!"
            else:
                # ✅ 정답을 ? 자리에 표시
                main = f"{a} × {b} = {p['ans']}"
                hint = ""

        # Timer badge only for current unanswered revealed card
        timer_html = ""
        if i == current_idx and is_rev and res is None:
            sec = max(0, int(remain_sec))
            cls = "danger" if sec <= 3 else "warn" if sec <= 6 else "safe"
            timer_html = f'<div class="gugu-timer {cls}">⏱ {sec}s</div>'

        badge = "✅" if res is True else "❌" if res is False else ""

        parts.append(
            f"""
<div class="{' '.join(classes)}">
  <div class="gugu-card-inner">
    <div class="gugu-face gugu-back">🂠</div>

    <div class="gugu-face gugu-front">
      {f'<div class="gugu-hint">{hint}</div>' if hint else ''}
      {f'<div class="gugu-badge">{badge}</div>' if badge else ''}
      <div class="gugu-title">{html.escape(main)}</div>
      {timer_html}
    </div>
  </div>
</div>
"""
        )

    parts.append("</div>")
    return "\n".join(parts)


# -----------------------------
# State
# -----------------------------
if "level" not in st.session_state:
    st.session_state.level = 1
if "game" not in st.session_state:
    st.session_state.game = None
if "show_score_popup" not in st.session_state:
    st.session_state.show_score_popup = False


def start_new_game():
    st.session_state.game = {
        "problems": make_problems(16),
        "idx": 0,
        "results": [None] * 16,  # None / True / False
        "revealed": [False] * 16,
        "flipped_once": [False] * 16,  # ✅ flip 애니메이션 1회 보장
        "phase": "preflip",  # preflip -> answer
        "phase_start_ts": time.time(),
        "card_start_ts": None,  # answer에서만
        "last_heard": "",
        "status": "playing",  # playing / finished
    }
    st.session_state.show_score_popup = False


# -----------------------------
# Score Dialog (real modal)
# -----------------------------
@st.dialog("🎉 게임 종료!", width="large")
def show_score_dialog(score: int, correct: int):
    st.markdown(
        f"""
        <div style="text-align:center; padding: 8px 0 6px 0;">
          <div style="font-size:18px; font-weight:900; color:#111827;">결과</div>
          <div style="font-size:56px; font-weight:950; color:#0f172a; margin-top:6px;">{score}점</div>
          <div style="font-size:16px; font-weight:900; color:#334155; margin-top:6px;">정답 {correct} / 16</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("닫기", use_container_width=True):
            st.session_state.show_score_popup = False
            st.rerun()
    with c2:
        if st.button("다시 하기", use_container_width=True):
            start_new_game()
            st.rerun()
    with c3:
        if st.button("Level 올리고 다시", use_container_width=True):
            st.session_state.level += 1
            start_new_game()
            st.rerun()


# -----------------------------
# Header
# -----------------------------
st.title("🎤 음성 구구단 카드 게임")

top1, top2, top3 = st.columns([1, 1, 2])
with top1:
    st.write(f"**Level:** {st.session_state.level}")
with top2:
    if st.button("🔄 새 게임 시작", use_container_width=True):
        start_new_game()
        st.rerun()
with top3:
    st.caption(
        "모바일은 카드 영역 내부 스크롤로 전체 확인 가능 / Chrome 권장(마이크 권한 필요)"
    )

if st.session_state.game is None:
    st.info("새 게임을 시작해줘!")
    st.stop()

game = st.session_state.game

# -----------------------------
# Main Game
# -----------------------------
if game["status"] == "playing":
    st_autorefresh(interval=200, key="tick")  # 0.2초

    idx = game["idx"]
    limit = time_limit_for_level(st.session_state.level)
    now = time.time()

    # preflip(0.25s) -> answer(펼침+타이머 시작)
    if game["phase"] == "preflip":
        # 아직 펼치지 않음
        if now - game["phase_start_ts"] >= FLIP_DELAY_SEC:
            game["revealed"][idx] = True
            game["phase"] = "answer"
            game["card_start_ts"] = now
            # answer 진입 후 바로 rerun하면 타이밍이 더 안정적
            st.rerun()
    else:
        # answer
        game["revealed"][idx] = True
        if game["card_start_ts"] is None:
            game["card_start_ts"] = now

    # remain
    elapsed = (now - game["card_start_ts"]) if game["phase"] == "answer" else 0.0
    remain = max(0.0, limit - elapsed)

    # flip 애니메이션은 딱 1번만
    just_flipped = None
    if game["phase"] == "answer" and not game["flipped_once"][idx]:
        just_flipped = idx
        game["flipped_once"][idx] = True

    # Cards render (responsive + iframe scroll for mobile)
    card_html = render_cards_html(
        game["problems"],
        game["revealed"],
        game["results"],
        current_idx=idx,
        remain_sec=remain,
        just_flipped_idx=just_flipped,
    )
    components.html(card_html, height=720, scrolling=True)

    st.write("---")

    # Answer input only in answer phase
    if game["phase"] == "answer":
        st.write("### 🎙️ 정답 말하기")
        st.caption(
            "마이크 버튼 누르고 정답을 말해줘. (인식 텍스트에 숫자가 포함되면 판정)"
        )

        rec = mic_recorder(
            start_prompt="🎤 녹음 시작",
            stop_prompt="⏹️ 종료",
            just_once=True,
            key=f"mic_{idx}",
        )

        heard_text = ""
        if isinstance(rec, dict):
            heard_text = (rec.get("text") or "").strip()

        if heard_text:
            game["last_heard"] = heard_text

        # 시간 초과 -> 오답
        if remain <= 0.0 and game["results"][idx] is None:
            game["results"][idx] = False

        # 정답 판정
        if game["results"][idx] is None and game["last_heard"]:
            guess = parse_int_from_text(game["last_heard"])
            if guess is not None:
                game["results"][idx] = guess == game["problems"][idx]["ans"]

        # 다음 카드로
        if game["results"][idx] is not None:
            game["idx"] += 1
            game["last_heard"] = ""
            game["phase"] = "preflip"
            game["phase_start_ts"] = time.time()
            game["card_start_ts"] = None

            if game["idx"] >= 16:
                game["status"] = "finished"
                st.session_state.show_score_popup = True

            st.rerun()

# -----------------------------
# Finished: keep cards as-is, show dialog
# -----------------------------
if game["status"] == "finished":
    # 카드 상태 그대로 유지하면서 그대로 렌더(타이머/힌트는 더 이상 표시되지 않음)
    # current_idx는 마지막 카드로 고정(혹은 0으로)
    keep_idx = min(game["idx"], 15)

    card_html = render_cards_html(
        game["problems"],
        game["revealed"],
        game["results"],
        current_idx=keep_idx,
        remain_sec=0,
        just_flipped_idx=None,
    )
    components.html(card_html, height=720, scrolling=True)

    # 점수 모달
    if st.session_state.show_score_popup:
        correct = sum(1 for r in game["results"] if r is True)
        score = round(correct / 16 * 100)
        show_score_dialog(score, correct)
