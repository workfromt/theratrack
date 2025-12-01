import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, time
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
                  
    # Sites Table
    c.execute('''CREATE TABLE IF NOT EXISTS sites 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, address TEXT, type TEXT, therapist_id TEXT)''')
    
    # Session Plans (Structured Data)
    c.execute('''CREATE TABLE IF NOT EXISTS session_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER,
                date DATE,
                plan_intro TEXT,
                plan_checkin TEXT,
                plan_warmup TEXT,
                plan_main TEXT,
                plan_reflection TEXT,
                plan_props TEXT,
                plan_closing TEXT,
                plan_notes TEXT,
                therapist_id TEXT
            )''')


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
        
    # Seed Default Admin User (only if no users exist at all)
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
if 'signup_mode' not in st.session_state:
    st.session_state.signup_mode = False

def login_page():
    conn = get_connection()
    c = conn.cursor()
    
    # --- Image Area (Replaced with text header to fix compile error) ---
    st.markdown("<h1 style='text-align: center; color: #1e88e5;'>🧠 TheraTrack: Therapist's Documentation Manager</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: #607d8b;'>Documentation made easy</h3>", unsafe_allow_html=True)
    
    col_login, col_signup = st.columns(2)

    with col_login:
        if not st.session_state.signup_mode:
            st.markdown("## 🔒 Therapist Login")
            
            # --- REMOVED DEFAULT LOGIN MESSAGE HERE ---
            
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Login", type="primary"):
                    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
                    user = c.fetchone()
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.user = username
                        st.session_state.signup_mode = False
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password")
            with c2:
                if st.button("Go to Sign Up"):
                    st.session_state.signup_mode = True
                    st.rerun()

    with col_signup:
        if st.session_state.signup_mode:
            st.markdown("## 📝 New User Sign Up")
            new_user = st.text_input("New Username", key="new_user")
            new_pass = st.text_input("New Password", type="password", key="new_pass")
            
            c3, c4 = st.columns(2)
            with c3:
                if st.button("Create Account", type="primary"):
                    if not new_user or not new_pass:
                        st.error("Username and Password cannot be empty.")
                    else:
                        try:
                            c.execute("INSERT INTO users VALUES (?, ?)", (new_user, new_pass))
                            conn.commit()
                            st.success(f"Account '{new_user}' created! Please log in.")
                            st.session_state.signup_mode = False
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Username already taken.")
            with c4:
                if st.button("Back to Login"):
                    st.session_state.signup_mode = False
                    st.rerun()
                    
    # --- Batch File Creation Prompt ---
    st.divider()
    if not os.path.exists('run_app.bat'):
        st.info("To make launching easier next time, click below to try and generate a double-click shortcut (.bat file).")
        if st.button("Create Double-Click Launch File"):
            # Using a known common WindowsApps path structure for the batch file
            specific_path = r"C:\Users\dwtdm\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe -m streamlit"
            create_batch_file(specific_path)
            
    conn.close()


# --- PDF GENERATOR ---
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
        line = f"Date: {row['date']} | Time: {row['session_time']} | Session: {row['session_number']} | Rating: {row['rating']}/10"
        pdf.cell(200, 10, txt=line, ln=True)
        pdf.multi_cell(0, 5, txt=f"Goals: {row['goals_selected']}")
        pdf.multi_cell(0, 5, txt=f"Notes: {row['progress_notes']}")
        pdf.ln(2)
        
    return pdf.output(dest='S').encode('latin-1')

