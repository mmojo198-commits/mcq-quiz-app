import streamlit as st
import pandas as pd
import time
import re
from pathlib import Path

# ---------------------------
# Config
# ---------------------------
st.set_page_config(page_title="MCQ Quiz", page_icon="🎯", layout="wide")

# ---------------------------
# Helpers
# ---------------------------
def normalize_text(s):
    """
    Normalize text for comparison:
    - convert to string
    - lowercase
    - normalize whitespace
    - strip trailing punctuation commonly differing (.,;:)
    - strip enclosing quotes
    """
    if pd.isna(s):
        return ""
    text = str(s).strip().lower()
    # replace multiple whitespace/newlines/tabs
    text = " ".join(text.split())
    # remove enclosing quotes if any
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
    # remove trailing punctuation that commonly differs between sources
    text = text.rstrip(".,;:") 
    return text

def extract_letter(s):
    """
    Try to extract a single answer letter (A-D) from string s.
    Handles:
      - 'A', 'A.', 'A)', 'A -', 'Option A', 'Option: A', 'OPTION A: ...'
    Returns 'A'|'B'|'C'|'D' or None
    """
    if s is None:
        return None
    s_str = str(s).strip().upper()
    # Simple cases where the cell only contains the letter
    if s_str in {"A", "B", "C", "D"}:
        return s_str
    # Leading letter patterns like "A.", "A)", "A -", "A :"
    m = re.match(r"^([A-D])[\.\:\)\-\s]", s_str)
    if m:
        return m.group(1)
    # Patterns like "OPTION A" or "OPTION: A"
    m2 = re.search(r"OPTION[\s\:\-]*([A-D])", s_str)
    if m2:
        return m2.group(1)
    # Patterns like "A: Some text" (covered by regex above, but keep fallback)
    m3 = re.match(r"^([A-D])\s*\:", s_str)
    if m3:
        return m3.group(1)
    return None

def find_correct_letter(row, debug=False):
    """
    Given a dataframe row with columns Option A..D and Correct Answer,
    return the letter ('A'..'D') that matches the correct answer, or None.
    """
    corr_raw = row.get("Correct Answer")
    corr_let = extract_letter(corr_raw)

    if debug:
        st.write("🔍 find_correct_letter debug")
        st.write(f"  raw correct value: `{corr_raw}`")
        st.write(f"  extracted letter: {corr_let}")

    if corr_let:
        return corr_let

    # No letter: try exact normalized text match against options
    correct_text_norm = normalize_text(corr_raw)
    if debug:
        st.write(f"  correct_text_norm: `{correct_text_norm}`")

    for letter in ["A", "B", "C", "D"]:
        opt = row.get(f"Option {letter}")
        if pd.notna(opt):
            opt_norm = normalize_text(opt)
            if debug:
                st.write(f"  Option {letter} normalized: `{opt_norm}`")
            if opt_norm == correct_text_norm:
                if debug:
                    st.write(f"  ✅ matched Option {letter}")
                return letter

    if debug:
        st.write("  ❌ no matching option found")
    return None

def is_correct(selected, correct_raw):
    """
    Determine if a selected UI answer (e.g. "B: some text") is correct given correct_raw (which may be a letter or full text).
    """
    if not selected:
        return False

    # Extract selected letter & text
    selected_letter = selected.split(":", 1)[0].strip().upper()
    selected_text = ""
    if ":" in selected:
        selected_text = selected.split(":", 1)[1].strip()

    # If correct_raw has an explicit letter, compare letters
    correct_letter = extract_letter(correct_raw)
    if correct_letter:
        return selected_letter == correct_letter

    # Otherwise compare normalized text (both sides)
    # Normalize both selected_text and correct_raw
    return normalize_text(selected_text) == normalize_text(correct_raw)

