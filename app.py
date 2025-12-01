import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px
from fpdf import FPDF
import io
import os
import re 
import base64 

# --- CONFIGURATION & SETUP ---
st.set_page_config(page_title="TheraTrack Pro", layout="wide", page_icon="🧠")

# Database Connection
def get_connection():
    # Connect to the local SQLite database file
    conn = sqlite3.connect('therapy_data.db', check_same_thread=False)
    return conn

# File Handling Helpers
def get_base64_data(uploaded_file):
    # Reads file and returns Base64 string for storage
    bytes_data = uploaded_file.read()
    return base64.b64encode(bytes_data).decode('utf-8')

def display_file(filename, filedata_b64, filetype):
    # Decodes Base64 data for display/download
    data_url = f"data:{filetype};base64,{filedata_b64}"
    if 'image' in filetype:
        st.image(data_url, caption=filename, width=200)
    elif 'pdf' in filetype:
        st.markdown(f"**{filename}**")
        st.download_button(
            label="Download PDF",
            data=base64.b64decode(filedata_b64),
            file_name=filename,
            mime=filetype
        )
    else:
        st.markdown(f"File: **{filename}** ({filetype})")
        st.download_button(
            label="Download File",
            data=base64.b64decode(filedata_b64),
            file_name=filename,
            mime=filetype
        )


