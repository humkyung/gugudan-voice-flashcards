# app.py
import html
import random
import re
import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_mic_recorder import mic_recorder
import streamlit.components.v1 as components

# -----------------------------
# Config
# -----------------------------
st.set_page_config(page_title="음성 구구단 카드 게임", layout="wide")

FLIP_DELAY_SEC = 0.25  # ✅ 카드가 바뀔 때 0.25초 텀(자동으로 펼쳐지는 느낌)


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
    # level 1: 10초, level 2: 9초 ... 최소 3초
    return max(3, 11 - level)


# -----------------------------
# Card UI (Flip)
# -----------------------------
def inject_card_css():
    st.markdown(
        """
<style>
.gugu-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 14px;
}

.gugu-card {
  height: 110px;
  perspective: 1000px;
}

.gugu-card-inner {
  position: relative;
  width: 100%;
  height: 100%;
  transform-style: preserve-3d;
  transition: transform 520ms cubic-bezier(.2,.8,.2,1);
}

.gugu-card.is-flipped .gugu-card-inner {
  transform: rotateY(180deg);
}

/* 방금 펼쳐진 카드에만 “촥” */
.gugu-card.just-flipped .gugu-card-inner {
  animation: guguFlipIn 520ms cubic-bezier(.2,.8,.2,1) 1;
}

@keyframes guguFlipIn {
  0%   { transform: rotateY(0deg); }
  100% { transform: rotateY(180deg); }
}

/* 앞/뒤 면 */
.gugu-face {
  position: absolute;
  inset: 0;
  border-radius: 16px;
  backface-visibility: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  user-select: none;
  box-shadow: 0 10px 24px rgba(0,0,0,.10);
  border: 1px solid rgba(0,0,0,.08);
}

.gugu-back {
  background: linear-gradient(135deg, rgba(30, 144, 255, .14), rgba(0,0,0,.04));
}

.gugu-front {
  transform: rotateY(180deg);
  background: rgba(255,255,255,.92);
}

.gugu-title {
  font-size: 22px;
  letter-spacing: .2px;
}

.gugu-sub {
  font-size: 14px;
  opacity: .8;
  margin-top: 6px;
  font-weight: 600;
}

.gugu-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  font-size: 14px;
  font-weight: 800;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(0,0,0,.10);
  background: rgba(255,255,255,.85);
}

.gugu-pulse {
  position: absolute;
  inset: -1px;
  border-radius: 16px;
  border: 2px solid rgba(30, 144, 255, .55);
  pointer-events: none;
  animation: guguPulse 1.1s ease-in-out infinite;
}

@keyframes guguPulse {
  0%   { opacity: .25; transform: scale(1.00); }
  50%  { opacity: .75; transform: scale(1.01); }
  100% { opacity: .25; transform: scale(1.00); }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_cards_html(problems, revealed, results, current_idx, just_flipped_idx=None):
    css = """
<style>
.gugu-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 14px;
}
.gugu-card { height: 110px; perspective: 1000px; }
.gugu-card-inner {
  position: relative; width: 100%; height: 100%;
  transform-style: preserve-3d;
  transition: transform 520ms cubic-bezier(.2,.8,.2,1);
}
.gugu-card.is-flipped .gugu-card-inner { transform: rotateY(180deg); }
.gugu-card.just-flipped .gugu-card-inner { animation: guguFlipIn 520ms cubic-bezier(.2,.8,.2,1) 1; }
@keyframes guguFlipIn { 0% {transform: rotateY(0deg);} 100% {transform: rotateY(180deg);} }

.gugu-face {
  position: absolute; inset: 0;
  border-radius: 16px;
  backface-visibility: hidden;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; user-select: none;
  box-shadow: 0 10px 24px rgba(0,0,0,.10);
  border: 1px solid rgba(0,0,0,.08);
}
.gugu-back { background: linear-gradient(135deg, rgba(30,144,255,.14), rgba(0,0,0,.04)); }
.gugu-front { transform: rotateY(180deg); background: rgba(255,255,255,.92); }

.gugu-title { font-size: 22px; letter-spacing: .2px; }
.gugu-sub { font-size: 14px; opacity: .8; margin-top: 6px; font-weight: 600; }