def parse_rationale(rationale_text, selected_letter, selected_option_text=None):
    """
    Extract rationale for a specific selected letter (A..D) from the Rationale (Wrong Answers) column.
    The rationale may be in formats:
      - "Option A: explanation | Option B: explanation"
      - "A: explanation | B: explanation"
      - "Full option text: explanation | Other option text: explanation"
    Returns explanation string or None.
    """
    if pd.isna(rationale_text):
        return None
    parts = [p.strip() for p in str(rationale_text).split("|") if p.strip()]
    # First try letter prefixes
    for part in parts:
        up = part.upper()
        if up.startswith(f"OPTION {selected_letter}:") or up.startswith(f"{selected_letter}:"):
            if ":" in part:
                return part.split(":", 1)[1].strip()
    # Then try prefix being option text
    if selected_option_text:
        for part in parts:
            if part.startswith(selected_option_text):
                if ":" in part:
                    return part.split(":", 1)[1].strip()
    # Last resort: return first part as fallback (not ideal)
    return None

def read_quiz_df(df):
    expected = ["Question", "Option A", "Option B", "Option C", "Option D", "Correct Answer", "Hint"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}. Columns found: {list(df.columns)}")
        return pd.DataFrame()
    cols_to_keep = expected.copy()
    if "Rationale (Wrong Answers)" in df.columns:
        cols_to_keep.append("Rationale (Wrong Answers)")
    return df[cols_to_keep].copy()

# ---------------------------
# Session State initialization
# ---------------------------
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False
if "questions" not in st.session_state:
    st.session_state.questions = None
if "index" not in st.session_state:
    st.session_state.index = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "time_spent" not in st.session_state:
    st.session_state.time_spent = {}
if "submitted_q" not in st.session_state:
    st.session_state.submitted_q = {}
if "timer_per_question" not in st.session_state:
    st.session_state.timer_per_question = None
if "question_start_time" not in st.session_state:
    st.session_state.question_start_time = None
if "shuffle" not in st.session_state:
    st.session_state.shuffle = True
if "timer_choice" not in st.session_state:
    st.session_state.timer_choice = 30
if "finished" not in st.session_state:
    st.session_state.finished = False
if "score" not in st.session_state:
    st.session_state.score = 0

def update_score():
    sc = 0
    for idx in range(len(st.session_state.questions)):
        ans = st.session_state.answers.get(idx)
        if ans and is_correct(ans, st.session_state.questions.iloc[idx]["Correct Answer"]):
            sc += 1
    st.session_state.score = sc

def save_time_state():
    """Save elapsed time for current question index."""
    i = st.session_state.index
    if st.session_state.question_start_time is not None:
        elapsed = time.time() - st.session_state.question_start_time
        current_total = st.session_state.time_spent.get(i, 0)
        if st.session_state.timer_per_question is None:
            st.session_state.time_spent[i] = current_total + elapsed
        else:
            st.session_state.time_spent[i] = min(st.session_state.timer_per_question, current_total + elapsed)

# Navigation helper
def handle_navigation(new_index):
    i = st.session_state.index
    save_time_state()
    current_selected = st.session_state.get(f"radio_{i}")
    if not st.session_state.submitted_q.get(i, False):
        st.session_state.answers[i] = current_selected
    st.session_state.index = new_index
    st.session_state.question_start_time = time.time()
    st.experimental_rerun()

# ---------------------------
# State 1: File Upload
# ---------------------------
if st.session_state.questions is None:
    st.title("📘 Interactive MCQ Quiz")
    with st.container():
        st.write("### 📤 Upload Quiz Data")
        st.write("Upload an Excel file (.xlsx) with columns: `Question`, `Option A`, `Option B`, `Option C`, `Option D`, `Correct Answer`, `Hint`, `Rationale (Wrong Answers)`")
        uploaded_file = st.file_uploader("Choose file", type=["xlsx"], label_visibility="collapsed")

        df = None
        if uploaded_file is None:
            # try common demo folders: /mnt/data (server) then current directory
            fallback_paths = []
            p1 = Path("/mnt/data")
            if p1.exists():
                fallback_paths.extend(sorted(p1.glob("*.xlsx")))
            p2 = Path(".")
            fallback_paths.extend(sorted(p2.glob("*.xlsx")))
            if fallback_paths:
                fallback_path = fallback_paths[0].as_posix()
                st.info(f"Auto-detected file: `{fallback_path}`")
                if st.button("Load Auto-detected File"):
                    try:
                        df_raw = pd.read_excel(fallback_path)
                        df = read_quiz_df(df_raw)
                    except Exception as e:
                        st.error(f"Error loading file: {e}")
        else:
            try:
                df_raw = pd.read_excel(uploaded_file)
                df = read_quiz_df(df_raw)
            except Exception as e:
                st.error(f"Error reading uploaded file: {e}")
                df = None

        if df is not None and not df.empty:
            st.session_state.questions = df.reset_index(drop=True)
            st.session_state.quiz_started = False
            st.success(f"✅ Loaded {len(st.session_state.questions)} questions!")
            st.experimental_rerun()
    st.stop()