# Initialize Database Tables
def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Core Tables
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS goals 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS soap_notes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, date DATE, 
                  subjective TEXT, objective TEXT, assessment TEXT, plan TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS client_goals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, 
                  goal_description TEXT, UNIQUE(client_id, goal_description))''')
    c.execute('''CREATE TABLE IF NOT EXISTS diagnostic_history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, date DATE, 
                  diagnosis_code TEXT, diagnosis_description TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS client_files
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, filename TEXT, 
                  filetype TEXT, filedata BLOB, upload_date DATE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS therapist_checkin 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, date DATE,
                  therapist_id TEXT, energy_rating INTEGER, focus_rating INTEGER, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS session_resources 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER, title TEXT,
                  url TEXT, notes TEXT, therapist_id TEXT)''')
                  
    # NEW TABLE: Sites
    c.execute('''CREATE TABLE IF NOT EXISTS sites 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, address TEXT, type TEXT, therapist_id TEXT)''')

    # Clients table must be created/updated with 'site_id'
    c.execute('''CREATE TABLE IF NOT EXISTS clients 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, dob DATE, diagnosis TEXT, history TEXT, 
                  therapist_id TEXT)''')
    try:
        c.execute("ALTER TABLE clients ADD COLUMN status TEXT DEFAULT 'Active'")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE clients ADD COLUMN site_id INTEGER")
    except sqlite3.OperationalError:
        pass


    # Sessions table must be created/updated with 'session_time'
    c.execute('''CREATE TABLE IF NOT EXISTS sessions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  client_id INTEGER, date DATE, session_number INTEGER, 
                  goals_selected TEXT, progress_notes TEXT, 
                  rating INTEGER, therapist_id TEXT)''')
    try:
        c.execute("ALTER TABLE sessions ADD COLUMN session_time TEXT")
    except sqlite3.OperationalError:
        pass 
    
    # Seed Default Goals (Goal Templates)
    c.execute("SELECT count(*) FROM goals")
    if c.fetchone()[0] == 0:
        default_goals = [
            ("Emotional & Psychological Well-being", "Enhance emotional expression and regulation"),
            ("Emotional & Psychological Well-being", "Increase self-awareness and self-esteem"),
            ("Emotional & Psychological Well-being", "Process and integrate psychological trauma"),
            ("Emotional & Psychological Well-being", "Reduce symptoms of anxiety, depression, and stress"),
            ("Emotional & Psychological Well-being", "Improve mood and overall quality of life"),
            ("Emotional & Psychological Well-being", "Develop positive coping mechanisms"),
            ("Physical Health & Function", "Increase body awareness and mind-body connection"),
            ("Physical Health & Function", "Improve coordination, balance, strength, and flexibility"),
            ("Physical Health & Function", "Reduce muscle tension and chronic pain"),
            ("Physical Health & Function", "Enhance motor skills and range of motion"),
            ("Social & Interpersonal Functioning", "Develop effective verbal and nonverbal communication skills"),
            ("Social & Interpersonal Functioning", "Build trust and empathy in relationships"),
            ("Social & Interpersonal Functioning", "Enhance interpersonal relationships and social interaction"),
            ("Social & Interpersonal Functioning", "Overcome social isolation and foster a sense of belonging"),
            ("Cognitive Function & Insight", "Improve executive function, attention, and memory"),
            ("Cognitive Function & Insight", "Gain insight into personal behaviors and patterns"),
            ("Cognitive Function & Insight", "Enhance problem-solving abilities"),
            ("Cognitive Function & Insight", "Stimulate neuroplasticity and brain function")
        ]
        c.executemany("INSERT INTO goals (category, description) VALUES (?, ?)", default_goals)
        
    # Seed Default Admin User
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES ('admin', 'admin')")

    conn.commit()
    conn.close()

init_db()

# --- BATCH FILE CREATION FOR EASY LAUNCH ---
def create_batch_file(full_command):
    batch_file_content = f'@echo off\n{full_command} run app.py\npause'
    try:
        with open('run_app.bat', 'w') as f:
            f.write(batch_file_content)
        st.success(f"✅ Success! A file named **run_app.bat** has been created in your folder. Double-click it next time to launch the app!")
    except Exception as e:
        st.warning(f"Could not create batch file: {e}")

# --- AUTHENTICATION ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

def login_page():
    if not os.path.exists('run_app.bat'):
        st.subheader("🛠️ Setup Note")
        st.info("If you had to use a long command to launch this, click below to create a simple shortcut for future use.")
        if st.button("Create Double-Click Launch File"):
            specific_path = r"C:\Users\dwtdm\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe -m streamlit"
            create_batch_file(specific_path)
    
    st.markdown("## 🔒 Therapist Login")
    st.write("Default login: **admin** / **admin**")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            st.session_state.logged_in = True
            st.session_state.user = username
            st.rerun()
        else:
            st.error("Invalid credentials")

# --- PDF GENERATOR (Print Reports) ---
def create_pdf(client_name, df_sessions, df_soap):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Client Report: {client_name}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Session Summary", ln=True, align='L')
    
    pdf.set_font("Arial", size=10)
    for index, row in df_sessions.iterrows():
        line = f"Date: {row['date']} ({row.get('session_time', 'N/A')}) | Session: {row['session_number']} | Rating: {row['rating']}/10"
        pdf.cell(200, 10, txt=line, ln=True)
        pdf.multi_cell(0, 5, txt=f"Notes: {row['progress_notes']}")
        pdf.ln(2)
        
    return pdf.output(dest='S').encode('latin-1')

# --- MAIN APP ---
def main_app():
    conn = get_connection()
    
    with st.sidebar:
        st.title(f"Welcome, {st.session_state.user}")
        menu = st.radio("Navigation", 
                        ["Dashboard", "New Session", "Client Records", "Analytics & Reports", "Goal Management", "My Sites"]) # Added My Sites
        st.divider()
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

    # --- DASHBOARD (Risk Alert) ---
    if menu == "Dashboard":
        st.header("Practice Overview")
        
        # --- 🚨 HIGH RISK ALERT WIDGET ---
        risk_df = pd.read_sql(f"""
            SELECT c.name, s.assessment, s.date 
            FROM soap_notes s 
            JOIN clients c ON s.client_id = c.id 
            WHERE c.therapist_id='{st.session_state.user}' 
            ORDER BY s.date DESC
        """, conn)
        
        if not risk_df.empty:
            latest_notes = risk_df.drop_duplicates(subset=['name'], keep='first')
            risk_keywords = ["Suicidal Ideation", "Homicidal Ideation", "Self-Harm Risk", "Grave Disability"]
            
            high_risk_clients = latest_notes[latest_notes['assessment'].apply(
                lambda x: any(risk in x for risk in risk_keywords) if x else False
            )]
            
            if not high_risk_clients.empty:
                st.error("🚨 **ATTENTION: High Risk Flags Detected in Latest Notes**")
                for i, row in high_risk_clients.iterrows():
                    client_data_result = pd.read_sql(f"SELECT id, status FROM clients WHERE name='{row['name']}'", conn)
                    if not client_data_result.empty:
                        client_id = client_data_result.iloc[0]['id']
                        current_status = client_data_result.iloc[0]['status']
                    else:
                        continue 
                        
                    try:
                        risk_status = row['assessment'].split('|')[0] 
                    except:
                        risk_status = row['assessment']
                        
                    st.markdown(f"**{row['name']}** (Current Status: {current_status})")
                    st.caption(f"🚩 Flag: {risk_status}")
                    
                    with st.form(key=f"risk_update_form_{client_id}"):
                        col_update_1, col_update_2 = st.columns([3, 1])
                        
                        with col_update_1:
                            new_status = st.selectbox(
                                "Update Status/Action:",
                                options=['Active', 'Inactive/On Hold', 'Terminated/Completed', 'Terminated/No Show'],
                                index=['Active', 'Inactive/On Hold', 'Terminated/Completed', 'Terminated/No Show'].index(current_status),
                                label_visibility="collapsed"
                            )
                        
                        with col_update_2:
                            update_button = st.form_submit_button(f"Update Status", type="primary")
                    
                    if update_button:
                        conn.execute("UPDATE clients SET status=? WHERE id=?", (new_status, client_id))
                        conn.commit()
                        st.success(f"Status for {row['name']} updated to: {new_status}")
                        st.rerun()

                    st.divider()

        # Fetch Quick Stats
        client_count_df = pd.read_sql(f"SELECT count(*) FROM clients WHERE therapist_id='{st.session_state.user}' AND status='Active'", conn)
        client_count = client_count_df.iloc[0,0] if not client_count_df.empty else 0
        
        session_count_df = pd.read_sql(f"SELECT count(*) FROM sessions WHERE therapist_id='{st.session_state.user}'", conn)
        session_count = session_count_df.iloc[0,0] if not session_count_df.empty else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Active Clients", client_count)
        col2.metric("Total Sessions", session_count)
        col3.metric("Date", datetime.now().strftime("%Y-%m-%d"))
        
        st.subheader("Recent Sessions")
        recent = pd.read_sql(f"""
            SELECT c.name, s.date, s.session_time, s.rating 
            FROM sessions s JOIN clients c ON s.client_id = c.id 
            WHERE s.therapist_id='{st.session_state.user}' 
            ORDER BY s.date DESC LIMIT 5""", conn)
        st.dataframe(recent, use_container_width=True)

    # --- NEW SESSION ---
    elif menu == "New Session":
        st.header("📝 Enter Session Data")
        
        clients = pd.read_sql(f"SELECT id, name FROM clients WHERE therapist_id='{st.session_state.user}' AND status='Active'", conn)
        if clients.empty:
            st.warning("Please add an Active client in 'Client Records' first.")
        else:
            client_map = dict(zip(clients['name'], clients['id']))
            selected_client_name = st.selectbox("Select Participant", clients['name'])
            client_id = client_map[selected_client_name]
            
            c1, c2 = st.columns(2)
            with c1:
                sess_date = st.date_input("Date")
                sess_num = st.number_input("Session Number", min_value=1, value=1)
            with c2:
                session_time = st.time_input("Session Time", value=datetime.now().time()) 
                rating = st.slider("Progress Rating (1-10)", 1, 10, 5) 
            
            assigned_goals_df = pd.read_sql(f"SELECT goal_description FROM client_goals WHERE client_id={client_id}", conn)
            if not assigned_goals_df.empty:
                all_goals = assigned_goals_df['goal_description'].tolist()
                st.info("Goal list filtered to Client's Assigned Goals.")
            else:
                all_goals_df = pd.read_sql("SELECT description FROM goals", conn)
                all_goals = all_goals_df['description'].tolist()
            
            goals_selected = st.multiselect("Select Goals Addressed", all_goals) 
            
            progress_notes = st.text_area("**Goals Achieved / Progress Noted**") 
            
            if st.button("Save Session"):
                c = conn.cursor()
                goals_str = ", ".join(goals_selected)
                c.execute("""INSERT INTO sessions (client_id, date, session_number, goals_selected, progress_notes, rating, therapist_id, session_time)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
                             (client_id, sess_date, sess_num, goals_str, progress_notes, rating, st.session_state.user, session_time.strftime('%H:%M')))
                conn.commit()
                st.success("Session Saved Successfully!")

    # --- CLIENT RECORDS (8 Tabs) ---
    elif menu == "Client Records":
        st.header("📂 Client Details")
        
        # Get Sites for new client creation
        sites_df = pd.read_sql(f"SELECT id, name, type FROM sites WHERE therapist_id='{st.session_state.user}'", conn)
        site_options = ["None Assigned"] + sites_df['name'].tolist()
        site_map = {name: sid for sid, name in zip(sites_df['id'], sites_df['name'])}
        
        # Create New Client
        with st.expander("Add New Client"):
            if sites_df.empty:
                 st.warning("Please set up a session site in 'My Sites' before adding a client.")
                 new_site_selection = "None Assigned"
            
            new_name = st.text_input("Client Name")
            new_dob = st.date_input("Date of Birth")
            new_diag = st.text_input("Primary Diagnosis (Initial)")
            new_site_selection = st.selectbox("Associated Session Site", site_options)
            
            if st.button("Create Client"):
                if new_site_selection == "None Assigned" and not sites_df.empty:
                    st.error("Please select a session site.")
                else:
                    site_id_to_save = site_map.get(new_site_selection)
                    c = conn.cursor()
                    c.execute("INSERT INTO clients (name, dob, diagnosis, therapist_id, site_id) VALUES (?, ?, ?, ?, ?)", 
                              (new_name, new_dob, new_diag, st.session_state.user, site_id_to_save))
                    conn.commit()
                    st.success("Client Added")
                    st.rerun()

        clients = pd.read_sql(f"SELECT * FROM clients WHERE therapist_id='{st.session_state.user}'", conn)
        if not clients.empty:
            selected_client_name = st.selectbox("Select Client to View", clients['name'])
            client_data = clients[clients['name'] == selected_client_name].iloc[0]
            client_id = int(client_data['id'])
            
            # --- TABS ---
            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
                "Client Profile", "SOAP Notes", "Structured Plans", "Diagnostic History", 
                "Client Goals", "Files/Art", "Self Check-In", "Resources"
            ])
            
            with tab1: # Client Profile (Status/Termination, Site Display)
                
                # --- Profile Display (Updated) ---
                st.subheader(f"Client Profile: {client_data['name']}")
                
                # Get site information
                site_display = "Not Assigned"
                if pd.notna(client_data['site_id']) and client_data['site_id'] not in (0, None):
                    site_id_int = int(client_data['site_id'])
                    site_info_df = pd.read_sql(f"SELECT name, type FROM sites WHERE id={site_id_int}", conn)
                    if not site_info_df.empty:
                        site_info = site_info_df.iloc[0]
                        site_display = f"**{site_info['name']}** ({site_info['type']})"
                
                # Get session count
                session_count = pd.read_sql(f"SELECT count(*) FROM sessions WHERE client_id={client_id}", conn).iloc[0,0]
                current_status = client_data['status'] if 'status' in client_data else 'Active'

                col_info_1, col_info_2 = st.columns(2)
                
                with col_info_1:
                    st.markdown(f"**Date of Birth:** {client_data['dob']}")
                    st.markdown(f"**Primary Diagnosis:** {client_data['diagnosis']}")
                    st.markdown(f"**Associated Site:** {site_display}")
                    
                with col_info_2:
                    st.markdown(f"**Current Status:** :blue[{current_status}]")
                    st.markdown(f"**Total Sessions Logged:** {session_count}")
                    
                st.divider()

                # --- Client Status Management ---
                st.subheader("Client Status Management")
                
                new_status = st.selectbox(
                    "Change Client Status", 
                    options=['Active', 'Inactive/On Hold', 'Terminated/Completed', 'Terminated/No Show'],
                    index=['Active', 'Inactive/On Hold', 'Terminated/Completed', 'Terminated/No Show'].index(current_status)
                )

                if st.button("Update Status"):
                    conn.execute("UPDATE clients SET status=? WHERE id=?", (new_status, client_id))
                    conn.commit()
                    st.success(f"Client status updated to: **{new_status}**")
                    st.rerun()
                
                st.divider()
                
                # --- History Update ---
                curr_hist = client_data['history'] if client_data['history'] else ""
                new_hist = st.text_area("Medical/Personal History", value=curr_hist)
                if st.button("Update History"):
                    conn.execute("UPDATE clients SET history=? WHERE id=?", (new_hist, client_id))
                    conn.commit()
                    st.success("History Updated")

                st.divider()

                # --- DANGER ZONE: DELETE CLIENT (New Feature) ---
                st.subheader("⚠️ Danger Zone: Delete Client")
                st.error("Permanently deleting the client will remove ALL associated session data, SOAP notes, goals, and files.")
                
                with st.form(key="delete_client_form"):
                    
                    st.warning(f"Are you absolutely sure you want to delete **{selected_client_name}**?")
                    confirm_delete = st.form_submit_button("I Understand: PERMANENTLY DELETE CLIENT", type="primary")
                
                if confirm_delete:
                    # Deletion Logic: Cascade delete across all related tables
                    c = conn.cursor()
                    
                    c.execute("DELETE FROM clients WHERE id=?", (client_id,))
                    c.execute("DELETE FROM sessions WHERE client_id=?", (client_id,))
                    c.execute("DELETE FROM soap_notes WHERE client_id=?", (client_id,))
                    c.execute("DELETE FROM client_goals WHERE client_id=?", (client_id,))
                    c.execute("DELETE FROM diagnostic_history WHERE client_id=?", (client_id,))
                    c.execute("DELETE FROM client_files WHERE client_id=?", (client_id,))
                    c.execute("DELETE FROM therapist_checkin WHERE client_id=?", (client_id,))
                    c.execute("DELETE FROM session_resources WHERE client_id=?", (client_id,))
                    
                    conn.commit()
                    st.success(f"Client {selected_client_name} and ALL associated records have been permanently deleted.")
                    # Must rerun to clear the dropdown menu
                    st.rerun() 

            # --- SOAP NOTE SECTION ---
            with tab2:
                st.subheader("📝 Add SOAP Note")
                
                st.markdown("#### Subjective (Client Reports)")
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    reported_mood = st.selectbox("Reported Mood", ["Euthymic/Neutral", "Depressed/Sad", "Anxious/Worried", "Angry/Irritable", "Euphoric/Manic", "Fluctuating"], key="s_mood")
                    symptoms = st.multiselect("Presenting Symptoms", ["Sleep Disturbance", "Appetite Changes", "Low Energy", "Panic Attacks", "Flashbacks", "Social Withdrawal", "Excessive Guilt", "Substance Use"], key="s_symp")
                with col_s2:
                    s_narrative = st.text_area("Subjective Narrative (Quotes/Context)", height=100, key="s_narr")
                final_subj = f"Mood: {reported_mood} | Symptoms: {', '.join(symptoms)}\nNotes: {s_narrative}"

                st.divider()

                st.markdown("#### Objective (Therapist Observations)")
                col_o1, col_o2 = st.columns(2)
                with col_o1:
                    affect = st.selectbox("Affect", ["Appropriate/Congruent", "Flat/Blunted", "Labile", "Constricted", "Inappropriate"], key="o_aff")
                    orientation = st.multiselect("Orientation", ["Person", "Place", "Time", "Situation"], default=["Person", "Place", "Time", "Situation"], key="o_orient")
                    appearance = st.multiselect("Appearance/Behavior", ["Well-Groomed", "Disheveled", "Psychomotor Agitation", "Psychomotor Retardation", "Poor Eye Contact", "Cooperative"], key="o_app")
                with col_o2:
                    o_narrative = st.text_area("Objective Observations (Details)", height=150, key="o_narr")
                final_obj = f"Affect: {affect} | Orientation: {', '.join(orientation)} | Appearance: {', '.join(appearance)}\nNotes: {o_narrative}"

                st.divider()

                col_ap1, col_ap2 = st.columns(2)
                with col_ap1:
                    st.markdown("#### Assessment")
                    risk_status = st.multiselect("Risk Assessment", ["No Current Risk", "Suicidal Ideation", "Homicidal Ideation", "Self-Harm Risk", "Grave Disability"], key="a_risk")
                    s_assess = st.text_area("Clinical Impression/Analysis", height=100, key="a_assess")
                    final_assess = f"Risk: {', '.join(risk_status)} | Analysis: {s_assess}"
                
                with col_ap2:
                    st.markdown("#### Plan")
                    next_sess = st.date_input("Next Session Date", key="p_date")
                    s_plan = st.text_area("Interventions & Homework", height=100, key="p_plan")
                    final_plan = f"Next Session: {next_sess}\nPlan: {s_plan}"

                if st.button("Save SOAP Note", type="primary"):
                    conn.execute("INSERT INTO soap_notes (client_id, date, subjective, objective, assessment, plan) VALUES (?, ?, ?, ?, ?, ?)",
                                 (client_id, datetime.now(), final_subj, final_obj, final_assess, final_plan))
                    conn.commit()
                    st.success("SOAP Note Saved Successfully!")
                    st.rerun()
                
                st.divider()
                st.subheader("📜 Past SOAP Notes")
                soap_hist = pd.read_sql(f"SELECT date, subjective, objective, assessment, plan FROM soap_notes WHERE client_id={client_id} ORDER BY date DESC", conn)
                
                for i, note in soap_hist.iterrows():
                    with st.expander(f"Note from {note['date']}"):
                        st.markdown(f"**S:** {note['subjective']}")
                        st.markdown(f"**O:** {note['objective']}")
                        st.markdown(f"**A:** {note['assessment']}")
                        st.markdown(f"**P:** {note['plan']}")
            
            # --- STRUCTURED SESSION PLANS ---
            with tab3: 
                st.subheader("📅 Structured Session Plan Fields")
                st.info("Fill out these fields to structure your next session plan.")
                
                plan_date = st.date_input("Plan Date for Next Session")
                
                st.markdown("##### Session Structure")
                intro = st.text_area("1. Introduction/Arrival", height=70)
                check_in = st.text_area("2. Check-In", height=70)
                warm_up = st.text_area("3. Warm-Up", height=70)
                main_theme = st.text_area("4. Main Theme/Activity", height=100)
                reflection = st.text_area("5. Reflection", height=70)
                props = st.text_area("6. Props Used", height=70)
                closing = st.text_area("7. Closing", height=70)
                additional_notes = st.text_area("8. Additional Notes", height=100)
                
                full_plan = f"Plan Date: {plan_date}\n\n"
                full_plan += f"1. Introduction/Arrival: {intro}\n"
                full_plan += f"2. Check-In: {check_in}\n"
                full_plan += f"3. Warm-Up: {warm_up}\n"
                full_plan += f"4. Main Theme/Activity: {main_theme}\n"
                full_plan += f"5. Reflection: {reflection}\n"
                full_plan += f"6. Props Used: {props}\n"
                full_plan += f"7. Closing: {closing}\n"
                full_plan += f"8. Additional Notes: {additional_notes}"
                
                if st.button("Display Plan for Copying"):
                    st.code(full_plan, language='text', height=400)
                    st.warning("Note: This plan is not stored persistently. Please copy the generated text if you need to save it elsewhere.")


            with tab4: # Diagnostic History
                st.subheader("Add New Diagnostic Entry")
                
                with st.form("new_diagnosis_form"):
                    diag_date = st.date_input("Date of Diagnosis/Review")
                    diag_code = st.text_input("Diagnosis Code (e.g., F33.2)")
                    diag_desc = st.text_area("Diagnosis Description/Title", value=client_data['diagnosis'])
                    diag_notes = st.text_area("Notes/Rationale for Diagnosis")
                    
                    if st.form_submit_button("Log New Diagnosis"):
                        if diag_code and diag_desc:
                            conn.execute("""
                                INSERT INTO diagnostic_history (client_id, date, diagnosis_code, diagnosis_description, notes) 
                                VALUES (?, ?, ?, ?, ?)
                            """, (client_id, diag_date, diag_code, diag_desc, diag_notes))
                            conn.execute("UPDATE clients SET diagnosis=? WHERE id=?", (diag_desc, client_id))
                            conn.commit()
                            st.success("Diagnostic entry saved and client's Primary Diagnosis updated.")
                            st.rerun()
                        else:
                            st.error("Diagnosis Code and Description are required.")
                
                st.divider()
                st.subheader("Past Diagnostic History")
                diag_hist_df = pd.read_sql(f"SELECT date, diagnosis_code, diagnosis_description, notes FROM diagnostic_history WHERE client_id={client_id} ORDER BY date DESC", conn)
                
                if not diag_hist_df.empty:
                    st.dataframe(diag_hist_df, use_container_width=True)
                else:
                    st.info("No formal diagnostic history logged yet.")


            with tab5: # Client Goals
                st.subheader(f"🎯 Assigned Goals for {selected_client_name}")

                global_goals_df = pd.read_sql("SELECT description FROM goals ORDER BY description", conn)
                assigned_goals_df = pd.read_sql(f"SELECT goal_description FROM client_goals WHERE client_id={client_id} ORDER BY goal_description", conn)
                
                current_assigned = assigned_goals_df['goal_description'].tolist()
                
                st.info("Select goals below to assign them permanently to this client. Only assigned goals will appear in the 'New Session' selection dropdown.")

                new_assigned = st.multiselect(
                    "Select Goals to Assign to Client",
                    options=global_goals_df['description'].tolist(),
                    default=current_assigned
                )

                if st.button("Update Client Goals", type="primary"):
                    c = conn.cursor()
                    goals_to_remove = set(current_assigned) - set(new_assigned)
                    for goal in goals_to_remove:
                        c.execute("DELETE FROM client_goals WHERE client_id=? AND goal_description=?", (client_id, goal))
                    
                    goals_to_add = set(new_assigned) - set(current_assigned)
                    for goal in goals_to_add:
                        try:
                            c.execute("INSERT INTO client_goals (client_id, goal_description) VALUES (?, ?)", (client_id, goal))
                        except sqlite3.IntegrityError:
                            pass 

                    conn.commit()
                    st.success(f"Goals updated for {selected_client_name}!")
                    st.rerun()
                    
            with tab6: # File Uploads/Art
                st.subheader("🖼️ Upload Client Files or Art")
                
                uploaded_file = st.file_uploader("Choose a file (Image, PDF, etc.)", type=['png', 'jpg', 'jpeg', 'pdf', 'txt'])
                file_note = st.text_area("Notes on File/Art Content (e.g., 'Drawing of a safe place')")
                
                if uploaded_file is not None and st.button("Save File to Client Record"):
                    if uploaded_file.size > 2 * 1024 * 1024:
                        st.error("File size limit is 2MB for storage in the database. Please upload a smaller file.")
                    else:
                        file_data_b64 = get_base64_data(uploaded_file)
                        
                        conn.execute("""
                            INSERT INTO client_files (client_id, filename, filetype, filedata, upload_date)
                            VALUES (?, ?, ?, ?, ?)
                        """, (client_id, uploaded_file.name, uploaded_file.type, file_data_b64, datetime.now().date()))
                        conn.commit()
                        st.success(f"File '{uploaded_file.name}' saved successfully!")
                        st.rerun()
                        
                st.divider()
                st.subheader("Stored Client Files")
                
                files_df = pd.read_sql(f"SELECT id, filename, filetype, upload_date, filedata FROM client_files WHERE client_id={client_id} ORDER BY upload_date DESC", conn)
                
                if not files_df.empty:
                    cols = st.columns(4)
                    for i, row in files_df.iterrows():
                        with cols[i % 4]:
                            display_file(row['filename'], row['filedata'], row['filetype'])
                            st.caption(f"Uploaded: {row['upload_date']}")
                            if st.button("Delete", key=f"del_{row['id']}"):
                                conn.execute("DELETE FROM client_files WHERE id=?", (row['id'],))
                                conn.commit()
                                st.warning("File deleted.")
                                st.rerun()
                else:
                    st.info("No files or art uploaded for this client yet.")
                    
            # --- THERAPIST SELF CHECK-IN ---
            with tab7: 
                st.subheader("🧠 Therapist Self Check-In")
                st.info("Log your internal state related to working with this client.")
                
                checkin_date = st.date_input("Check-In Date")
                
                t_energy = st.slider("Energy Level (1=Low, 10=High)", 1, 10, 5, key="t_energy")
                t_focus = st.slider("Focus Level (1=Poor, 10=Excellent)", 1, 10, 5, key="t_focus")
                t_notes = st.text_area("Notes on Emotional/Physical State (Related to Session)", key="t_notes")
                
                if st.button("Log Therapist Check-In"):
                    conn.execute("""
                        INSERT INTO therapist_checkin (client_id, date, therapist_id, energy_rating, focus_rating, notes) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (client_id, checkin_date, st.session_state.user, t_energy, t_focus, t_notes))
                    conn.commit()
                    st.success("Therapist Check-In Logged.")
                    st.rerun()
                
                st.divider()
                st.subheader("Check-In History")
                checkin_hist_df = pd.read_sql(f"SELECT date, energy_rating, focus_rating, notes FROM therapist_checkin WHERE client_id={client_id} ORDER BY date DESC", conn)
                st.dataframe(checkin_hist_df, use_container_width=True)

            # --- RESOURCE LIST ---
            with tab8: 
                st.subheader("📚 Session Resource List")
                st.info("List external links, books, or exercises recommended to the client.")
                
                with st.form("new_resource_form"):
                    resource_title = st.text_input("Resource Title (e.g., '5-Minute Grounding Exercise')")
                    resource_url = st.text_input("URL/External Link (Optional)")
                    resource_notes = st.text_area("Notes (When to use, context, etc.)")
                    
                    if st.form_submit_button("Add Resource"):
                        if resource_title:
                            conn.execute("""
                                INSERT INTO session_resources (client_id, therapist_id, title, url, notes)
                                VALUES (?, ?, ?, ?, ?)
                            """, (client_id, st.session_state.user, resource_title, resource_url, resource_notes))
                            conn.commit()
                            st.success("Resource Added!")
                            st.rerun()
                        else:
                            st.error("Resource Title is required.")
                            
                st.divider()
                st.subheader("Client's Resources")
                resource_hist_df = pd.read_sql(f"SELECT title, url, notes FROM session_resources WHERE client_id={client_id} ORDER BY title ASC", conn)
                st.dataframe(resource_hist_df, use_container_width=True)


    # --- ANALYTICS & REPORTS (Visualization and CSV Export) ---
    elif menu == "Analytics & Reports":
        st.header("📊 Analytics & Visualization")
        
        clients = pd.read_sql(f"SELECT id, name FROM clients WHERE therapist_id='{st.session_state.user}'", conn)
        
        if not clients.empty:
            # Filtering 
            col1, col2, col3 = st.columns(3)
            with col1:
                client_filter = st.selectbox("Filter by Participant", ["All"] + list(clients['name']))
            with col2:
                goal_filter = st.text_input("Filter by Specific Goal Keyword")
            with col3:
                # Date filter setup
                df_sessions_raw = pd.read_sql(f"""
                    SELECT c.name, s.date, s.session_number, s.rating, s.goals_selected, s.progress_notes 
                    FROM sessions s 
                    JOIN clients c ON s.client_id = c.id 
                    WHERE s.therapist_id='{st.session_state.user}'
                    ORDER BY s.date ASC
                """, conn)
                
                df_sessions_raw['date'] = pd.to_datetime(df_sessions_raw['date'])
                
                min_date = df_sessions_raw['date'].min().date() if not df_sessions_raw.empty else datetime.now().date()
                max_date = df_sessions_raw['date'].max().date() if not df_sessions_raw.empty else datetime.now().date()
                
                date_range = st.date_input("Filter by Date Range", [min_date, max_date])
                
                df = df_sessions_raw
                
                # Apply Python Filtering
                if client_filter != "All":
                    df = df[df['name'] == client_filter]
                
                if goal_filter:
                    df = df[df['goals_selected'].str.contains(goal_filter, case=False, na=False)]

                if len(date_range) == 2:
                    start_date, end_date = date_range[0], date_range[1]
                    df = df[(df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)]


            if not df.empty:
                st.subheader("Progress Over Time (Numerical Rating)")
                # Visualization 1: Progress Over Time (Numerical)
                fig_progress = px.line(df, x='date', y='rating', color='name', markers=True, title="Session Ratings (1-10)")
                st.plotly_chart(fig_progress, use_container_width=True)
                
                # --- GOAL ACHIEVEMENT FREQUENCY ---
                st.subheader("Goal Achievement Frequency by Session")
                
                all_goals_list = []
                for goals_str in df['goals_selected'].dropna():
                    goals = [g.strip() for g in goals_str.split(',') if g.strip()]
                    all_goals_list.extend(goals)
                
                if all_goals_list:
                    goal_counts = pd.Series(all_goals_list).value_counts().reset_index()
                    goal_counts.columns = ['Goal', 'Frequency (Sessions)']
                    
                    # Visualization 2: Goal Frequency (Goals achieved in session)
                    fig_goals = px.bar(
                        goal_counts.sort_values(by='Frequency (Sessions)', ascending=True),
                        y='Goal', 
                        x='Frequency (Sessions)',
                        color='Frequency (Sessions)',
                        orientation='h',
                        title=f"Frequency of Goals Addressed Across {len(df)} Sessions"
                    )
                    st.plotly_chart(fig_goals, use_container_width=True)
                else:
                    st.info("No goals were selected in the filtered sessions.")
                
                st.subheader("Session Data")
                st.dataframe(df)
                
                # CSV Export
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV (Includes Filters)", csv, "session_data.csv", "text/csv")
                
                # PDF Export (Print Reports)
                if client_filter != "All":
                    client_id_for_pdf = clients[clients['name'] == client_filter]['id'].iloc[0]
                    soap_df = pd.read_sql(f"SELECT * FROM soap_notes WHERE client_id={client_id_for_pdf}", conn)
                    pdf_bytes = create_pdf(client_filter, df, soap_df)
                    st.download_button("Download PDF Report (Print Reports)", pdf_bytes, f"{client_filter}_Report.pdf", "application/pdf")
            else:
                st.info("No data matches these filters.")

    # --- GOAL MANAGEMENT ---
    elif menu == "Goal Management":
        st.header("🎯 Goal Templates")
        
        goals_df = pd.read_sql("SELECT * FROM goals", conn)
        st.dataframe(goals_df, use_container_width=True)
        
        # Add Goal
        st.subheader("Add New Goal Template")
        col1, col2 = st.columns(2)
        with col1:
            new_cat = st.selectbox("Category", [
                "Emotional & Psychological Well-being", 
                "Physical Health & Function", 
                "Social & Interpersonal Functioning", 
                "Cognitive Function & Insight"
            ])
        with col2:
            new_desc = st.text_input("Goal Description")
            
        if st.button("Add Goal"):
            conn.execute("INSERT INTO goals (category, description) VALUES (?, ?)", (new_cat, new_desc))
            conn.commit()
            st.success("Goal added to dropdown menu.")
            st.rerun()
            
        st.divider()
        # Delete Goal
        st.subheader("Delete Existing Goal")
        goal_to_delete = st.selectbox("Select Goal to Delete", goals_df['description'])
        if st.button("Delete Selected Goal"):
            conn.execute("DELETE FROM client_goals WHERE goal_description=?", (goal_to_delete,))
            conn.execute("DELETE FROM goals WHERE description=?", (goal_to_delete,))
            conn.commit()
            st.warning(f"Goal '{goal_to_delete}' deleted.")
            st.rerun()
            
    # --- NEW: MY SITES ---
    elif menu == "My Sites":
        st.header("📍 My Session Sites")
        st.subheader("Add New Site")
        
        with st.form("new_site_form"):
            site_name = st.text_input("Site Name (e.g., Downtown Office, Telehealth Link)")
            site_address = st.text_area("Address (Physical or Virtual URL)")
            site_type = st.selectbox("Site Type", ["Office/Clinic", "School", "Home Visit", "Telehealth/Virtual", "Other"])
            
            if st.form_submit_button("Save New Site"):
                if site_name and site_address:
                    conn.execute("""
                        INSERT INTO sites (name, address, type, therapist_id)
                        VALUES (?, ?, ?, ?)
                    """, (site_name, site_address, site_type, st.session_state.user))
                    conn.commit()
                    st.success(f"Site '{site_name}' added successfully!")
                    st.rerun()
                else:
                    st.error("Site Name and Address/URL are required.")
                    
        st.divider()
        st.subheader("Existing Sites & Associated Clients")
        
        existing_sites_df = pd.read_sql(f"SELECT id, name, type, address FROM sites WHERE therapist_id='{st.session_state.user}'", conn)
        all_clients_df = pd.read_sql(f"SELECT name, status, site_id FROM clients WHERE therapist_id='{st.session_state.user}'", conn)
        
        if not existing_sites_df.empty:
            for i, site in existing_sites_df.iterrows():
                with st.expander(f"**{site['name']}** ({site['type']}) - {site['address']}", expanded=False):
                    
                    # Filter clients for the current site ID
                    site_clients = all_clients_df[all_clients_df['site_id'] == site['id']]
                    
                    if not site_clients.empty:
                        # Display client list
                        st.markdown("##### Clients Assigned to This Site:")
                        site_clients['Client Status'] = site_clients['name'] + " (" + site_clients['status'] + ")"
                        st.dataframe(site_clients[['Client Status']], use_container_width=True, hide_index=True)
                    else:
                        st.info("No clients are currently associated with this site.")

        else:
            st.info("No sites defined yet. Use the form above to add your session locations.")


    conn.close()
    
# --- RUN THE APP ---
if st.session_state.logged_in:
    main_app()
else:
    login_page()