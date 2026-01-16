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
    return max(3, 6 - level)


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
.gugu-wrap { width: 100%; }

/* Grid is disabled: use stack UI on all devices */
.gugu-grid { display: none; }

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

/* Stack UI (use on all screens) */
.gugu-stack {
  display: block;
  position: relative;
  padding: 12px 8px 6px 8px;
  height: 420px;
}
.gugu-stack-meta {
  display: block;
  padding: 0 10px 10px 10px;
  font-size: 14px;
  font-weight: 900;
  color: #334155;
}
.gugu-stack-card {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: clamp(320px, 70vw, 560px);
  height: 260px;
}
.gugu-stack-card.back {
  filter: saturate(.85);
}
</style>
"""

    def card_inner_html(i: int, p: dict, is_rev: bool, res, show_timer: bool):
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
                main = f"{a} × {b} = {p['ans']}"
                hint = ""

        timer_html = ""
        if show_timer:
            sec = max(0, int(remain_sec))
            cls = "danger" if sec <= 3 else "warn" if sec <= 6 else "safe"
            timer_html = f'<div class="gugu-timer {cls}">⏱ {sec}s</div>'

        badge = "✅" if res is True else "❌" if res is False else ""

        classes = ["gugu-card"]
        if is_rev:
            classes.append("is-flipped")
        if just_flipped_idx == i:
            classes.append("just-flipped")

        return f"""
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

    parts = [css, '<div class="gugu-wrap">']

    # -------- Grid UI (desktop/tablet) --------
    parts.append('<div class="gugu-grid">')

    for i, p in enumerate(problems):
        is_rev = revealed[i]
        res = results[i]
        show_timer = i == current_idx and is_rev and res is None
        parts.append(card_inner_html(i, p, is_rev, res, show_timer))

    parts.append("</div>")  # grid

    # -------- Stack UI (mobile) --------
    total = len(problems)
    done = sum(1 for r in results if r is not None)
    remain_cards = max(0, total - done)
    correct_cnt = sum(1 for r in results if r is True)
    wrong_cnt = sum(1 for r in results if r is False)
    parts.append(
        f'<div class="gugu-stack-meta">진행: {done} / {total} · 남은 카드: {remain_cards} · ✅ {correct_cnt} · ❌ {wrong_cnt}</div>'
    )

    parts.append('<div class="gugu-stack">')

    # 1) A few back cards behind (visual only)
    back_n = min(3, max(0, total - current_idx - 1))
    for k in range(back_n, 0, -1):
        top = 18 + k * 10
        scale = 1 - k * 0.04
        parts.append(
            f"""
<div class=\"gugu-stack-card back\" style=\"top:{top}px; transform: translateX(-50%) scale({scale}); opacity:{0.55 + (3-k)*0.1};\">
  <div class=\"gugu-card\">
    <div class=\"gugu-card-inner\">
      <div class=\"gugu-face gugu-back\">🂠</div>
      <div class=\"gugu-face gugu-front\"></div>
    </div>
  </div>
</div>
"""
        )

    # 2) Current card (real)
    if 0 <= current_idx < total:
        p = problems[current_idx]
        is_rev = revealed[current_idx]
        res = results[current_idx]
        show_timer = is_rev and res is None
        parts.append(
            f"""
<div class=\"gugu-stack-card\" style=\"top: 12px;\">
  {card_inner_html(current_idx, p, is_rev, res, show_timer)}
</div>
"""
        )

    parts.append("</div>")  # stack

    parts.append("</div>")  # wrap
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
        "mode": "normal",  # normal / retry_wrong
        "map_idx": list(range(16)),  # displayed idx -> original idx
        "orig": None,  # original game snapshot when retrying wrongs
    }
    st.session_state.show_score_popup = False


def start_retry_wrong():
    """Start a new round using only the wrong problems from the last normal game.
    It keeps the original game's card/result state in game['orig'] and updates it as you retry.
    """
    g = st.session_state.game
    if not g or g.get("mode") != "normal":
        return

    wrong_display_idxs = [i for i, r in enumerate(g["results"]) if r is False]
    if not wrong_display_idxs:
        return

    # snapshot original (shallow is enough: inner dicts are immutable here)
    orig = {k: g[k] for k in g.keys()}

    problems = [g["problems"][i] for i in wrong_display_idxs]
    n = len(problems)

    st.session_state.game = {
        "problems": problems,
        "idx": 0,
        "results": [None] * n,
        "revealed": [False] * n,
        "flipped_once": [False] * n,
        "phase": "preflip",
        "phase_start_ts": time.time(),
        "card_start_ts": None,
        "last_heard": "",
        "status": "playing",
        "mode": "retry_wrong",
        "map_idx": wrong_display_idxs,  # displayed idx -> original idx (in orig)
        "orig": orig,
    }
    st.session_state.show_score_popup = False


def restart_retry_wrong():
    """Restart retry_wrong round (when already in retry mode)."""
    g = st.session_state.game
    if not g or g.get("mode") != "retry_wrong":
        return
    orig = g.get("orig")
    if not orig:
        return
    # restore original then start retry again with current wrong list
    st.session_state.game = orig
    start_retry_wrong()