.gugu-badge {
  position: absolute; top: 10px; right: 10px;
  font-size: 14px; font-weight: 800;
  padding: 6px 10px; border-radius: 999px;
  border: 1px solid rgba(0,0,0,.10);
  background: rgba(255,255,255,.85);
}
.gugu-pulse {
  position: absolute; inset: -1px;
  border-radius: 16px;
  border: 2px solid rgba(30,144,255,.55);
  pointer-events: none;
  animation: guguPulse 1.1s ease-in-out infinite;
}
@keyframes guguPulse {
  0% {opacity: .25; transform: scale(1.00);}
  50% {opacity: .75; transform: scale(1.01);}
  100% {opacity: .25; transform: scale(1.00);}
}
</style>
"""

    parts = [css, '<div class="gugu-grid">']

    for i, p in enumerate(problems):
        is_rev = revealed[i]
        res = results[i]

        card_classes = ["gugu-card"]
        if is_rev:
            card_classes.append("is-flipped")
        if just_flipped_idx is not None and i == just_flipped_idx:
            card_classes.append("just-flipped")

        if not is_rev:
            front_main = ""
            front_sub = ""
        else:
            a, b = p["a"], p["b"]
            if res is None:
                front_main = f"{a} × {b} = ?"
                front_sub = "말로 정답을 입력!"
            else:
                front_main = f"{a} × {b}"
                front_sub = f"정답: {p['ans']}"

        badge_html = ""
        if is_rev:
            if res is True:
                badge_html = '<div class="gugu-badge">✅</div>'
            elif res is False:
                badge_html = '<div class="gugu-badge">❌</div>'

        pulse_html = ""
        if i == current_idx and is_rev and res is None:
            pulse_html = '<div class="gugu-pulse"></div>'

        parts.append(
            f"""
<div class="{' '.join(card_classes)}">
  <div class="gugu-card-inner">
    <div class="gugu-face gugu-back">
      <div style="text-align:center;">
        <div class="gugu-title">🂠</div>
        <div class="gugu-sub">CARD {i+1:02d}</div>
      </div>
    </div>

    <div class="gugu-face gugu-front">
      {badge_html}
      {pulse_html}
      <div style="text-align:center; padding: 0 10px;">
        <div class="gugu-title">{html.escape(front_main)}</div>
        <div class="gugu-sub">{html.escape(front_sub)}</div>
      </div>
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

if "last_animated_idx" not in st.session_state:
    st.session_state.last_animated_idx = None


def start_new_game():
    st.session_state.game = {
        "problems": make_problems(16),
        "idx": 0,
        "results": [None] * 16,  # None / True / False
        "revealed": [False] * 16,
        "card_start_ts": None,  # answer phase에서만 타이머 시작 시간
        "status": "playing",  # playing / finished
        "last_heard": "",
        "phase": "preflip",  # preflip(0.25초) / answer
        "phase_start_ts": time.time(),
    }
    st.session_state.last_animated_idx = None


# -----------------------------
# UI Header
# -----------------------------
st.title("🎤 음성 구구단 카드 게임")

colA, colB, colC = st.columns([1, 1, 2])
with colA:
    st.write(f"**Level:** {st.session_state.level}")
with colB:
    if st.button("🔄 새 게임 시작", use_container_width=True):
        start_new_game()
        st.rerun()
with colC:
    st.caption("Chrome 권장 / 마이크 권한 허용 필요")

if st.session_state.game is None:
    st.info("아직 게임이 없어. **새 게임 시작**을 눌러줘!")
    st.stop()

game = st.session_state.game


