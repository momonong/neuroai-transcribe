import streamlit as st
import pandas as pd
import jiwer
import time
import difflib
import json

# --- 1. 系統配置與 CSS 優化 (深色模式版) ---
st.set_page_config(
    page_title="Clinical ASR Annotation System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定義 CSS：針對深色模式優化的配色
st.markdown("""
    <style>
    /* 強制設定深色背景與文字顏色，確保與 Streamlit Dark Theme 一致 */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    
    /* 差異比對容器 */
    .diff-container {
        display: flex;
        flex-direction: row;
        border-bottom: 1px solid #3d3d3d; /* 深灰分隔線 */
        padding: 12px 0;
        align-items: center; /* 垂直置中 */
    }
    
    /* 表頭專用樣式 */
    .diff-header {
        background-color: #262730; /* 稍亮的深灰底 */
        font-weight: bold;
        border-radius: 8px;
        padding: 10px 0;
        margin-bottom: 10px;
        border: 1px solid #4a4a4a;
    }
    
    /* 欄位設定 */
    .diff-col {
        flex: 1;
        padding: 0 15px;
        font-family: 'Courier New', monospace; /* 等寬字體方便對齊 */
        font-size: 15px;
        line-height: 1.6;
    }
    
    /* 刪除 (紅) - 深色模式高對比配色 */
    .diff-del {
        background-color: #4a181d; /* 深紅底 */
        color: #ff8a93;            /* 亮粉紅字 */
        text-decoration: line-through;
        padding: 2px 4px;
        border-radius: 4px;
    }
    
    /* 新增 (綠) - 深色模式高對比配色 */
    .diff-add {
        background-color: #123820; /* 深綠底 */
        color: #6bf797;            /* 亮綠字 */
        font-weight: bold;
        padding: 2px 4px;
        border-radius: 4px;
    }
    
    /* 調整頂部間距 */
    .block-container {
        padding-top: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. 核心邏輯函數 ---

def load_clinical_mock_data():
    """
    模擬 ASD 門診場域的對話資料。
    情境：醫師詢問家長關於兒童的社交互動與固著行為。
    """
    return pd.DataFrame([
        {
            "speaker": "SPEAKER_01", 
            "start": "00:00", 
            "end": "00:05", 
            "original": "小朋友進來的時候有沒有眼神的接處", 
            "corrected": "小朋友進來的時候有沒有眼神的接觸"
        },
        {
            "speaker": "SPEAKER_02", 
            "start": "00:05", 
            "end": "00:10", 
            "original": "比較少他通常都看著地板或者是看那個旋轉的電風扇", 
            "corrected": "比較少，他通常都看著地板，或者是看那個旋轉的電風扇"
        },
        {
            "speaker": "SPEAKER_01", 
            "start": "00:10", 
            "end": "00:15", 
            "original": "了解那對於呼喚名字有沒有反應例如叫他的小名", 
            "corrected": "了解，那對於呼喚名字有沒有反應？例如叫他的小名"
        },
        {
            "speaker": "SPEAKER_03", 
            "start": "00:15", 
            "end": "00:18", 
            "original": "火車火車我要看火車", 
            "corrected": "火車...火車...我要看火車"
        },
        {
            "speaker": "SPEAKER_02", 
            "start": "00:18", 
            "end": "00:24", 
            "original": "就像這樣他現在完全沉浸在自己的世界裡聽不到我們講話", 
            "corrected": "就像這樣，他現在完全沉浸在自己的世界裡，聽不到我們講話"
        },
         {
            "speaker": "SPEAKER_01", 
            "start": "00:24", 
            "end": "00:30", 
            "original": "這是一個明顯的固著行為我們需要做進一步的阿多斯測驗", 
            "corrected": "這是一個明顯的固著行為，我們需要做進一步的 ADOS 測驗"
        },
    ])

def highlight_differences(text1, text2):
    """
    比較兩個字串，並產生帶有 HTML 顏色標註的 Side-by-Side 視圖
    """
    d = difflib.SequenceMatcher(None, text1, text2)
    html_1 = []
    html_2 = []
    
    for tag, i1, i2, j1, j2 in d.get_opcodes():
        segment1 = text1[i1:i2]
        segment2 = text2[j1:j2]
        
        if tag == 'equal':
            html_1.append(segment1)
            html_2.append(segment2)
        elif tag == 'replace':
            html_1.append(f'<span class="diff-del">{segment1}</span>')
            html_2.append(f'<span class="diff-add">{segment2}</span>')
        elif tag == 'delete':
            html_1.append(f'<span class="diff-del">{segment1}</span>')
        elif tag == 'insert':
            html_2.append(f'<span class="diff-add">{segment2}</span>')
            
    return "".join(html_1), "".join(html_2)

def convert_to_training_format(df):
    """
    將 DataFrame 轉換為 JSONL 格式 (常見於 LLM Fine-tuning)
    """
    training_data = []
    for index, row in df.iterrows():
        entry = {
            "audio_segment": f"segment_{index}.wav", 
            "speaker": row['speaker'],
            "ground_truth": row['corrected']
        }
        training_data.append(entry)
    return json.dumps(training_data, ensure_ascii=False, indent=2)

# --- 3. 側邊欄：控制與設定 ---

with st.sidebar:
    st.title("System Control")
    st.markdown("---")
    
    st.subheader("1. Data Import")
    uploaded_file = st.file_uploader("Upload Audio (WAV/MP3/M4A)", type=["wav", "mp3", "m4a"])
    
    load_demo = st.button("Load Clinical Demo Data", type="primary")

    if 'df' not in st.session_state:
        st.session_state.df = None
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False

    if load_demo:
        with st.spinner("Initializing ASR Model & Transcribing..."):
            time.sleep(0.8) 
            st.session_state.df = load_clinical_mock_data()
            st.session_state.analysis_done = False

    # 講者定義 (Speaker Definition)
    if st.session_state.df is not None:
        st.markdown("---")
        st.subheader("2. Speaker Diarization Mapping")
        
        unique_speakers = sorted(st.session_state.df['speaker'].unique())
        speaker_map = {}
        
        # 預設對應 (模擬真實操作)
        default_roles = {
            "SPEAKER_01": "Clinician (醫師)",
            "SPEAKER_02": "Parent (家長)",
            "SPEAKER_03": "Child (兒童)"
        }
        
        for spk in unique_speakers:
            val = default_roles.get(spk, spk)
            new_name = st.text_input(f"Role for {spk}:", value=val)
            speaker_map[spk] = new_name

# --- 4. 主介面 ---

st.title("Clinical Audio Transcription & Annotation System")
st.markdown("#### Purpose: ASD Diagnostic Interview Transcription (Localhost Secure Environment)")

if st.session_state.df is not None:
    
    # 應用講者名稱對應
    display_df = st.session_state.df.copy()
    if 'speaker_map' in locals():
        display_df['speaker'] = display_df['speaker'].map(speaker_map)

    # --- 區塊 A: 編輯介面 ---
    st.markdown("### 1. Annotation Interface")
    st.info("Review the model output and correct any discrepancies in the 'Human Correction' column.")
    
    edited_df = st.data_editor(
        display_df,
        num_rows="fixed",
        width="stretch",
        hide_index=True,
        column_config={
            "speaker": st.column_config.TextColumn("Speaker", width="medium", disabled=True),
            "start": st.column_config.TextColumn("Start", width="small", disabled=True),
            "end": st.column_config.TextColumn("End", width="small", disabled=True),
            "original": st.column_config.TextColumn("Model Output (Pre-computation)", disabled=True),
            "corrected": st.column_config.TextColumn("Human Correction (Ground Truth)", required=True),
        }
    )

    st.markdown("---")

    # --- 區塊 B: 分析與匯出 ---
    col_action, col_space = st.columns([1, 5])
    with col_action:
        analyze_btn = st.button("Analyze & Visualize Differences", type="primary")
    
    if analyze_btn:
        st.session_state.analysis_done = True

    if st.session_state.analysis_done:
        st.markdown("### 2. Comparative Analysis & Training Data Generation")
        
        # 計算 Metrics
        originals = edited_df["original"].tolist()
        correcteds = edited_df["corrected"].tolist()
        
        cer = jiwer.cer("".join(correcteds), "".join(originals))
        wer = jiwer.wer("".join(correcteds), "".join(originals)) # 中文 WER 僅供參考
        
        # 顯示 Metrics (專業風格)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("CER (Character Error Rate)", f"{cer:.2%}")
        m2.metric("WER (Word Error Rate)", f"{wer:.2%}")
        m3.metric("Total Segments", len(edited_df))
        m4.metric("Correction Needed", f"{len(edited_df[edited_df['original'] != edited_df['corrected']])}")

        # --- 視覺化核心 (Side-by-Side View) ---
        st.subheader("Discrepancy Visualization (Model vs. Human)")
        
        # 使用專門的 Header CSS
        st.markdown("""
        <div class="diff-container diff-header">
            <div class="diff-col" style="flex:0.5">Speaker</div>
            <div class="diff-col">Model Output (Baseline)</div>
            <div class="diff-col">Human Correction (Ground Truth)</div>
        </div>
        """, unsafe_allow_html=True)
        
        diff_found = False

        for idx, row in edited_df.iterrows():
            if row['original'] != row['corrected']:
                diff_found = True
                html_model, html_human = highlight_differences(row['original'], row['corrected'])
                
                st.markdown(f"""
                <div class="diff-container">
                    <div class="diff-col" style="flex:0.5; color: #aaa;">{row['speaker']}</div>
                    <div class="diff-col">{html_model}</div>
                    <div class="diff-col">{html_human}</div>
                </div>
                """, unsafe_allow_html=True)
            
        if not diff_found:
            st.success("No discrepancies detected. The model output matches the human ground truth perfectly.")

        # --- 資料匯出 (For Fine-tuning) ---
        st.markdown("---")
        st.subheader("3. Dataset Export (For Model Fine-tuning)")
        
        col_json, col_download = st.columns([4, 1])
        
        json_data = convert_to_training_format(edited_df)
        
        with col_json:
            st.text_area("Preview Training Data (JSONL Format)", json_data, height=150)
        
        with col_download:
            st.download_button(
                label="Download Dataset (.json)",
                data=json_data,
                file_name="asd_clinical_finetune_data.json",
                mime="application/json",
                type="primary"
            )

else:
    st.info("Please import audio data via the sidebar to begin the session.")