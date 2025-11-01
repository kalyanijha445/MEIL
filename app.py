from flask import send_from_directory
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
import werkzeug.utils
from werkzeug.utils import secure_filename
import google.generativeai as genai
import json
import re 
import uuid 
import cv2  
import threading 
import time 

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_more_secure_default_secret_key") 
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


GEMINI_API_KEY = "AIzaSyCXlI8LJOlHI9pUyqeJKEVdaZEgjh2OUVc"


try:
    genai.configure(api_key=GEMINI_API_KEY)
    genai_configured = True
    print("Gemini API configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini API: {e}")
    genai_configured = False


DB_FILE = "database.db"

VIDEOS_DB_FILE = os.path.join(UPLOAD_FOLDER, 'videos.json')

CAMERA_STREAM_URL = 'http://10.89.155.174 :8080/video' 
camera_cap = None
camera_lock = threading.Lock()

def open_camera_capture():
    global camera_cap
    with camera_lock:
        if camera_cap is None or not camera_cap.isOpened():
            camera_cap = cv2.VideoCapture(CAMERA_STREAM_URL)
            if not camera_cap.isOpened():
                print(f"Error: Could not open camera stream at {CAMERA_STREAM_URL}")
                camera_cap = None

def generate_video_frames():
    open_camera_capture()
    time.sleep(1) 
    while True:
        frame = None
        with camera_lock:
            if camera_cap:
                success, frame = camera_cap.read()
            else:
                
                open_camera_capture()
                time.sleep(2) 
                continue

        if not success or frame is None:
            time.sleep(0.5)
            continue
        
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            continue
        
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def get_videos_data():
    if not os.path.exists(VIDEOS_DB_FILE):
        return []
    with open(VIDEOS_DB_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_videos_data(data):
    with open(VIDEOS_DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

LANGUAGE_MAP = {
    "en": "English", "as": "Assamese", "bn": "Bengali", "brx": "Bodo", "doi": "Dogri",
    "gu": "Gujarati", "hi": "Hindi", "kn": "Kannada", "ks": "Kashmiri", "kok": "Konkani",
    "mai": "Maithili", "ml": "Malayalam", "mni": "Manipuri", "mr": "Marathi",
    "ne": "Nepali", "or": "Odia", "pa": "Punjabi", "sa": "Sanskrit", "sat": "Santali",
    "sd": "Sindhi", "ta": "Tamil", "te": "Telugu", "ur": "Urdu"
}


def init_db():
    """Initialize SQLite database and create tables with a new user schema."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        role TEXT NOT NULL,
                        name TEXT,
                        email TEXT,
                        project_code TEXT,
                        blood_group TEXT,
                        emergency_name TEXT,
                        emergency_relation TEXT,
                        emergency_mobile TEXT
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        submitted_by TEXT,
                        project_name TEXT,
                        subjects TEXT,
                        description TEXT,
                        location TEXT,
                        timestamp TEXT,
                        priority TEXT,
                        resolution_time TEXT,
                        suggestion TEXT,
                        image_paths TEXT,
                        report_type TEXT,
                        present_count INTEGER
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        submitted_by TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        location TEXT,
                        image_path TEXT NOT NULL,
                        present_count INTEGER NOT NULL,
                        attendees_data TEXT 
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS notices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        content TEXT,
                        date TEXT,
                        time TEXT,
                        location TEXT,
                        image_paths TEXT
                    )''')
    
    conn.commit()
    conn.close()

PROJECTS = [
    {"code": "P2024-ALPHA", "name": "Project Alpha - Skyscraper Construction"},
    {"code": "P2024-BETA", "name": "Project Beta - Bridge Development"},
    {"code": "P2024-GAMMA", "name": "Project Gamma - Tunnel Excavation"},
    {"code": "P2024-DELTA", "name": "Project Delta - Residential Complex"},
    {"code": "P2024-SIGMA", "name": "Project Sigma - Power Plant Maintenance"},
    {"code": "GENERAL", "name": "General / Not Project-Specific"}
]

ADMIN_PROJECTS = [
    {"code": "P2024-ALPHA", "name": "Skyscraper Construction", "icon": "bxs-building-house"},
    {"code": "P2024-BETA", "name": "Bridge Development", "icon": "bx-arch"},
    {"code": "P2024-GAMMA", "name": "Tunnel Excavation", "icon": "bx-unite"},
    {"code": "P2024-DELTA", "name": "Residential Complex", "icon": "bxs-home-heart"},
    {"code": "P2024-SIGMA", "name": "Power Plant Maintenance", "icon": "bxs-zap"},
    {"code": "P2025-EPSILON", "name": "Metro Rail Network", "icon": "bxs-train"},
    {"code": "P2025-ZETA", "name": "Airport Expansion", "icon": "bxs-plane-alt"},
    {"code": "P2025-ETA", "name": "Dam Construction", "icon": "bx-water"},
    {"code": "P2025-THETA", "name": "Industrial Park", "icon": "bxs-factory"},
    {"code": "P2026-IOTA", "name": "IT Hub Infrastructure", "icon": "bxs-server"},
    {"code": "P2026-KAPPA", "name": "Offshore Oil Rig", "icon": "bxs-cylinder"},
    {"code": "P2026-LAMBDA", "name": "Renewable Energy Farm", "icon": "bxs-sun"},
    {"code": "P2026-MU", "name": "National Highway Project", "icon": "bxs-traffic-cone"},
    {"code": "P2027-NU", "name": "Smart City Grid", "icon": "bxs-network-chart"},
    {"code": "P2027-XI", "name": "High-Speed Rail Line", "icon": "bx-move-horizontal"},
    {"code": "P2027-OMICRON", "name": "Coastal Defense System", "icon": "bxs-shield-alt-2"},
    {"code": "P2028-PI", "name": "Data Center Facility", "icon": "bxs-hdd"},
    {"code": "P2028-RHO", "name": "Waste Management Plant", "icon": "bxs-recycle"},
    {"code": "P2028-TAU", "name": "Public University Campus", "icon": "bxs-graduation"},
    {"code": "P2028-UPSILON", "name": "Space Research Center", "icon": "bxs-rocket"}
]

def verify_user(user_id, password, role):
    """Verify user against the database, including their selected role."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
   
    cursor.execute("SELECT role FROM users WHERE user_id=? AND password=? AND role=?", (user_id, password, role))
    user = cursor.fetchone()
    conn.close()
    return user[0] if user else None


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        role = request.form['role'] 
        
        verified_role = verify_user(user_id, password, role)

        if verified_role:
            session['user_id'] = user_id
            session['role'] = verified_role
            if verified_role == 'safety_officer':
                return redirect(url_for('SO_dashboard'))
            elif verified_role == 'manager':
        
                return redirect(url_for('SM_dashboard'))
            elif verified_role in ['admin', 'employee']:
                return redirect(url_for(f'{verified_role}_dashboard'))
            else:
                flash("Dashboard not available for your role.")
                return redirect(url_for('login'))
        else:
            flash("Invalid User ID, Password, or Role. Please try again.")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        
        user_id = request.form['user_id']
        password = request.form['password']
        role = request.form['role']
        name = request.form['name']
        email = request.form['email']
        project_code = request.form['project_code']
        blood_group = request.form['blood_group']
        emergency_name = request.form['emergency_name']
        emergency_relation = request.form['emergency_relation']
        emergency_mobile = request.form['emergency_mobile']

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

      
        cursor.execute("SELECT id FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            flash("User ID already exists. Please choose a different one.", "error")
            conn.close()
            return redirect(url_for('signup'))
            
        cursor.execute("""
            INSERT INTO users (user_id, password, role, name, email, project_code, blood_group, 
                               emergency_name, emergency_relation, emergency_mobile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, password, role, name, email, project_code, blood_group, 
              emergency_name, emergency_relation, emergency_mobile))
        
        conn.commit()
        conn.close()
        
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for('login'))


    return render_template('signup.html', projects=PROJECTS)


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been successfully logged out.")
    return redirect(url_for('login'))
    
@app.route('/get_user_info')
def get_user_info():
    """Fetches user information directly from the database."""
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_id = session.get('user_id')
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    conn.close()

    if not user_row:
        return jsonify({"error": "User not found"}), 404
    
    
    user_data = dict(user_row)
    project_code = user_data.get('project_code')
    project_name = "N/A"
    for p in PROJECTS:
        if p['code'] == project_code:
            project_name = p['name']
            break
    user_data['project_name'] = project_name

    return jsonify(user_data)

@app.route('/SO_dashboard')
def SO_dashboard():
    if 'role' not in session or session['role'] != 'safety_officer':
        flash("You are not authorized to view this page.")
        return redirect(url_for('login'))
    return render_template('SO_dashboard.html')

@app.route('/sos')
def sos_page():
    if 'user_id' not in session:
        flash("You must be logged in to access this page.")
        return redirect(url_for('login'))
    return render_template('SOS.html')

@app.route('/manager_dashboard')
def SM_dashboard(): 
    if 'role' not in session or session['role'] != 'manager':
        flash("You are not authorized to view this page.")
        return redirect(url_for('login'))
    return render_template('SM_dashboard.html')

@app.route('/admin_dashboard')
def admin_dashboard(): 
    if 'role' not in session or session['role'] != 'admin':
        flash("You are not authorized to view this page.")
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html', projects=ADMIN_PROJECTS)


@app.route('/employee_dashboard')
def employee_dashboard(): 
    if 'role' not in session or session['role'] != 'employee':
        flash("You are not authorized to view this page.")
        return redirect(url_for('login'))
    
  
    videos = get_videos_data()
    return render_template('employee.html', videos=videos)

@app.route('/track_reports')
def track_reports():
    if 'role' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM reports")
    reports_data = cursor.fetchall()
    
    cursor.execute("SELECT * FROM attendance_records")
    attendance_data = cursor.fetchall()

    cursor.execute("SELECT user_id, project_code FROM users")
    user_projects_rows = cursor.fetchall()
    user_project_map = {row['user_id']: row['project_code'] for row in user_projects_rows}
    project_name_map = {p['code']: p['name'] for p in PROJECTS}

    conn.close()
    
    
    all_records = []
    
    
    for row in reports_data:
        report_dict = dict(row)
        try:
            image_paths_json = report_dict.get('image_paths', '[]')
            report_dict['image_paths'] = json.loads(image_paths_json) if image_paths_json and image_paths_json.strip() else []
        except (json.JSONDecodeError, TypeError):
            report_dict['image_paths'] = []
        
        report_dict['subjects'] = report_dict['subjects'].split(',') if report_dict.get('subjects') else []
        all_records.append(report_dict)
    for row in attendance_data:
        record = dict(row)
        
        
        try:
            attendees_list = json.loads(record.get('attendees_data', '[]'))
            description_text = "\n".join([f"- {p.get('name', 'Unknown')} ({p.get('id', 'N/A')})" for p in attendees_list])
            if not description_text:
                description_text = "No attendees were listed in this record."
        except (json.JSONDecodeError, TypeError):
            description_text = "Could not parse attendee data."
            
        
        submitter_id = record.get('submitted_by')
        project_code = user_project_map.get(submitter_id)
        project_name = project_name_map.get(project_code, 'General / Not Project-Specific')

       
        attendance_as_report = {
            'id': f"ATT-{record['id']}", # Prefix ID to avoid potential numeric collision in JS
            'report_type': 'attendance',
            'submitted_by': record.get('submitted_by'),
            'project_name': project_name, # Use the looked-up name
            'timestamp': record.get('timestamp'),
            'location': record.get('location'),
            'present_count': record.get('present_count'), # Pass the count for the template
            'description': description_text,
            'image_paths': [record.get('image_path')] if record.get('image_path') else [], # Must be a list of paths
            # Add placeholder fields to prevent template errors
            'priority': 'Low',
            'subjects': ['Attendance Record'],
            'suggestion': '',
            'resolution_time': ''
        }
        all_records.append(attendance_as_report)

    # Sort the final combined list by timestamp in descending order (newest first)
    all_records.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    return render_template('track_reports.html', reports=all_records, projects=PROJECTS)


# MODIFICATION START: ADDED NEW ROUTES FOR MANAGER DASHBOARD REDIRECTION
@app.route('/attendance_mr')
def attendance_mr():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance_records ORDER BY id DESC")
    records_data = cursor.fetchall()
    conn.close()

    # Process records for display
    records = []
    for row in records_data:
        record_dict = dict(row)
        try:
            # Parse the JSON string from the DB into a Python list
            attendees_json = record_dict.get('attendees_data', '[]')
            record_dict['attendees_data'] = json.loads(attendees_json) if attendees_json else []
        except (json.JSONDecodeError, TypeError):
            record_dict['attendees_data'] = []
        records.append(record_dict)

    return render_template('attendance_mr.html', records=records)

@app.route('/training_mr', methods=['GET', 'POST'])
def training_mr():
    # Centralized session check for both GET and POST requests
    if 'user_id' not in session:
        if request.method == 'POST':
            # For AJAX requests, return a JSON error
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        # For browser requests, redirect to login
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Check if the post request has the file parts
        if 'videoFile' not in request.files or 'thumbnailFile' not in request.files:
            return jsonify({'status': 'error', 'message': 'File parts are missing'}), 400
        
        video_file = request.files['videoFile']
        thumbnail_file = request.files['thumbnailFile']
        title = request.form.get('title')
        description = request.form.get('description')

        if video_file.filename == '' or thumbnail_file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file'}), 400
            
        if video_file and thumbnail_file and title:
            # Generate unique filenames to prevent overwrites
            video_ext = os.path.splitext(secure_filename(video_file.filename))[1]
            thumb_ext = os.path.splitext(secure_filename(thumbnail_file.filename))[1]
            
            video_filename = str(uuid.uuid4()) + video_ext
            thumb_filename = str(uuid.uuid4()) + thumb_ext
            
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], thumb_filename)

            video_file.save(video_path)
            thumbnail_file.save(thumb_path)
            
            # Save metadata to JSON file
            videos = get_videos_data()
            new_video = {
                'id': str(uuid.uuid4()),
                'title': title,
                'description': description,
                'video_path': os.path.join('uploads', video_filename).replace("\\", "/"),
                'thumbnail_path': os.path.join('uploads', thumb_filename).replace("\\", "/")
            }
            videos.insert(0, new_video) # Add new video to the beginning
            save_videos_data(videos)
            
            return jsonify({'status': 'success', 'message': 'Video uploaded successfully!', 'video': new_video})
        else:
            return jsonify({'status': 'error', 'message': 'Missing data in form'}), 400


    # For GET request, load videos and render the page
    videos = get_videos_data()
    return render_template('training_mr.html', videos=videos)
    
# --- NEW ROUTE ADDED HERE ---
@app.route('/delete_video/<video_id>', methods=['POST'])
def delete_video(video_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        videos = get_videos_data()
        video_to_delete = None
        for video in videos:
            if video.get('id') == video_id:
                video_to_delete = video
                break
        
        if not video_to_delete:
            return jsonify({'status': 'error', 'message': 'Video not found'}), 404

        # 1. Delete the actual files from the server
        video_path = video_to_delete.get('video_path')
        thumb_path = video_to_delete.get('thumbnail_path')

        if video_path:
            # Construct the full file path safely
            full_video_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(video_path))
            try:
                os.remove(full_video_path)
            except FileNotFoundError:
                print(f"Warning: Video file not found for deletion: {full_video_path}")
        
        if thumb_path:
            full_thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(thumb_path))
            try:
                os.remove(full_thumb_path)
            except FileNotFoundError:
                print(f"Warning: Thumbnail file not found for deletion: {full_thumb_path}")
        
        # 2. Remove the video's record from the JSON data
        updated_videos = [v for v in videos if v.get('id') != video_id]
        save_videos_data(updated_videos)
        
        return jsonify({'status': 'success', 'message': 'Video deleted successfully'})

    except Exception as e:
        print(f"Error deleting video: {e}")
        return jsonify({'status': 'error', 'message': 'An internal error occurred'}), 500
# --- END OF NEW ROUTE ---

@app.route('/projects_mr')
def projects_mr():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('projects.html', projects=PROJECTS)

@app.route('/notices_mr')
def notices_mr():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notices ORDER BY id DESC")
    notices_data = cursor.fetchall()
    conn.close()

    notices = []
    for row in notices_data:
        notice_dict = dict(row)
        try:
            image_paths_json = notice_dict.get('image_paths', '[]')
            # The path stored is like 'uploads/image.jpg', perfect for url_for
            notice_dict['images'] = json.loads(image_paths_json) if image_paths_json else []
        except (json.JSONDecodeError, TypeError):
            notice_dict['images'] = []
        notices.append(notice_dict)
    
    return render_template('notices_mr.html', notices=notices)

# --- NEW ROUTE: ADD A NOTICE ---
@app.route('/add_notice_mr', methods=['POST'])
def add_notice_mr():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    try:
        title = request.form.get('title')
        content = request.form.get('content')
        date = request.form.get('date')
        time = request.form.get('time')
        location = request.form.get('location')
        images = request.files.getlist('images')

        if not title or not content:
            return jsonify({'status': 'error', 'message': 'Title and content are required'}), 400

        saved_image_paths = []
        for image in images:
            if image and image.filename != '':
                ext = os.path.splitext(secure_filename(image.filename))[1]
                filename = str(uuid.uuid4()) + ext
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(filepath)
                saved_image_paths.append(os.path.join('uploads', filename).replace("\\", "/"))

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notices (title, content, date, time, location, image_paths)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, content, date, time, location, json.dumps(saved_image_paths)))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Notice posted successfully!'})
    except Exception as e:
        print(f"Error adding notice: {e}")
        return jsonify({'status': 'error', 'message': 'An internal server error occurred'}), 500

# --- NEW ROUTE: DELETE A NOTICE ---
@app.route('/delete_notice_mr/<int:notice_id>', methods=['POST'])
def delete_notice_mr(notice_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT image_paths FROM notices WHERE id = ?", (notice_id,))
        result = cursor.fetchone()
        if result and result[0]:
            image_paths = json.loads(result[0])
            for path in image_paths:
                full_path = os.path.join('static', path)
                if os.path.exists(full_path):
                    os.remove(full_path)
        
        cursor.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'message': 'Notice deleted successfully!'})
    except Exception as e:
        print(f"Error deleting notice: {e}")
        return jsonify({'status': 'error', 'message': 'An internal server error occurred'}), 500


# --- MODIFICATION START: UPDATED ADMIN ROUTE TO FIX REDIRECTION ---
@app.route('/track_reports_ad')
def track_reports_ad():
    if 'role' not in session or session['role'] != 'admin':
        flash("You are not authorized to view this page.")
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    # Fetch all regular safety reports
    cursor.execute("SELECT * FROM reports")
    reports_data = cursor.fetchall()
    
    # Fetch all attendance records
    cursor.execute("SELECT * FROM attendance_records")
    attendance_data = cursor.fetchall()

    # Create maps to efficiently get user's project name for attendance records
    cursor.execute("SELECT user_id, project_code FROM users")
    user_projects_rows = cursor.fetchall()
    user_project_map = {row['user_id']: row['project_code'] for row in user_projects_rows}
    project_name_map = {p['code']: p['name'] for p in PROJECTS}

    conn.close()
    
    all_records = []
    
    # Process regular reports
    for row in reports_data:
        report_dict = dict(row)
        try:
            image_paths_json = report_dict.get('image_paths', '[]')
            report_dict['image_paths'] = json.loads(image_paths_json) if image_paths_json and image_paths_json.strip() else []
        except (json.JSONDecodeError, TypeError):
            report_dict['image_paths'] = []
        report_dict['subjects'] = report_dict['subjects'].split(',') if report_dict.get('subjects') else []
        all_records.append(report_dict)

    # Process attendance records and transform them
    for row in attendance_data:
        record = dict(row)
        try:
            attendees_list = json.loads(record.get('attendees_data', '[]'))
            description_text = "\n".join([f"- {p.get('name', 'Unknown')} ({p.get('id', 'N/A')})" for p in attendees_list])
            if not description_text:
                description_text = "No attendees were listed in this record."
        except (json.JSONDecodeError, TypeError):
            description_text = "Could not parse attendee data."
            
        submitter_id = record.get('submitted_by')
        project_code = user_project_map.get(submitter_id)
        project_name = project_name_map.get(project_code, 'General / Not Project-Specific')

        attendance_as_report = {
            'id': f"ATT-{record['id']}", 
            'report_type': 'attendance',
            'submitted_by': record.get('submitted_by'),
            'project_name': project_name,
            'timestamp': record.get('timestamp'),
            'location': record.get('location'),
            'present_count': record.get('present_count'), 
            'description': description_text,
            'image_paths': [record.get('image_path')] if record.get('image_path') else [], 
            'priority': 'Low',
            'subjects': ['Attendance Record'],
            'suggestion': '',
            'resolution_time': ''
        }
        all_records.append(attendance_as_report)

    # Sort all records by timestamp (newest first)
    all_records.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Render the correct template with all the fetched data
    return render_template('track_reports_ad.html', reports=all_records, projects=PROJECTS)
# --- MODIFICATION END ---

@app.route('/sw.js')
def sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/live_view')
def live_view():
    if 'role' not in session or session['role'] != 'admin':
        flash("You are not authorized to view this page.")
        return redirect(url_for('login'))
 
    return render_template('live_view.html')

# --- NEW ROUTE FOR VIDEO STREAMING ---
@app.route('/video_feed')
def video_feed():
    if 'role' not in session or session['role'] != 'admin':
        return "Unauthorized", 401
    return Response(generate_video_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
# --- END NEW ROUTE ---


@app.route('/notices_ad')
def notices_ad():
    if 'role' not in session or session['role'] != 'admin':
        flash("You are not authorized to view this page.")
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Fetch all notices, newest first
    cursor.execute("SELECT * FROM notices ORDER BY id DESC")
    notices_data = cursor.fetchall()
    conn.close()

    notices = []
    for row in notices_data:
        notice_dict = dict(row)
        try:
            # Convert image_paths JSON string from DB into a list
            image_paths_json = notice_dict.get('image_paths', '[]')
            notice_dict['images'] = json.loads(image_paths_json) if image_paths_json else []
        except (json.JSONDecodeError, TypeError):
            notice_dict['images'] = []
        notices.append(notice_dict)
    
    # Render the new admin-specific notices template
    return render_template('notices_ad.html', notices=notices)


@app.route('/track_reports_mr')
def track_reports_mr():
    if 'role' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    # 1. Fetch all regular safety reports
    cursor.execute("SELECT * FROM reports")
    reports_data = cursor.fetchall()
    
    # 2. Fetch all attendance records
    cursor.execute("SELECT * FROM attendance_records")
    attendance_data = cursor.fetchall()

    # 3. Create maps to efficiently get user's project name for attendance records
    cursor.execute("SELECT user_id, project_code FROM users")
    user_projects_rows = cursor.fetchall()
    user_project_map = {row['user_id']: row['project_code'] for row in user_projects_rows}
    project_name_map = {p['code']: p['name'] for p in PROJECTS}

    conn.close()
    
    # This list will hold both types of records in a unified format
    all_records = []
    
    # Process regular reports first
    for row in reports_data:
        report_dict = dict(row)
        try:
            image_paths_json = report_dict.get('image_paths', '[]')
            report_dict['image_paths'] = json.loads(image_paths_json) if image_paths_json and image_paths_json.strip() else []
        except (json.JSONDecodeError, TypeError):
            report_dict['image_paths'] = []
        
        report_dict['subjects'] = report_dict['subjects'].split(',') if report_dict.get('subjects') else []
        all_records.append(report_dict)

    # Process attendance records and transform them to match the 'report' structure
    for row in attendance_data:
        record = dict(row)
        
        # A. Format the attendees list from JSON for the 'description' field
        try:
            attendees_list = json.loads(record.get('attendees_data', '[]'))
            description_text = "\n".join([f"- {p.get('name', 'Unknown')} ({p.get('id', 'N/A')})" for p in attendees_list])
            if not description_text:
                description_text = "No attendees were listed in this record."
        except (json.JSONDecodeError, TypeError):
            description_text = "Could not parse attendee data."
            
        # B. Look up the project name for the submitter
        submitter_id = record.get('submitted_by')
        project_code = user_project_map.get(submitter_id)
        project_name = project_name_map.get(project_code, 'General / Not Project-Specific')

        # C. Create a new dictionary that mimics the structure expected by the template
        attendance_as_report = {
            'id': f"ATT-{record['id']}", 
            'report_type': 'attendance',
            'submitted_by': record.get('submitted_by'),
            'project_name': project_name,
            'timestamp': record.get('timestamp'),
            'location': record.get('location'),
            'present_count': record.get('present_count'), 
            'description': description_text,
            'image_paths': [record.get('image_path')] if record.get('image_path') else [], 
            'priority': 'Low',
            'subjects': ['Attendance Record'],
            'suggestion': '',
            'resolution_time': ''
        }
        all_records.append(attendance_as_report)

    # Sort the final combined list by timestamp in descending order (newest first)
    all_records.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return render_template('track_reports_mr.html', reports=all_records, projects=PROJECTS)
# MODIFICATION END


# MODIFICATION START: Updated attendance route to fetch past AI records
@app.route('/attendance')
def attendance(): 
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance_records ORDER BY id DESC")
    records_data = cursor.fetchall()
    conn.close()

    # Process records for display
    records = []
    for row in records_data:
        record_dict = dict(row)
        try:
            # Parse the JSON string from the DB into a Python list
            attendees_json = record_dict.get('attendees_data', '[]')
            record_dict['attendees_data'] = json.loads(attendees_json) if attendees_json else []
        except (json.JSONDecodeError, TypeError):
            record_dict['attendees_data'] = []
        records.append(record_dict)

    return render_template('attendance.html', records=records)
# MODIFICATION END

# MODIFICATION: I have ADDED the missing /training route below
@app.route('/training')
def training():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    videos = get_videos_data()
    # The user requested to render training.html
    return render_template('training.html', videos=videos)

# MODIFICATION START: Corrected /notices route to fetch data
@app.route('/notices')
def notices():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # This logic was missing. It fetches notices for the template.
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notices ORDER BY id DESC")
    notices_data = cursor.fetchall()
    conn.close()

    notices = []
    for row in notices_data:
        notice_dict = dict(row)
        try:
            image_paths_json = notice_dict.get('image_paths', '[]')
            notice_dict['images'] = json.loads(image_paths_json) if image_paths_json else []
        except (json.JSONDecodeError, TypeError):
            notice_dict['images'] = []
        notices.append(notice_dict)

    # Now we pass the fetched notices to the template
    return render_template('notices.html', notices=notices)
# MODIFICATION END

@app.route('/get_projects')
def get_projects():
    return jsonify(PROJECTS)

@app.route('/analyze_new', methods=['POST'])
def analyze_new():
    if not genai_configured:
         return jsonify({"error": "Server is not configured with a valid API key."}), 500

    images = request.files.getlist('images')
    user_description = request.form.get('description', '')
    project = request.form.get('project', 'N/A')
    subjects = request.form.get('subjects', 'N/A')
    # MODIFICATION START: Get selected language
    selected_language = request.form.get("selected_language", "en").strip()
    language_name = LANGUAGE_MAP.get(selected_language, "English")
    # MODIFICATION END

    image_parts = []
    saved_filenames = []
    for image in images:
        if image and image.filename != '':
            filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{image.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(filepath)
            saved_filenames.append(f"/static/uploads/{filename}")
            with open(filepath, 'rb') as f:
                image_parts.append({ 'mime_type': image.mimetype, 'data': f.read() })

    if not user_description and not image_parts:
        return jsonify({"error": "No description or valid images provided"}), 400
    
    # MODIFICATION START: Updated prompt for multilingual support
    prompt = f"""
    You are an expert construction safety compliance AI. Your task is to analyze the user's report and generate a structured safety assessment.
    
    IMPORTANT: The analysis part of your response (the explanatory text for 'Description' and 'Suggestion') MUST be written in the '{language_name}' language. However, the keywords 'Description:', 'Priority:', 'Resolution:', and 'Suggestion:' MUST remain in English for parsing.
    
    **USER'S REPORT CONTEXT:**
    - Project: {project}
    - Subjects of Report: {subjects}
    - User's Description: "{user_description}"
    - Attached Images: [Analyze the provided images for safety hazards]
    
    **YOUR TASK:**
    Based on all the provided information (text and images), generate a report with the following fields. Do not add any extra text or intro/outro. Only provide the fields as requested below.
    Description: [Provide a detailed, professional description of the safety issue(s) you observe IN {language_name}.]
    Priority: [Assign a priority level: Low, Medium, High, or Critical.]
    Resolution: [Estimate a realistic resolution time in the format 'X days, Y hours'. Be specific.]
    Suggestion: [Provide clear, actionable, and concise recommendations to mitigate the identified risks IN {language_name}.]
    """
    # MODIFICATION END
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp") 
        response = model.generate_content([prompt] + image_parts)
        ai_text = response.text
        
        parsed_data = {}
        lines = ai_text.strip().split('\n')
        for line in lines:
            if ":" in line:
                key, value = line.split(":", 1)
                key_clean = key.strip().lower().replace(" ", "_")
                parsed_data[key_clean] = value.strip()

        ai_response = {
            "description": parsed_data.get("description", "AI analysis could not determine a description."),
            "priority": parsed_data.get("priority", "Medium"),
            "resolution_time": parsed_data.get("resolution", "Not estimated"),
            "suggestion": parsed_data.get("suggestion", "No specific suggestion generated."),
            "image_paths": saved_filenames
        }
        return jsonify(ai_response)

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return jsonify({"error": f"AI analysis failed: {str(e)}"}), 500

# MODIFICATION START: Added AI route for attendance
@app.route('/analyze_attendance', methods=['POST'])
def analyze_attendance():
    if not genai_configured:
         return jsonify({"success": False, "error": "AI Server not configured."}), 500
    
    image = request.files.get('image')
    if not image or image.filename == '':
        return jsonify({"success": False, "error": "No image provided"}), 400

    # Save the image
    filename = secure_filename(f"attendance_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.jpg")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image.save(filepath)
    saved_filepath = f"/static/uploads/{filename}"

    # Prepare image for AI
    with open(filepath, 'rb') as f:
        image_parts = [{'mime_type': image.mimetype, 'data': f.read()}]

    prompt = """
    You are an advanced AI attendance system for MEIL construction company. Your task is to identify employees from the provided image.
    Based on a hypothetical internal employee database, you must match the faces to employee names and their unique User IDs.

    **Your Response MUST follow this strict format for each person identified:**
    Name: [Employee Name], ID: [Employee User ID]

    - Each person should be on a new line.
    - DO NOT include any introductory text, summary, headers, or any other text.
    - If a person's face is unclear or cannot be identified, return: "Name: Unknown, ID: N/A".
    - Provide a response for every person visible in the image.

    Example Response:
    Name: John Doe, ID: EMP20250142
    Name: Jane Smith, ID: EMP20170178
    Name: Unknown, ID: N/A
    """
    
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp") 
        response = model.generate_content([prompt] + image_parts)
        
        attendees = []
        # Use regex to robustly parse the "Name: ..., ID: ..." format
        matches = re.findall(r"Name:\s*(.*?),\s*ID:\s*(.*)", response.text)
        for match in matches:
            name = match[0].strip()
            user_id = match[1].strip()
            if name: # Only add if name is found
                attendees.append({"name": name, "id": user_id})

        if not attendees and "Unknown" not in response.text:
             # Handle cases where the AI gives a conversational response instead of data
            return jsonify({"success": False, "error": "AI did not return identifiable data. Please try a clearer photo."})

        return jsonify({
            "success": True, 
            "count": len(attendees),
            "attendees": attendees,
            "image_path": saved_filepath
        })

    except Exception as e:
        print(f"Error in /analyze_attendance: {e}")
        return jsonify({"success": False, "error": f"AI analysis failed: {str(e)}"}), 500
# MODIFICATION END
        
@app.route('/submit_report', methods=['POST'])
def submit_report():
    data = request.json
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reports (
            submitted_by, project_name, subjects, description, location, 
            timestamp, priority, resolution_time, suggestion, image_paths, report_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session.get('user_id', 'Unknown'),
        data.get('project'),
        ",".join(data.get('subjects', [])),
        data.get('description'),
        data.get('location'),
        data.get('timestamp'),
        data.get('priority'),
        data.get('resolution_time'),
        data.get('suggestion'),
        json.dumps(data.get('image_paths', [])),
        data.get('report_type')
    ))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Report submitted successfully!"})
    
# MODIFICATION START: Added route for submitting attendance records
@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    data = request.json
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO attendance_records (submitted_by, timestamp, location, image_path, present_count, attendees_data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session['user_id'],
            data.get('timestamp'),
            data.get('location'),
            data.get('image_path'),
            data.get('count'),
            json.dumps(data.get('attendees', [])) # Convert list to JSON string
        ))
        conn.commit()
        return jsonify({"success": True, "message": "Attendance Recorded Successfully!"})
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"success": False, "error": f"Database error: {e}"}), 500
    finally:
        conn.close()
# MODIFICATION END

@app.route('/update_report/<int:report_id>', methods=['POST'])
def update_report(report_id):
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE reports 
            SET project_name = ?, subjects = ?, description = ?, location = ?, 
                timestamp = ?, priority = ?, resolution_time = ?, suggestion = ?, report_type = ?
            WHERE id = ?
        """, (
            data.get('project'),
            ",".join(data.get('subjects', [])),
            data.get('description'),
            data.get('location'),
            data.get('timestamp'),
            data.get('priority'),
            data.get('resolution_time'),
            data.get('suggestion'),
            data.get('report_type'),
            report_id
        ))
        conn.commit()
        return jsonify({"success": True, "message": "Report updated successfully!"})
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"success": False, "error": f"Database error: {e}"}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    init_db() 
    app.run(debug=True)