# ---------------------------
# State 2: Setup
# ---------------------------
if st.session_state.questions is not None and not st.session_state.quiz_started:
    st.title("⚙️ Quiz Setup")
    with st.container():
        st.write(f"**Total Questions:** {len(st.session_state.questions)}")
        TIMER_OPTIONS = ["No timer", 10, 15, 20, 30, 45, 60]
        try:
            default_idx = TIMER_OPTIONS.index(st.session_state.timer_choice)
        except ValueError:
            default_idx = TIMER_OPTIONS.index(30)

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.shuffle = st.checkbox("Shuffle Questions", value=st.session_state.shuffle)
        with col2:
            st.session_state.timer_choice = st.selectbox("Time per question (seconds)", TIMER_OPTIONS, index=default_idx)

        st.divider()
        if st.button("🚀 Start Quiz", use_container_width=True, type="primary"):
            questions_df = st.session_state.questions
            if st.session_state.shuffle:
                st.session_state.questions = questions_df.sample(frac=1, random_state=int(time.time())).reset_index(drop=True)
            else:
                st.session_state.questions = questions_df.reset_index(drop=True)
            st.session_state.index = 0
            st.session_state.answers = {}
            st.session_state.time_spent = {}
            st.session_state.submitted_q = {}
            # timer config
            if st.session_state.timer_choice == "No timer":
                st.session_state.timer_per_question = None
            else:
                st.session_state.timer_per_question = int(st.session_state.timer_choice)
            st.session_state.question_start_time = time.time()
            st.session_state.quiz_started = True
            st.session_state.finished = False
            st.session_state.score = 0
            st.experimental_rerun()

        if st.button("🔄 Reset File"):
            st.session_state.questions = None
            st.experimental_rerun()
    st.stop()