# --- MAIN APP ---
def main_app():
    conn = get_connection()
    
    with st.sidebar:
        st.title(f"Welcome, {st.session_state.user}")
        menu = st.radio("Navigation", 
                        ["Dashboard", "My Sites", "New Session", "Client Records", "Analytics & Reports", "Goal Management"])
        st.divider()
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

    # --- DASHBOARD (Includes Risk Alert) ---
    if menu == "Dashboard":
        st.header("Practice Overview")
        
        # --- 🚨 RISK ALERT WIDGET ---
        risk_df = pd.read_sql(f"""
            SELECT c.name, s.assessment, s.date, c.id
            FROM soap_notes s 
            JOIN clients c ON s.client_id = c.id 
            WHERE c.therapist_id='{st.session_state.user}' 
            ORDER BY s.date DESC
        """, conn)
        
        clients_df_status = pd.read_sql(f"SELECT id, name, status FROM clients WHERE therapist_id='{st.session_state.user}'", conn)
        
        if not risk_df.empty:
            # Keep only the most recent note for each client
            latest_notes = risk_df.drop_duplicates(subset=['name'], keep='first')
            risk_keywords = ["Suicidal Ideation", "Homicidal Ideation", "Self-Harm Risk", "Grave Disability"]
            
            high_risk_clients = latest_notes[latest_notes['assessment'].apply(
                lambda x: any(risk in x for risk in risk_keywords) if x else False
            )]
            
            if not high_risk_clients.empty:
                st.error("🚨 **ATTENTION: High Risk Flags Detected in Latest Notes**")
                
                for i, row in high_risk_clients.iterrows():
                    col_risk_name, col_risk_status, col_risk_button = st.columns([3, 2, 2])
                    client_id_risk = row['id']
                    
                    # Fetch current status for display
                    current_status = clients_df_status[clients_df_status['id'] == client_id_risk]['status'].iloc[0]
                    
                    with col_risk_name:
                        try:
                            risk_status = row['assessment'].split('|')[0] 
                        except:
                            risk_status = row['assessment']
                            
                        st.markdown(f"**{row['name']}** (Last note: {row['date']})")
                        st.caption(f"🚩 Flag: {risk_status}")
                    
                    with col_risk_status:
                        new_status = st.selectbox(
                            "Update Status", 
                            ["Active", "Terminated", "No-Show", "Inactive"],
                            index=["Active", "Terminated", "No-Show", "Inactive"].index(current_status),
                            key=f"risk_status_{client_id_risk}"
                        )
                        
                    with col_risk_button:
                        if st.button("Apply Update", key=f"risk_update_{client_id_risk}"):
                            conn.execute("UPDATE clients SET status=? WHERE id=?", (new_status, client_id_risk))
                            conn.commit()
                            st.success(f"Status for {row['name']} updated to {new_status}.")
                            st.rerun()
                    
                    st.divider()

        # Fetch Quick Stats
        client_count_df = pd.read_sql(f"SELECT count(*) FROM clients WHERE therapist_id='{st.session_state.user}'", conn)
        client_count = client_count_df.iloc[0,0] if not client_count_df.empty else 0
        
        session_count_df = pd.read_sql(f"SELECT count(*) FROM sessions WHERE therapist_id='{st.session_state.user}'", conn)
        session_count = session_count_df.iloc[0,0] if not session_count_df.empty else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Clients", client_count)
        col2.metric("Total Sessions", session_count)
        col3.metric("Date", datetime.now().strftime("%Y-%m-%d"))
        
        st.subheader("Recent Sessions")
        recent = pd.read_sql(f"""
            SELECT c.name, s.date, s.session_number, s.session_time, s.rating 
            FROM sessions s JOIN clients c ON s.client_id = c.id 
            WHERE s.therapist_id='{st.session_state.user}' 
            ORDER BY s.date DESC LIMIT 5""", conn)
        st.dataframe(recent, use_container_width=True)

    # --- MY SITES ---
    elif menu == "My Sites":
        st.header("📍 Session Site Management")

        # --- Add New Site ---
        with st.expander("➕ Add New Session Site"):
            site_name = st.text_input("Site Name (e.g., Downtown Office, Telehealth Link)")
            site_address = st.text_area("Address / URL", height=50)
            site_type = st.selectbox("Site Type", ["Office", "School", "Home Visit", "Telehealth", "Virtual"])
            
            if st.button("Save Site"):
                if site_name:
                    conn.execute("INSERT INTO sites (name, address, type, therapist_id) VALUES (?, ?, ?, ?)",
                                 (site_name, site_address, site_type, st.session_state.user))
                    conn.commit()
                    st.success(f"Site '{site_name}' added.")
                    st.rerun()
                else:
                    st.error("Site Name cannot be empty.")

        st.divider()
        st.subheader("🌐 Existing Sites & Caseload Breakdown")
        
        sites_df = pd.read_sql(f"SELECT * FROM sites WHERE therapist_id='{st.session_state.user}'", conn)
        clients_all_df = pd.read_sql(f"SELECT id, name, site_id, status FROM clients WHERE therapist_id='{st.session_state.user}'", conn)

        if sites_df.empty:
            st.info("No sites defined yet. Add a site above.")
        else:
            for index, site in sites_df.iterrows():
                site_id = site['id']
                
                # Filter clients for the current site
                site_clients_df = clients_all_df[clients_all_df['site_id'] == site_id]
                
                with st.expander(f"**{site['name']}** ({site['type']}) - {len(site_clients_df)} Clients"):
                    st.caption(f"Address/Details: {site['address']}")
                    
                    if site_clients_df.empty:
                        st.info("No clients currently assigned to this site.")
                    else:
                        client_list = site_clients_df[['name', 'status']].rename(
                            columns={'name': 'Client Name', 'status': 'Status'}
                        )
                        st.dataframe(client_list, use_container_width=True, hide_index=True)

                    # Option to Delete Site
                    if st.button(f"Delete Site: {site['name']}", key=f"delete_site_{site_id}"):
                        if len(site_clients_df) > 0:
                             st.error("Cannot delete site: first unassign all clients.")
                        else:
                            conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
                            conn.commit()
                            st.warning(f"Site '{site['name']}' deleted.")
                            st.rerun()

    # --- NEW SESSION (Goals and Progress Entry) ---
    elif menu == "New Session":
        st.header("📝 Enter Session Data")
        
        clients = pd.read_sql(f"SELECT id, name, status FROM clients WHERE therapist_id='{st.session_state.user}' AND status='Active'", conn)
        
        if clients.empty:
            st.warning("Please add an Active client in 'Client Records' first.")
        else:
            client_map = dict(zip(clients['name'], clients['id']))
            selected_client_name = st.selectbox("Select Participant", clients['name'])
            client_id = client_map[selected_client_name]
            
            col_date, col_time, col_num = st.columns(3)
            with col_date:
                sess_date = st.date_input("Date")
            with col_time:
                sess_time = st.time_input("Session Time", time(10, 00)).strftime("%H:%M") # Added time option
            with col_num:
                sess_num = st.number_input("Session Number", min_value=1, value=1)
            
            rating = st.slider("Progress Rating (1-10)", 1, 10, 5) # Progress Tracking (Numerical)
            
            # Fetch Client-Specific Goals
            client_goals_df = pd.read_sql(f"SELECT goal_description FROM client_goals WHERE client_id={client_id}", conn)
            
            if client_goals_df.empty:
                 st.warning("No specific goals assigned to this client. Navigate to Client Records -> Client Goals to assign them.")
                 all_goals = pd.read_sql("SELECT description FROM goals", conn)
                 available_goals = all_goals['description']
            else:
                 available_goals = client_goals_df['goal_description']
            
            goals_selected = st.multiselect("Select Goals Addressed", available_goals)
            
            progress_notes = st.text_area("**Goals Achieved / Progress Noted**") # Progress Notes Entry
            
            if st.button("Save Session", type="primary"):
                c = conn.cursor()
                goals_str = ", ".join(goals_selected)
                c.execute("""INSERT INTO sessions (client_id, date, session_number, session_time, goals_selected, progress_notes, rating, therapist_id)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
                             (client_id, sess_date, sess_num, sess_time, goals_str, progress_notes, rating, st.session_state.user))
                conn.commit()
                st.success("Session Saved Successfully!")

    # --- CLIENT RECORDS (Client Profile, SOAP, History) ---
    elif menu == "Client Records":
        st.header("📂 Client Details")
        
        # --- Add New Client ---
        sites_available = pd.read_sql(f"SELECT id, name FROM sites WHERE therapist_id='{st.session_state.user}'", conn)
        site_map = dict(zip(sites_available['name'], sites_available['id']))
        site_names = sites_available['name'].tolist()
        
        with st.expander("➕ Add New Client"):
            new_name = st.text_input("Client Name")
            new_dob = st.date_input("Date of Birth")
            new_diag = st.text_input("Primary Diagnosis")
            
            if site_names:
                selected_site_name = st.selectbox("Associated Session Site", site_names)
                new_site_id = site_map[selected_site_name]
            else:
                st.warning("Please define at least one site in 'My Sites' before adding a client.")
                new_site_id = None
                
            if st.button("Create Client"):
                if new_name and new_site_id is not None:
                    c = conn.cursor()
                    c.execute("INSERT INTO clients (name, dob, diagnosis, site_id, therapist_id, status) VALUES (?, ?, ?, ?, ?, ?)", 
                              (new_name, new_dob, new_diag, new_site_id, st.session_state.user, 'Active'))
                    conn.commit()
                    st.success("Client Added")
                    st.rerun()
                elif not new_name:
                    st.error("Client Name is required.")

        # --- Select Existing Client ---
        clients = pd.read_sql(f"SELECT * FROM clients WHERE therapist_id='{st.session_state.user}'", conn)
        if not clients.empty:
            selected_client_name = st.selectbox("Select Client to View", clients['name'])
            client_data = clients[clients['name'] == selected_client_name].iloc[0]
            client_id = int(client_data['id'])
            
            # TABS for detailed records
            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
                "Client Profile", "SOAP Notes", "Session Plans", "Diagnostic History",
                "Client Goals", "Files/Art", "Self Check-In", "Resources"
            ])
            
            # --- Tab 1: Client Profile (Reorganized and Delete Option Added) ---
            with tab1:
                st.subheader("Client Overview")
                
                # --- General Info Display ---
                col_name, col_dob, col_diag = st.columns(3)
                col_status, col_site = st.columns(2)
                
                with col_name: st.markdown(f"**Name:** {client_data['name']}")
                with col_dob: st.markdown(f"**DOB:** {client_data['dob']}")
                with col_diag: st.markdown(f"**Diagnosis:** {client_data['diagnosis']}")
                
                # Site Display (FIXED: Handling nan/None in site_id)
                site_name_display = "N/A (Update Below)"
                if client_data['site_id'] is not None and not pd.isna(client_data['site_id']):
                    site_id_int = int(client_data['site_id'])
                    try:
                        site_info = pd.read_sql(f"SELECT name, type FROM sites WHERE id={site_id_int}", conn).iloc[0]
                        site_name_display = f"{site_info['name']} ({site_info['type']})"
                    except IndexError:
                        site_name_display = "ID Missing/Invalid"
                    except pd.errors.DatabaseError:
                        site_name_display = "DB Error"
                
                with col_site: st.markdown(f"**Primary Site:** {site_name_display}")
                with col_status: st.markdown(f"**Current Status:** :green[{client_data['status']}]" if client_data['status'] == 'Active' else f"**Current Status:** :red[{client_data['status']}]")

                st.divider()

                # --- Status Update Section (Termination/No-Show) ---
                st.subheader("Status & Site Update")
                col_stat_up, col_site_up = st.columns(2)
                
                with col_stat_up:
                    new_status = st.selectbox(
                        "Update Client Status", 
                        ["Active", "Terminated", "No-Show", "Inactive"],
                        index=["Active", "Terminated", "No-Show", "Inactive"].index(client_data['status'])
                    )
                    if st.button("Update Status"):
                        conn.execute("UPDATE clients SET status=? WHERE id=?", (new_status, client_id))
                        conn.commit()
                        st.success(f"Status updated to {new_status}")
                        st.rerun()
                
                with col_site_up:
                    current_site_index = site_names.index(sites_available[sites_available['id'] == client_data['site_id']]['name'].iloc[0]) if client_data['site_id'] is not None and not sites_available.empty and client_data['site_id'] in sites_available['id'].values else 0
                    
                    new_site_name = st.selectbox("Change Associated Session Site", site_names, index=current_site_index)
                    new_site_id = site_map[new_site_name]
                    
                    if st.button("Update Site"):
                        conn.execute("UPDATE clients SET site_id=? WHERE id=?", (new_site_id, client_id))
                        conn.commit()
                        st.success(f"Primary Site updated to {new_site_name}")
                        st.rerun()


                st.divider()

                # --- History Update ---
                st.subheader("Medical/Personal History")
                curr_hist = client_data['history'] if client_data['history'] else ""
                new_hist = st.text_area("Update History Notes", value=curr_hist, height=150)
                if st.button("Update History Notes"):
                    conn.execute("UPDATE clients SET history=? WHERE id=?", (new_hist, client_id))
                    conn.commit()
                    st.success("History Notes Updated")
                    st.rerun()
                    
                st.divider()
                
                # --- DANGER ZONE ---
                st.error("⚠️ DANGER ZONE: Delete Client")
                delete_confirm = st.text_input(f"Type the client's name ('{client_data['name']}') to confirm deletion of ALL associated data:", key="delete_confirm_profile")
                
                if delete_confirm == client_data['name']:
                    if st.button(f"PERMANENTLY DELETE {client_data['name']}", type="secondary"):
                        # Delete from all tables
                        conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
                        conn.execute("DELETE FROM sessions WHERE client_id=?", (client_id,))
                        conn.execute("DELETE FROM soap_notes WHERE client_id=?", (client_id,))
                        conn.execute("DELETE FROM client_goals WHERE client_id=?", (client_id,))
                        conn.execute("DELETE FROM diagnostic_history WHERE client_id=?", (client_id,))
                        conn.execute("DELETE FROM client_files WHERE client_id=?", (client_id,))
                        conn.execute("DELETE FROM therapist_checkin WHERE client_id=?", (client_id,))
                        conn.execute("DELETE FROM session_resources WHERE client_id=?", (client_id,))
                        conn.execute("DELETE FROM session_plans WHERE client_id=?", (client_id,))
                        conn.commit()
                        st.success(f"Client {client_data['name']} and all associated records have been permanently deleted.")
                        st.rerun()
            
            # --- Tab 2: SOAP Notes ---
            with tab2:
                st.subheader("📝 Add SOAP Note")
                # Subjective
                st.markdown("#### Subjective (Client Reports)")
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    reported_mood = st.selectbox("Reported Mood", 
                        ["Euthymic/Neutral", "Depressed/Sad", "Anxious/Worried", "Angry/Irritable", "Euphoric/Manic", "Fluctuating"], key="soap_mood")
                    symptoms = st.multiselect("Presenting Symptoms", 
                        ["Sleep Disturbance", "Appetite Changes", "Low Energy", "Panic Attacks", "Flashbacks", "Social Withdrawal", "Excessive Guilt", "Substance Use"], key="soap_symptoms")
                with col_s2:
                    s_narrative = st.text_area("Subjective Narrative (Quotes/Context)", height=100, key="soap_snarrative")
                final_subj = f"Mood: {reported_mood} | Symptoms: {', '.join(symptoms)}\nNotes: {s_narrative}"

                st.divider()

                # Objective
                st.markdown("#### Objective (Therapist Observations)")
                col_o1, col_o2 = st.columns(2)
                with col_o1:
                    affect = st.selectbox("Affect", ["Appropriate/Congruent", "Flat/Blunted", "Labile", "Constricted", "Inappropriate"], key="soap_affect")
                    orientation = st.multiselect("Orientation", ["Person", "Place", "Time", "Situation"], default=["Person", "Place", "Time", "Situation"], key="soap_orientation")
                    appearance = st.multiselect("Appearance/Behavior", ["Well-Groomed", "Disheveled", "Psychomotor Agitation", "Psychomotor Retardation", "Poor Eye Contact", "Cooperative"], key="soap_appearance")
                with col_o2:
                    o_narrative = st.text_area("Objective Observations (Details)", height=150, key="soap_onarrative")
                final_obj = f"Affect: {affect} | Orientation: {', '.join(orientation)} | Appearance: {', '.join(appearance)}\nNotes: {o_narrative}"

                st.divider()

                # Assessment & Plan
                col_ap1, col_ap2 = st.columns(2)
                with col_ap1:
                    st.markdown("#### Assessment")
                    risk_status = st.multiselect("Risk Assessment", ["No Current Risk", "Suicidal Ideation", "Homicidal Ideation", "Self-Harm Risk", "Grave Disability"], key="soap_risk")
                    s_assess = st.text_area("Clinical Impression/Analysis", height=100, key="soap_assess")
                    final_assess = f"Risk: {', '.join(risk_status)} | Analysis: {s_assess}"
                
                with col_ap2:
                    st.markdown("#### Plan")
                    next_sess = st.date_input("Next Session Date", key="soap_nextdate")
                    s_plan = st.text_area("Interventions & Homework", height=100, key="soap_plan")
                    final_plan = f"Next Session: {next_sess}\nPlan: {s_plan}"

                if st.button("Save SOAP Note", type="primary", key="save_soap"):
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

            # --- Tab 3: Session Plans (Structured Planning) ---
            with tab3:
                st.subheader("🗓️ Create or Update Session Plan")
                
                plan_date = st.date_input("Plan Date", key="plan_date")
                
                st.markdown("---")
                
                col_plan_1, col_plan_2, col_plan_3 = st.columns(3)
                
                with col_plan_1:
                    plan_intro = st.text_area("1. Introduction/Arrival", height=100, key="plan_intro")
                    plan_checkin = st.text_area("2. Check In", height=100, key="plan_checkin")
                
                with col_plan_2:
                    plan_warmup = st.text_area("3. Warm Up", height=100, key="plan_warmup")
                    plan_main = st.text_area("4. Main Theme/Activity", height=100, key="plan_main")
                
                with col_plan_3:
                    plan_reflection = st.text_area("5. Reflection", height=100, key="plan_reflection")
                    plan_closing = st.text_area("6. Closing", height=100, key="plan_closing")

                st.markdown("---")
                
                col_props, col_notes = st.columns(2)
                with col_props:
                    plan_props = st.text_area("Props Used (Materials needed)", height=100, key="plan_props")
                with col_notes:
                    plan_notes = st.text_area("Additional Notes", height=100, key="plan_notes")
                
                if st.button("Save Session Plan", type="primary", key="save_plan"):
                    conn.execute("""INSERT INTO session_plans (client_id, date, plan_intro, plan_checkin, plan_warmup, plan_main, 
                                                               plan_reflection, plan_props, plan_closing, plan_notes, therapist_id) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                 (client_id, plan_date, plan_intro, plan_checkin, plan_warmup, plan_main, 
                                  plan_reflection, plan_props, plan_closing, plan_notes, st.session_state.user))
                    conn.commit()
                    st.success("Session Plan Saved!")
                    st.rerun()

                st.divider()
                st.subheader("Past Session Plans")
                plans_hist = pd.read_sql(f"SELECT date, plan_main, plan_notes FROM session_plans WHERE client_id={client_id} ORDER BY date DESC", conn)
                st.dataframe(plans_hist, use_container_width=True)


            # --- Tab 4: Diagnostic History ---
            with tab4:
                st.subheader("📜 Diagnostic History Log")
                
                col_diag_1, col_diag_2 = st.columns(2)
                with col_diag_1:
                    diag_code = st.text_input("New Diagnosis Code (e.g., F33.2)", key="new_diag_code")
                    diag_desc = st.text_input("Diagnosis Description", key="new_diag_desc")
                with col_diag_2:
                    diag_notes = st.text_area("Notes / Rationale for Diagnosis Change", height=100, key="new_diag_notes")

                if st.button("Log New Diagnosis", type="primary", key="log_diag"):
                    if diag_code and diag_desc:
                        conn.execute("INSERT INTO diagnostic_history (client_id, date, diagnosis_code, diagnosis_description, notes) VALUES (?, ?, ?, ?, ?)",
                                     (client_id, datetime.now(), diag_code, diag_desc, diag_notes))
                        conn.commit()
                        st.success(f"Diagnosis '{diag_desc}' logged.")
                        st.rerun()
                    else:
                        st.error("Code and Description are required.")
                        
                st.divider()
                st.subheader("History")
                diag_hist = pd.read_sql(f"SELECT date, diagnosis_code, diagnosis_description, notes FROM diagnostic_history WHERE client_id={client_id} ORDER BY date DESC", conn)
                st.dataframe(diag_hist, use_container_width=True)

            # --- Tab 5: Client Goals ---
            with tab5:
                st.subheader("🎯 Assign Client-Specific Goals")
                
                all_goals_df = pd.read_sql("SELECT category, description FROM goals", conn)
                client_goals_df = pd.read_sql(f"SELECT goal_description FROM client_goals WHERE client_id={client_id}", conn)
                client_goal_descriptions = client_goals_df['goal_description'].tolist()
                
                # Available goals are those not yet assigned
                assigned_goals = set(client_goal_descriptions)
                available_goals = all_goals_df[~all_goals_df['description'].isin(assigned_goals)]
                
                st.markdown("#### Add Goal from Template")
                
                if available_goals.empty:
                    st.info("All available goal templates have been assigned to this client.")
                else:
                    new_goal = st.selectbox("Select Goal to Assign", available_goals['description'])
                    if st.button("Assign Goal to Client"):
                        conn.execute("INSERT INTO client_goals (client_id, goal_description) VALUES (?, ?)", (client_id, new_goal))
                        conn.commit()
                        st.success(f"Goal '{new_goal}' assigned.")
                        st.rerun()

                st.divider()
                st.markdown("#### Currently Assigned Goals")
                if client_goals_df.empty:
                    st.info("No goals assigned. Use the form above to assign them.")
                else:
                    for goal_desc in client_goal_descriptions:
                        col_g_desc, col_g_del = st.columns([5, 1])
                        with col_g_desc:
                            st.write(f"- {goal_desc}")
                        with col_g_del:
                            if st.button("Remove", key=f"del_goal_{re.sub(r'[^a-zA-Z0-9]', '', goal_desc)[:10]}"):
                                conn.execute("DELETE FROM client_goals WHERE client_id=? AND goal_description=?", (client_id, goal_desc))
                                conn.commit()
                                st.warning("Goal removed.")
                                st.rerun()


            # --- Tab 6: Files/Art ---
            with tab6:
                st.subheader("🖼️ Client Files & Art Upload")
                
                uploaded_file = st.file_uploader("Upload File (Max 2MB)", type=["pdf", "png", "jpg", "jpeg"])
                
                if uploaded_file is not None:
                    if uploaded_file.size > 2 * 1024 * 1024:
                        st.error("File size exceeds 2MB limit.")
                    else:
                        if st.button(f"Save '{uploaded_file.name}'"):
                            file_data_b64 = get_base64_data(uploaded_file)
                            conn.execute("INSERT INTO client_files (client_id, filename, filetype, filedata, upload_date) VALUES (?, ?, ?, ?, ?)",
                                         (client_id, uploaded_file.name, uploaded_file.type, file_data_b64, datetime.now()))
                            conn.commit()
                            st.success(f"File '{uploaded_file.name}' saved.")
                            st.rerun()
                            
                st.divider()
                st.subheader("Saved Files")
                files_df = pd.read_sql(f"SELECT id, filename, filetype, filedata, upload_date FROM client_files WHERE client_id={client_id} ORDER BY upload_date DESC", conn)
                
                if files_df.empty:
                    st.info("No files saved yet.")
                else:
                    for i, row in files_df.iterrows():
                        col_f_name, col_f_view, col_f_del = st.columns([3, 1, 1])
                        with col_f_name:
                            st.write(f"**{row['filename']}** ({row['filetype']})")
                            st.caption(f"Uploaded: {row['upload_date'].split(' ')[0]}")
                        
                        with col_f_view:
                            display_file(row['filename'], row['filedata'], row['filetype'])

                        with col_f_del:
                            if st.button("Delete", key=f"del_file_{row['id']}"):
                                conn.execute("DELETE FROM client_files WHERE id=?", (row['id'],))
                                conn.commit()
                                st.warning(f"File '{row['filename']}' deleted.")
                                st.rerun()

            # --- Tab 7: Therapist Self Check-In ---
            with tab7:
                st.subheader("🧘 Therapist Self Check-In")
                
                col_e, col_f = st.columns(2)
                with col_e:
                    energy_rating = st.slider("Energy Level (1=Low, 10=High)", 1, 10, 5, key="self_energy")
                with col_f:
                    focus_rating = st.slider("Focus Level (1=Distracted, 10=Sharp)", 1, 10, 5, key="self_focus")
                    
                checkin_notes = st.text_area("Notes / Reflections on the session or client dynamics", height=150, key="self_notes")
                
                if st.button("Save Self Check-In", type="primary", key="save_checkin"):
                    conn.execute("INSERT INTO therapist_checkin (client_id, date, therapist_id, energy_rating, focus_rating, notes) VALUES (?, ?, ?, ?, ?, ?)",
                                 (client_id, datetime.now(), st.session_state.user, energy_rating, focus_rating, checkin_notes))
                    conn.commit()
                    st.success("Self Check-In saved.")
                    st.rerun()
                    
                st.divider()
                st.subheader("Past Check-Ins")
                checkin_hist = pd.read_sql(f"SELECT date, energy_rating, focus_rating, notes FROM therapist_checkin WHERE client_id={client_id} ORDER BY date DESC", conn)
                st.dataframe(checkin_hist, use_container_width=True)

            # --- Tab 8: Resources ---
            with tab8:
                st.subheader("📚 Client Resource List")
                
                col_r_title, col_r_url = st.columns(2)
                with col_r_title:
                    resource_title = st.text_input("Resource Title/Name", key="res_title")
                with col_r_url:
                    resource_url = st.text_input("Resource Link (URL)", key="res_url")
                    
                resource_notes = st.text_area("Description / When to use / Homework notes", height=100, key="res_notes")
                
                if st.button("Add Resource", type="primary", key="add_res"):
                    if resource_title:
                        conn.execute("INSERT INTO session_resources (client_id, title, url, notes, therapist_id) VALUES (?, ?, ?, ?, ?)",
                                     (client_id, resource_title, resource_url, resource_notes, st.session_state.user))
                        conn.commit()
                        st.success(f"Resource '{resource_title}' added.")
                        st.rerun()
                    else:
                        st.error("Resource Title is required.")
                        
                st.divider()
                st.subheader("Assigned Resources")
                resources_df = pd.read_sql(f"SELECT id, title, url, notes FROM session_resources WHERE client_id={client_id} ORDER BY id DESC", conn)
                
                for i, row in resources_df.iterrows():
                    col_r_disp, col_r_del = st.columns([5, 1])
                    with col_r_disp:
                        st.markdown(f"**{row['title']}**")
                        if row['url']:
                            st.caption(f"Link: {row['url']}")
                        st.markdown(f"Notes: {row['notes']}")
                    with col_r_del:
                        if st.button("Delete", key=f"del_res_{row['id']}"):
                            conn.execute("DELETE FROM session_resources WHERE id=?", (row['id'],))
                            conn.commit()
                            st.warning(f"Resource '{row['title']}' deleted.")
                            st.rerun()


    # --- MY SITES ---
    elif menu == "My Sites":
        st.header("📍 Session Site Management")

        # --- Add New Site ---
        with st.expander("➕ Add New Session Site"):
            site_name = st.text_input("Site Name (e.g., Downtown Office, Telehealth Link)")
            site_address = st.text_area("Address / URL", height=50)
            site_type = st.selectbox("Site Type", ["Office", "School", "Home Visit", "Telehealth", "Virtual"])
            
            if st.button("Save Site"):
                if site_name:
                    conn.execute("INSERT INTO sites (name, address, type, therapist_id) VALUES (?, ?, ?, ?)",
                                 (site_name, site_address, site_type, st.session_state.user))
                    conn.commit()
                    st.success(f"Site '{site_name}' added.")
                    st.rerun()
                else:
                    st.error("Site Name cannot be empty.")

        st.divider()
        st.subheader("🌐 Existing Sites & Caseload Breakdown")
        
        sites_df = pd.read_sql(f"SELECT * FROM sites WHERE therapist_id='{st.session_state.user}'", conn)
        clients_all_df = pd.read_sql(f"SELECT id, name, site_id, status FROM clients WHERE therapist_id='{st.session_state.user}'", conn)

        if sites_df.empty:
            st.info("No sites defined yet. Add a site above.")
        else:
            for index, site in sites_df.iterrows():
                site_id = site['id']
                
                # Filter clients for the current site
                site_clients_df = clients_all_df[clients_all_df['site_id'] == site_id]
                
                with st.expander(f"**{site['name']}** ({site['type']}) - {len(site_clients_df)} Clients"):
                    st.caption(f"Address/Details: {site['address']}")
                    
                    if site_clients_df.empty:
                        st.info("No clients currently assigned to this site.")
                    else:
                        client_list = site_clients_df[['name', 'status']].rename(
                            columns={'name': 'Client Name', 'status': 'Status'}
                        )
                        st.dataframe(client_list, use_container_width=True, hide_index=True)

                    # Option to Delete Site
                    if st.button(f"Delete Site: {site['name']}", key=f"delete_site_{site_id}"):
                        if len(site_clients_df) > 0:
                             st.error("Cannot delete site: first unassign all clients.")
                        else:
                            conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
                            conn.commit()
                            st.warning(f"Site '{site['name']}' deleted.")
                            st.rerun()

    # --- ANALYTICS & REPORTS (Visualization and CSV Export) ---
    elif menu == "Analytics & Reports":
        st.header("📊 Analytics & Visualization")
        
        clients = pd.read_sql(f"SELECT id, name FROM clients WHERE therapist_id='{st.session_state.user}'", conn)
        
        if not clients.empty:
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                client_filter = st.selectbox("Filter by Participant", ["All"] + list(clients['name']))
            with col2:
                goal_filter = st.text_input("Search by Goal keyword (e.g., 'Anxiety')")

            query = f"""
                SELECT c.name, s.date, s.session_number, s.session_time, s.rating, s.goals_selected, s.progress_notes 
                FROM sessions s 
                JOIN clients c ON s.client_id = c.id 
                WHERE s.therapist_id='{st.session_state.user}'
            """
            
            df = pd.read_sql(query, conn)
            
            # Apply Python Filtering
            if client_filter != "All":
                df = df[df['name'] == client_filter]
            
            if goal_filter:
                df = df[df['goals_selected'].str.contains(goal_filter, case=False, na=False)]

            if not df.empty:
                st.subheader("Progress Over Time")
                # Visualization (Plotly - Rating Trend)
                fig = px.line(df, x='date', y='rating', color='name', markers=True, title="Session Ratings (1-10)")
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("Goal Achievement Frequency (Sessions Addressing Goals)")
                
                # Visualization (Goal Frequency)
                all_goals_addressed = []
                for goals_str in df['goals_selected'].astype(str):
                    all_goals_addressed.extend([g.strip() for g in goals_str.split(',') if g.strip()])
                
                if all_goals_addressed:
                    goal_counts = pd.Series(all_goals_addressed).value_counts().reset_index()
                    goal_counts.columns = ['Goal', 'Sessions Addressed']
                    
                    fig_goals = px.bar(goal_counts, x='Sessions Addressed', y='Goal', orientation='h', 
                                       title="Goal Frequency Across Filtered Sessions")
                    st.plotly_chart(fig_goals, use_container_width=True)
                else:
                    st.info("No goals were logged in the filtered sessions.")


                st.subheader("Session Data")
                st.dataframe(df)
                
                # CSV Export
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("Download CSV", csv, "session_data.csv", "text/csv")
                
                # PDF Export (Print Reports)
                if client_filter != "All":
                    soap_df = pd.read_sql(f"SELECT * FROM soap_notes WHERE client_id=(SELECT id FROM clients WHERE name='{client_filter}')", conn)
                    pdf_bytes = create_pdf(client_filter, df, soap_df)
                    st.download_button("Download PDF Report", pdf_bytes, f"{client_filter}_Report.pdf", "application/pdf")
            else:
                st.info("No data matches these filters.")

    # --- GOAL MANAGEMENT (Add/Delete Template Goals) ---
    elif menu == "Goal Management":
        st.header("🎯 Goal Templates")
        
        goals_df = pd.read_sql("SELECT * FROM goals", conn)
        st.dataframe(goals_df, use_container_width=True)
        
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
        st.subheader("Delete Existing Goal")
        if not goals_df.empty:
            goal_to_delete = st.selectbox("Select Goal to Delete", goals_df['description'], key="delete_goal_select")
            if st.button("Delete Selected Goal"):
                conn.execute("DELETE FROM goals WHERE description=?", (goal_to_delete,))
                conn.commit()
                st.warning(f"Goal '{goal_to_delete}' deleted.")
                st.rerun()

    conn.close()

# --- RUN ---
if st.session_state.logged_in:
    main_app()
else:
    login_page()