# -----------------------------
# Score Dialog (real modal)
# -----------------------------
@st.dialog("🎉 게임 종료!", width="large")
def show_score_dialog(score: int, correct: int, wrong: int, total: int, mode: str):
    st.markdown(
        f"""
        <div style="text-align:center; padding: 8px 0 6px 0;">
          <div style="font-size:18px; font-weight:900; color:#111827;">결과</div>
          <div style="font-size:56px; font-weight:950; color:#0f172a; margin-top:6px;">{score}점</div>
          <div style="font-size:16px; font-weight:900; color:#334155; margin-top:6px;">정답 {correct} · 오답 {wrong} (총 {total})</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("닫기", use_container_width=True):
            st.session_state.show_score_popup = False
            st.rerun()
    with c2:
        if st.button("다시 하기", use_container_width=True):
            if mode == "retry_wrong":
                restart_retry_wrong()
            else:
                start_new_game()
            st.rerun()
    with c3:
        if st.button("Level 올리고 다시", use_container_width=True):
            st.session_state.level += 1
            start_new_game()
            st.rerun()
    with c4:
        # Only show for normal mode and when there are wrong answers
        if mode == "normal" and wrong > 0:
            if st.button("틀린 문제 다시", use_container_width=True):
                start_retry_wrong()
                st.rerun()
        else:
            st.button("​", disabled=True, use_container_width=True)


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
    st.caption("카드는 한 장씩 쌓여서 진행돼 / Chrome 권장(마이크 권한 필요)")

if st.session_state.game is None:
    st.info("새 게임을 시작해줘!")
    st.stop()

game = st.session_state.game

# 정답/오답 카운트 (화면 구성은 유지하고, 헤더 아래 한 줄로만 표시)
correct_cnt_ui = sum(1 for r in game["results"] if r is True)
wrong_cnt_ui = sum(1 for r in game["results"] if r is False)
st.markdown(
    f"<div style='font-weight:900; font-size:16px; margin: 6px 0 2px 0;'>✅ 정답 {correct_cnt_ui} &nbsp;&nbsp;|&nbsp;&nbsp; ❌ 오답 {wrong_cnt_ui}</div>",
    unsafe_allow_html=True,
)

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

    # (retry helper) If you just finished retrying wrong problems, you can go back to the original full board
    if game.get("mode") == "retry_wrong" and game.get("orig") is not None:
        if st.button("⬅️ 원래 전체 카드 보기", use_container_width=True):
            st.session_state.game = game["orig"]
            st.session_state.show_score_popup = False
            st.rerun()

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
            # retry 모드라면 원본 게임 결과에도 반영
            if game.get("mode") == "retry_wrong" and game.get("orig") is not None:
                orig_i = game["map_idx"][idx]
                game["orig"]["results"][orig_i] = False

        # 정답 판정
        if game["results"][idx] is None and game["last_heard"]:
            guess = parse_int_from_text(game["last_heard"])
            if guess is not None:
                game["results"][idx] = guess == game["problems"][idx]["ans"]
                # retry 모드라면 원본 게임 결과에도 반영(맞추면 True로 갱신)
                if game.get("mode") == "retry_wrong" and game.get("orig") is not None:
                    orig_i = game["map_idx"][idx]
                    game["orig"]["results"][orig_i] = game["results"][idx]

        # 다음 카드로
        if game["results"][idx] is not None:
            game["idx"] += 1
            game["last_heard"] = ""
            game["phase"] = "preflip"
            game["phase_start_ts"] = time.time()
            game["card_start_ts"] = None

            if game["idx"] >= len(game["problems"]):
                game["status"] = "finished"
                st.session_state.show_score_popup = True

            st.rerun()

# -----------------------------
# Finished: keep cards as-is, show dialog
# -----------------------------
if game["status"] == "finished":
    # 카드 상태 그대로 유지하면서 그대로 렌더(타이머/힌트는 더 이상 표시되지 않음)
    # current_idx는 마지막 카드로 고정(혹은 0으로)
    keep_idx = min(game["idx"], len(game["problems"]) - 1)

    card_html = render_cards_html(
        game["problems"],
        game["revealed"],
        game["results"],
        current_idx=keep_idx,
        remain_sec=0,
        just_flipped_idx=None,
    )
    components.html(card_html, height=720, scrolling=True)

    # (retry helper) If you just finished retrying wrong problems, you can go back to the original full board
    if game.get("mode") == "retry_wrong" and game.get("orig") is not None:
        if st.button("⬅️ 원래 전체 카드 보기", use_container_width=True):
            st.session_state.game = game["orig"]
            st.session_state.show_score_popup = False
            st.rerun()

    # 점수 모달
    if st.session_state.show_score_popup:
        correct = sum(1 for r in game["results"] if r is True)
        wrong = sum(1 for r in game["results"] if r is False)
        total = len(game["results"])
        score = round((correct / total) * 100) if total else 0
        show_score_dialog(score, correct, wrong, total, game.get("mode", "normal"))
