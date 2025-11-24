import streamlit as st
import pandas as pd
import io
import json
from pathlib import Path
import random

# --- Configuration and Styling ---

st.set_page_config(
    page_title="Jomin's Flashcard App",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for minimal top space
st.markdown("""
<style>
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 2rem !important;
    }
    header, #MainMenu, footer {
        visibility: hidden;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    h1 {
        color: white !important;
        font-size: 36px !important;
        font-weight: 700 !important;
        margin-top: 0px !important;
        margin-bottom: 0px !important;
        padding-top: 0px !important;
    }
    .stApp {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 50%, #1e293b 100%);
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .flashcard {
        background: linear-gradient(135deg, #2a344a 0%, #3e4a60 100%);
        border-radius: 24px;
        padding: 60px 40px;
        margin: 40px auto;
        max-width: 700px;
        min-height: 400px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        border: 1px solid #475569;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        transition: all 0.3s ease;
    }
    .flashcard-answer {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        border: 1px solid #059669;
    }
    .card-text {
        color: white;
        line-height: 1.6;
        font-weight: 400;
        margin: 0;
    }
    .card-label {
        color: #e2e8f0;
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-bottom: 20px;
        font-weight: 600;
    }
    .stButton > button {
        background: #4f46e5;
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-size: 16px;
        font-weight: 500;
        transition: all 0.3s ease;
        cursor: pointer;
    }
    .stButton > button:hover {
        background: #6366f1;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .stButton > button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    .nav-button > button {
        background: #334155 !important;
        color: white !important;
        border: none !important;
        border-radius: 50% !important;
        width: 56px !important;
        height: 56px !important;
        min-width: 56px !important;
        padding: 0 !important;
        font-size: 24px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .nav-button > button:hover {
        background: #475569 !important;
    }
    .nav-button:hover > button {
        background: #475569 !important;
    }
    .stFileUploader {
        background: rgba(255,255,255,0.05);
        border-radius: 12px;
        padding: 20px;
        border: 2px dashed #475569;
    }
    [data-testid="stMetricValue"] {
        color: #a5b4fc !important;
        font-size: 24px !important;
    }
    [data-testid="stMetricLabel"] {
        color: #cbd5e1 !important;
    }
    div[data-testid="column"] {
        gap: 0 !important;
    }
    
    /* Compact slider styling for font size control */
    .font-size-slider {
        font-size: 12px !important;
        color: #cbd5e1 !important;
    }
    .stSlider {
        margin: 0 !important;
        padding: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Session State Initialization ---

if 'flashcards' not in st.session_state:
    st.session_state.flashcards = []
if 'original_flashcards' not in st.session_state: 
    st.session_state.original_flashcards = []
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'show_answer' not in st.session_state:
    st.session_state.show_answer = False
if 'file_loaded' not in st.session_state:
    st.session_state.file_loaded = False
if 'app_title' not in st.session_state:
    st.session_state.app_title = "Flashcard Review"

# --- Data Loading Function (FIXED) ---

def load_flashcards(uploaded_file):
    file_extension = Path(uploaded_file.name).suffix.lower()
    df = None
    flashcards = []

    try:
        if file_extension in ['.xlsx', '.xls']:
            # Added header=None to read the first row as data
            df = pd.read_excel(uploaded_file, header=None)
        elif file_extension == '.csv':
            # Added header=None to read the first row as data
            df = pd.read_csv(uploaded_file, header=None)
        elif file_extension == '.json':
            uploaded_file.seek(0)
            data = json.load(uploaded_file)
            if isinstance(data, list) and all(isinstance(item, dict) and 'question' in item and 'answer' in item for item in data):
                flashcards = [{'question': str(item['question']).strip(), 'answer': str(item['answer']).strip()} for item in data]
                return flashcards
            else:
                st.error("JSON file must contain a list of objects, each with 'question' and 'answer' keys.")
                return []
        
        if df is not None:
            # Ensure we have at least 2 columns
            if df.shape[1] < 2:
                st.error("File must have at least two columns: Question and Answer.")
                return []
            
            # Since header=None, columns are integers 0 and 1
            questions_col = df.columns[0]
            answers_col = df.columns[1]
            
            for _, row in df.iterrows():
                question = str(row[questions_col]).strip()
                answer = str(row[answers_col]).strip()
                
                # Basic validation to skip empty rows or 'nan' strings
                if question and answer and question.lower() != 'nan' and answer.lower() != 'nan':
                    flashcards.append({'question': question, 'answer': answer})
                    
        return flashcards
    except Exception as e:
        st.error(f"Error loading {file_extension.upper()} file: {e}")
        return []

# --- Navigation and Control Functions ---

def next_card():
    if st.session_state.current_index < len(st.session_state.flashcards) - 1:
        st.session_state.current_index += 1
        st.session_state.show_answer = False

def previous_card():
    if st.session_state.current_index > 0:
        st.session_state.current_index -= 1
        st.session_state.show_answer = False

def toggle_answer():
    st.session_state.show_answer = not st.session_state.show_answer

def restart():
    st.session_state.current_index = 0
    st.session_state.show_answer = False

def shuffle_cards():
    if st.session_state.flashcards:
        random.shuffle(st.session_state.flashcards)
        st.session_state.current_index = 0
        st.session_state.show_answer = False

def reset_order():
    if st.session_state.original_flashcards:
        st.session_state.flashcards = st.session_state.original_flashcards.copy()
        st.session_state.current_index = 0
        st.session_state.show_answer = False

# --- Main App Layout ---

if not st.session_state.file_loaded or not st.session_state.flashcards:
    st.markdown("<h1 style='text-align: center;'>🧠 Jomin's Flashcard App</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94a3b8; font-size: 18px;'>Upload your study deck (Excel, CSV, or JSON) to begin your review.</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        subject_input = st.text_input(
            "Enter Subject or Deck Name (Optional)",
            value="Flashcard Review",
            max_chars=50,
            help="This name will appear as the main title of your session."
        )
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=['xlsx', 'xls', 'csv', 'json'],
            help="Upload a file with Questions in the first column/field and Answers in the second."
        )
        if uploaded_file:
            st.session_state.app_title = subject_input if subject_input else "Flashcard Review"
            with st.spinner(f'Loading flashcards for {st.session_state.app_title}...'):
                flashcards = load_flashcards(uploaded_file)
                if flashcards:
                    st.session_state.flashcards = flashcards
                    st.session_state.original_flashcards = flashcards.copy() 
                    st.session_state.file_loaded = True
                    st.session_state.current_index = 0
                    st.session_state.show_answer = False
                    st.success(f"✅ Loaded {len(flashcards)} flashcards for: {st.session_state.app_title}!")
                    st.rerun()
                else:
                    st.error("❌ No valid flashcards found in the file! Please check the file structure.")

else:
    current_card = st.session_state.flashcards[st.session_state.current_index]
    total_cards = len(st.session_state.flashcards)
    current_num = st.session_state.current_index + 1

    # Header with dynamic title
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"<h1>🧠 {st.session_state.app_title}</h1>", unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='nav-button'>", unsafe_allow_html=True)
        if st.button("📤 Upload New", use_container_width=True, key="new_upload"):
            st.session_state.file_loaded = False
            st.session_state.flashcards = []
            st.session_state.original_flashcards = []
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Main card area with navigation
    col1, col2, col3 = st.columns([0.5, 6, 0.5])

    with col1:
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("<div class='nav-button'>", unsafe_allow_html=True)
        st.button("←", on_click=previous_card, disabled=st.session_state.current_index == 0, key="prev")
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        card_class = "flashcard-answer" if st.session_state.show_answer else "flashcard"
        label = "ANSWER" if st.session_state.show_answer else "QUESTION"
        text = current_card['answer'] if st.session_state.show_answer else current_card['question']
        
        # Get font size from session state or set default
        if 'font_size' not in st.session_state:
            st.session_state.font_size = 28
        
        st.markdown(f"""
        <div class="flashcard {card_class}">
            <div class="card-label">{label}</div>
            <p class="card-text" style="font-size: {st.session_state.font_size}px;">{text}</p>
        </div>
        """, unsafe_allow_html=True)
        col_a, col_b, col_c = st.columns([2, 1, 2])
        with col_b:
            button_text = "🔄 Flip Card" if not st.session_state.show_answer else "👁️ Hide Answer"
            if st.button(button_text, 
                         on_click=toggle_answer, 
                         use_container_width=True,
                         key="flip-btn"):
                pass

    with col3:
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("<div class='nav-button'>", unsafe_allow_html=True)
        st.button("→", on_click=next_card, disabled=st.session_state.current_index == total_cards - 1, key="next")
        st.markdown("</div>", unsafe_allow_html=True)

    # Footer with progress and controls
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1_footer, col2_footer, col3_footer = st.columns([1.2, 1.8, 1])
    
    with col1_footer:
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🔢 Order", on_click=reset_order, use_container_width=True, help="Reset to original file order"):
                pass
        with c2:
            if st.button("🔀 Shuffle", on_click=shuffle_cards, use_container_width=True, help="Randomize cards"):
                pass
        with c3:
            if st.button("⏮️ Reset", on_click=restart, use_container_width=True, help="Go back to first card"):
                pass
                
    with col2_footer:
        progress = current_num / total_cards
        st.progress(progress)
        st.markdown(f"<p style='text-align: center; color: white; font-size: 18px; font-weight: 600;'>Card {current_num} of {total_cards}</p>", 
                    unsafe_allow_html=True)
    with col3_footer:
        col_metric, col_slider = st.columns([1, 1])
        with col_metric:
            st.metric("Completion", f"{int(progress * 100)}%")
        with col_slider:
            st.markdown("<div class='font-size-slider' style='padding-top: 8px;'>", unsafe_allow_html=True)
            st.session_state.font_size = st.slider(
                "Font Size",
                min_value=16,
                max_value=48,
                value=st.session_state.font_size,
                step=2,
                label_visibility="collapsed"
            )
            st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("""
        <script>
            document.addEventListener('keydown', function(e) {
                const prevButton = document.querySelector('[data-testid="stButton"] button[key="prev"]');
                const nextButton = document.querySelector('[data-testid="stButton"] button[key="next"]');
                const flipButton = document.querySelector('[data-testid="stButton"] button[key="flip-btn"]');
                if (!prevButton || !nextButton || !flipButton) return;
                if (e.key === 'ArrowLeft' || e.key === 'a') {
                    e.preventDefault();
                    if (!prevButton.disabled) prevButton.click();
                } else if (e.key === 'ArrowRight' || e.key === 'd') {
                    e.preventDefault();
                    if (!nextButton.disabled) nextButton.click();
                } else if (e.key === ' ' || e.key === 'Enter') {
                    e.preventDefault();
                    flipButton.click();
                }
            });
        </script>
        """, unsafe_allow_html=True)