# -----------------------------
# Main Game
# -----------------------------
if game["status"] == "playing":
    # 타이머/애니메이션 때문에 자동 새로고침
    st_autorefresh(interval=200, key="tick")  # 0.2초

    idx = game["idx"]
    level = st.session_state.level
    limit_sec = time_limit_for_level(level)

    now = time.time()

    # phase 안전장치(옛 state 대비)
    if "phase" not in game:
        game["phase"] = "preflip"
        game["phase_start_ts"] = now

    # -----------------------------
    # preflip(0.25초 텀) → answer(펼침+제한시간 시작)
    # -----------------------------
    if game["phase"] == "preflip":
        # 아직 펼치지 않음 (뒷면 유지)
        if now - game["phase_start_ts"] >= FLIP_DELAY_SEC:
            game["revealed"][idx] = True
            game["card_start_ts"] = now
            game["phase"] = "answer"
            game["phase_start_ts"] = now
            # answer로 넘어간 직후 rerun하면 플립 타이밍이 더 예쁨
            st.rerun()
    else:
        # answer 단계: 펼친 상태 유지
        game["revealed"][idx] = True
        if game["card_start_ts"] is None:
            game["card_start_ts"] = now

    # 타이머는 answer 단계에서만 진행
    if game["phase"] == "answer":
        elapsed = now - game["card_start_ts"]
    else:
        elapsed = 0.0

    remain = max(0.0, limit_sec - elapsed)

    # -----------------------------
    # HUD
    # -----------------------------
    st.subheader(f"카드 {idx+1}/16 — 제한시간: **{limit_sec}초**")

    if game["phase"] == "preflip":
        st.write("카드를 펼치는 중…")
        st.progress(1.0)  # 연출용(원하면 제거)
    else:
        st.progress(remain / limit_sec if limit_sec > 0 else 0.0)
        st.write(f"남은 시간: **{remain:.1f}초**")

    # -----------------------------
    # Cards Render
    # -----------------------------
    inject_card_css()

    just_flipped = None
    if game["phase"] == "answer":
        # answer로 들어온 순간에만 "just_flipped" 애니메이션 부여
        if st.session_state.last_animated_idx != idx:
            just_flipped = idx
            st.session_state.last_animated_idx = idx

    st.write("---")
    card_html = render_cards_html(
        problems=game["problems"],
        revealed=game["revealed"],
        results=game["results"],
        current_idx=idx,
        just_flipped_idx=just_flipped,
    )
    components.html(card_html, height=560, scrolling=False)
    st.write("---")

    # -----------------------------
    # Answer Input (음성)
    # - preflip 동안은 입력을 받지 않음(연출 깨짐 방지)
    # -----------------------------
    if game["phase"] == "answer":
        st.write("### 🎙️ 정답 말하기")
        st.caption(
            "마이크 버튼 누르고 정답을 말해줘. (인식 텍스트에 숫자가 포함되면 판정)"
        )

        rec = mic_recorder(
            start_prompt="🎤 녹음 시작",
            stop_prompt="⏹️ 녹음 종료",
            just_once=True,
            key=f"mic_{idx}",
        )

        heard_text = ""
        if isinstance(rec, dict):
            heard_text = (rec.get("text") or "").strip()

        if heard_text:
            game["last_heard"] = heard_text

        if game["last_heard"]:
            st.write(f"인식된 텍스트: **{game['last_heard']}**")

        # 시간 초과면 오답
        if remain <= 0.0 and game["results"][idx] is None:
            game["results"][idx] = False

        # 정답 판정
        if game["results"][idx] is None and game["last_heard"]:
            guess = parse_int_from_text(game["last_heard"])
            if guess is not None:
                cur = game["problems"][idx]
                game["results"][idx] = guess == cur["ans"]

        # -----------------------------
        # Next card
        # -----------------------------
        if game["results"][idx] is not None:
            # 다음 카드 준비
            game["idx"] += 1
            game["card_start_ts"] = None
            game["last_heard"] = ""

            if game["idx"] >= 16:
                game["status"] = "finished"
            else:
                game["phase"] = "preflip"
                game["phase_start_ts"] = time.time()

            st.rerun()

else:
    # finished
    correct = sum(1 for x in game["results"] if x is True)
    score = round(correct / 16 * 100)

    st.success(f"끝! ✅ 정답 {correct}/16  →  **점수 {score}점**")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("다시 하기 (Level 유지)", use_container_width=True):
            start_new_game()
            st.rerun()
    with c2:
        if st.button("Level 올리고 다시 하기", use_container_width=True):
            st.session_state.level += 1
            start_new_game()
            st.rerun()
    with c3:
        if st.button("Level 초기화 (1)", use_container_width=True):
            st.session_state.level = 1
            start_new_game()
            st.rerun()

    st.write("### 결과 상세")
    for i, p in enumerate(game["problems"]):
        mark = "✅" if game["results"][i] else "❌"
        st.write(f"{i+1:02d}. {mark}  {p['a']}×{p['b']} = {p['ans']}")
