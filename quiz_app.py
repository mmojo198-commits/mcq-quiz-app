import streamlit as st
import pandas as pd
import time
import re
from pathlib import Path

st.set_page_config(page_title="MCQ Quiz", page_icon="🎯", layout="wide")

# ---------------------------
# Helpers
# ---------------------------
def normalize_text(s):
    if pd.isna(s):
        return ""
    return " ".join(str(s).strip().lower().split())

def extract_letter(s):
    """Extract option letter (A, B, C, D) from text, avoiding false matches in words."""
    if s is None:
        return None
    s_str = str(s).strip().upper()
    
    # First check if it's just a single letter
    if s_str in {"A", "B", "C", "D"}:
        return s_str
    
    # Regex to find A., A), A- etc. avoiding false positives like "Apple"
    m = re.match(r"^([A-D])[\.\:\)\-]\s*", s_str)
    if m:
        return m.group(1)
    
    # Match "Option A" format with proper boundary
    m2 = re.search(r"^OPTION\s+([A-D])(?:\s|$|[\.\:\)])", s_str)
    if m2:
        return m2.group(1)
    
    return None

def find_correct_letter(row):
    """Find which option letter (A, B, C, D) matches the correct answer."""
    corr_let = extract_letter(row["Correct Answer"])
    if not corr_let:
        # No letter found, match by text
        correct_text_norm = normalize_text(row["Correct Answer"])
        for letter in ["A", "B", "C", "D"]:
            option_text = row.get(f"Option {letter}")
            if pd.notna(option_text) and normalize_text(option_text) == correct_text_norm:
                corr_let = letter
                break
    return corr_let

def is_correct(selected, correct_raw):
    """Check if the selected answer matches the correct answer."""
    if not selected:
        return False
    
    # Extract letter from selected option (format: "A: Option Text")
    selected_letter = selected.split(":", 1)[0].strip().upper() if ":" in selected else selected.strip().upper()
    
    # Get correct letter
    correct_letter = extract_letter(correct_raw)
    
    # If we couldn't extract a letter from correct_raw, try text matching
    if not correct_letter:
        selected_text = selected.split(":", 1)[1].strip() if ":" in selected else ""
        return normalize_text(selected_text) == normalize_text(correct_raw)
    
    # Primary check: compare by letter
    if selected_letter in ["A", "B", "C", "D"]:
        return selected_letter == correct_letter
    
    return False

def read_quiz_df(df):
    """Read and validate quiz DataFrame."""
    expected = ["Question", "Option A", "Option B", "Option C", "Option D", "Correct Answer", "Hint"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}. Columns found: {list(df.columns)}")
        return pd.DataFrame()
    
    cols_to_keep = expected.copy()
    for letter in ["A", "B", "C", "D"]:
        if f"Rationale {letter}" in df.columns:
            cols_to_keep.append(f"Rationale {letter}")
    
    return df[cols_to_keep].copy()

# ---------------------------
# Session State
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
    """Calculate and update the current score."""
    sc = 0
    for idx in range(len(st.session_state.questions)):
        ans = st.session_state.answers.get(idx)
        q_row = st.session_state.questions.iloc[idx]
        if ans and is_correct(ans, q_row['Correct Answer']):
            sc += 1
    st.session_state.score = sc

def save_time_state():
    """Updates the time spent for the current question."""
    i = st.session_state.index
    if st.session_state.question_start_time is not None:
        elapsed = time.time() - st.session_state.question_start_time
        current_total = st.session_state.time_spent.get(i, 0)
        
        if st.session_state.timer_per_question is None:
            st.session_state.time_spent[i] = current_total + elapsed
        else:
            st.session_state.time_spent[i] = min(st.session_state.timer_per_question, current_total + elapsed)

def handle_navigation(new_index):
    """Handles saving state before navigating to a different question."""
    i = st.session_state.index
    
    # Save time
    save_time_state()
    
    # Save answer if not already submitted (auto-save draft)
    current_selected = st.session_state.get(f"radio_{i}")
    if not st.session_state.submitted_q.get(i, False):
        st.session_state.answers[i] = current_selected
    
    # Update pointer
    st.session_state.index = new_index
    st.session_state.question_start_time = time.time()
    st.rerun()

# ---------------------------
# State 1: File Upload
# ---------------------------
if st.session_state.questions is None:
    st.title("📘 Interactive MCQ Quiz")
    
    with st.container(border=True):
        st.write("### 📤 Upload Quiz Data")
        st.write("Upload an Excel file (.xlsx) with columns: `Question`, `Option A`, `Option B`, `Option C`, `Option D`, `Correct Answer`, `Hint`, and `Rationale [A-D]`")
        
        uploaded_file = st.file_uploader("Choose file", type=["xlsx"], label_visibility="collapsed")
        
        df = None
        if uploaded_file is None:
            # Fallback logic for demo or local testing
            p = Path("cleaned_quiz_full_rationale.xlsx")
            if p.exists():
                fallback_path = p.as_posix()
                st.info(f"Auto-detected file: `{fallback_path}`")
                if st.button("Load Auto-detected File"):
                    try:
                        df_raw = pd.read_excel(fallback_path)
                        df = read_quiz_df(df_raw)
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            try:
                df_raw = pd.read_excel(uploaded_file)
                df = read_quiz_df(df_raw)
            except Exception as e:
                st.error(f"Error: {e}")
                df = None

        if df is not None and not df.empty:
            st.session_state.questions = df.reset_index(drop=True)
            st.session_state.quiz_started = False
            st.success(f"✅ Loaded {len(st.session_state.questions)} questions!")
            time.sleep(1)
            st.rerun()
    st.stop()

# ---------------------------
# State 2: Setup
# ---------------------------
if st.session_state.questions is not None and not st.session_state.quiz_started:
    st.title("⚙️ Quiz Setup")
    
    with st.container(border=True):
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
            st.session_state.timer_choice = st.selectbox(
                "Time per question (seconds)", 
                TIMER_OPTIONS, 
                index=default_idx
            )

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
            
            if st.session_state.timer_choice == "No timer":
                st.session_state.timer_per_question = None
            else:
                st.session_state.timer_per_question = int(st.session_state.timer_choice)
                
            st.session_state.question_start_time = time.time()
            st.session_state.quiz_started = True
            st.session_state.finished = False
            st.session_state.score = 0
            st.rerun()
            
        if st.button("🔄 Reset File"):
            st.session_state.questions = None
            st.rerun()
    st.stop()

# ---------------------------
# State 3: Results
# ---------------------------