# ---------------------------
# State 3: Results
# ---------------------------
if st.session_state.finished:
    st.title("🏆 Quiz Results")
    total_q = len(st.session_state.questions)
    percentage = (st.session_state.score / total_q) * 100 if total_q else 0
    col_res1, col_res2 = st.columns([1, 3])
    with col_res1:
        st.metric("Final Score", f"{st.session_state.score} / {total_q}")
    with col_res2:
        st.progress(st.session_state.score / total_q if total_q else 0)
        st.caption(f"Accuracy: {percentage:.1f}%")

    st.divider()
    # Summary Table
    results_data = []
    for idx in range(total_q):
        q = st.session_state.questions.iloc[idx]
        user_ans = st.session_state.answers.get(idx)
        correct_raw = q["Correct Answer"]
        is_corr = False
        if user_ans:
            is_corr = is_correct(user_ans, correct_raw)
        results_data.append({
            "No.": idx + 1,
            "Question": q["Question"],
            "Your Answer": user_ans if user_ans else "Skipped",
            "Correct Answer": correct_raw,
            "Result": "✅" if is_corr else "❌"
        })
    st.dataframe(pd.DataFrame(results_data), use_container_width=True, hide_index=True)

    col_act1, col_act2 = st.columns(2)
    with col_act1:
        if st.button("🔁 Retry Same Questions", use_container_width=True):
            st.session_state.quiz_started = False
            st.session_state.finished = False
            st.experimental_rerun()
    with col_act2:
        if st.button("📂 Upload New File", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.experimental_rerun()
    st.stop()

# ---------------------------
# State 4: Active Quiz UI
# ---------------------------
questions = st.session_state.questions
i = st.session_state.index
total_q = len(questions)
row = questions.iloc[i]
is_submitted = st.session_state.submitted_q.get(i, False)
time_allowed = st.session_state.timer_per_question

# Sidebar: Timer & Map
# compute remaining in sidebar and expose to main for auto-timeout logic
remaining = None
with st.sidebar:
    st.markdown("### ⏳ Timer")
    if st.session_state.question_start_time is None:
        st.session_state.question_start_time = time.time()
    if time_allowed is None:
        st.markdown("<h3 style='text-align: center; color: green; margin: 0;'>Unlimited</h3>", unsafe_allow_html=True)
        st.progress(1.0)
        remaining = None
    else:
        if is_submitted:
            time_spent = st.session_state.time_spent.get(i, 0)
        else:
            elapsed = time.time() - st.session_state.question_start_time
            previous_time = st.session_state.time_spent.get(i, 0)
            time_spent = min(time_allowed, previous_time + elapsed)
        remaining = max(0, time_allowed - time_spent)
        timer_color = "red" if remaining < 5 else "blue"
        st.markdown(f"<h1 style='text-align: center; color: {timer_color}; margin: 0;'>{int(remaining)}s</h1>", unsafe_allow_html=True)
        st.progress(min(1.0, max(0.0, remaining / time_allowed)))

    st.divider()
    st.markdown("### 🗺️ Question Map")
    cols_per_row = 4
    for r in range(0, total_q, cols_per_row):
        cols = st.columns(cols_per_row)
        for c_idx, q_idx in enumerate(range(r, min(r + cols_per_row, total_q))):
            with cols[c_idx]:
                btn_type = "secondary"
                lbl = str(q_idx + 1)
                if q_idx == i:
                    btn_type = "primary"
                    lbl = f"▶ {q_idx+1}"
                elif st.session_state.submitted_q.get(q_idx):
                    hist_ans = st.session_state.answers.get(q_idx)
                    if hist_ans and is_correct(hist_ans, st.session_state.questions.iloc[q_idx]["Correct Answer"]):
                        lbl = f"✓ {q_idx+1}"
                    else:
                        lbl = f"✗ {q_idx+1}"
                if st.button(lbl, key=f"nav_{q_idx}", use_container_width=True, type=btn_type):
                    handle_navigation(q_idx)

    st.divider()
    if st.button("🏁 Finish Quiz", use_container_width=True, type="primary" if i == total_q - 1 else "secondary"):
        save_time_state()
        curr = st.session_state.get(f"radio_{i}")
        if not is_submitted:
            st.session_state.answers[i] = curr
            st.session_state.submitted_q[i] = True
        update_score()
        st.session_state.finished = True
        st.experimental_rerun()

# Main content
st.markdown(f"#### Question {i + 1} of {total_q}")
st.progress(i / total_q if total_q else 0)

with st.container():
    st.markdown(f"### {row['Question']}")
    options = [
        ("A", row["Option A"]), ("B", row["Option B"]),
        ("C", row["Option C"]), ("D", row["Option D"]),
    ]
    display_options = [f"{letter}: {text}" for letter, text in options if pd.notna(text)]
    saved_ans = st.session_state.answers.get(i, None)
    radio_idx = None
    if saved_ans in display_options:
        radio_idx = display_options.index(saved_ans)
    selected = st.radio("Select your answer:", display_options, index=radio_idx if radio_idx is not None else 0, key=f"radio_{i}", disabled=is_submitted)

    # Feedback area when submitted
    if is_submitted:
        st.divider()
        if saved_ans:
            current_row = st.session_state.questions.iloc[i]
            if is_correct(saved_ans, current_row["Correct Answer"]):
                st.success("✅ Correct!")
            else:
                corr_let = find_correct_letter(current_row, debug=False)
                if corr_let:
                    corr_txt = current_row.get(f"Option {corr_let}", str(current_row["Correct Answer"]))
                    st.error(f"❌ Incorrect. Correct Answer: **{corr_let}: {corr_txt}**")
                else:
                    st.error(f"❌ Incorrect. Correct Answer: **{current_row['Correct Answer']}**")

                # debug expander (optional)
                with st.expander("🔍 Debug Info (for testing)"):
                    st.write(f"**Your selection:** {saved_ans}")
                    st.write(f"**Your Selected Letter:** {saved_ans.split(':', 1)[0].strip().upper()}")
                    st.write(f"**Correct Answer from Excel:** `{current_row['Correct Answer']}`")
                    st.write(f"**Correct Answer (normalized):** `{normalize_text(current_row['Correct Answer'])}`")
                    st.write("---")
                    st.write("**Calling find_correct_letter() WITH DEBUG:**")
                    test_corr_let = find_correct_letter(current_row, debug=True)
                    st.write(f"**Returned value: {test_corr_let}**")
                    st.write("---")
                    test_correct_norm = normalize_text(current_row['Correct Answer'])
                    st.write(f"Correct answer normalized: `{test_correct_norm}`")
                    for letter in ["A", "B", "C", "D"]:
                        opt = current_row.get(f"Option {letter}")
                        if pd.notna(opt):
                            opt_norm = normalize_text(opt)
                            is_exact_match = (opt_norm == test_correct_norm)
                            st.write(f"**Option {letter}:** `{opt}`")
                            st.write(f"  - Normalized: `{opt_norm}`  Exact match: {is_exact_match}")

                # show rationale
                selected_letter = saved_ans.split(":", 1)[0].strip().upper()
                selected_option_text = current_row.get(f"Option {selected_letter}")
                if "Rationale (Wrong Answers)" in current_row and pd.notna(current_row["Rationale (Wrong Answers)"]):
                    found_rationale = parse_rationale(current_row["Rationale (Wrong Answers)"], selected_letter, selected_option_text)
                    if found_rationale:
                        st.info(f"**Why this is wrong:** {found_rationale}")
        else:
            st.warning("⌛ Answer locked.")
            current_row = st.session_state.questions.iloc[i]
            corr_let_timeout = find_correct_letter(current_row)
            if corr_let_timeout:
                corr_txt = current_row.get(f"Option {corr_let_timeout}", str(current_row["Correct Answer"]))
                st.markdown(f"**Correct Answer:** {corr_let_timeout}: {corr_txt}")
            else:
                st.markdown(f"**Correct Answer:** {current_row['Correct Answer']}")
    else:
        if pd.notna(row.get("Hint")) and st.checkbox("Show Hint"):
            st.info(f"💡 Hint: {row['Hint']}")

# Footer navigation
col_prev, col_submit, col_next = st.columns([1, 2, 1])
with col_prev:
    if st.button("⬅️ Previous", disabled=(i == 0), use_container_width=True):
        handle_navigation(i - 1)
with col_submit:
    if not is_submitted:
        if st.button("🔒 Submit Answer", type="primary", use_container_width=True):
            save_time_state()
            st.session_state.answers[i] = selected
            st.session_state.submitted_q[i] = True
            update_score()
            st.experimental_rerun()
with col_next:
    if st.button("Next ➡️", disabled=(i == total_q - 1), use_container_width=True):
        handle_navigation(i + 1)

# Auto-action if timer exists
if time_allowed is not None:
    # If timer is active, check for timeout
    if remaining is not None and remaining <= 0 and not is_submitted:
        st.session_state.time_spent[i] = time_allowed
        st.session_state.submitted_q[i] = True
        current_selection = st.session_state.get(f"radio_{i}")
        st.session_state.answers[i] = current_selection
        update_score()
        st.warning("⏰ Time's Up!")
        # move to next question if available, else finish
        if i < total_q - 1:
            st.session_state.index = i + 1
            st.session_state.question_start_time = time.time()
            st.experimental_rerun()
        else:
            st.session_state.finished = True
            st.experimental_rerun()
    else:
        # Light heartbeat to refresh timer display (small sleep to avoid busy-loop)
        time.sleep(0.5)
        st.experimental_rerun()
