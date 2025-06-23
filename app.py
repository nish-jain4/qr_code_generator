# QuantumTrust DB Integration + QR Code Generator + QR Retrieval API + Web Dashboard
# Uses SQLite for simplicity (can be scaled to Firebase/PostgreSQL)
# Required packages: qrcode, pillow, flask

# Install using:
# pip install qrcode[pil] flask

import os
import datetime
import io
import sqlite3
import qrcode
import base64
from flask import Flask, send_file, request, jsonify, render_template, redirect, url_for, session
# from pyzbar.pyzbar import decode
import cv2
import numpy as np
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet  

app = Flask(__name__)
app.secret_key = "super-secret-key"
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Generate or load a Fernet key for QR code encryption
fernet_key = Fernet.generate_key()  # For production, save and reuse securely
fernet = Fernet(fernet_key)

# Simulated PQC encryption (replace with liboqs for production)
def pqc_encrypt(data: str) -> str:
    encrypted = fernet.encrypt(data.encode())
    return base64.urlsafe_b64encode(encrypted).decode()

def pqc_decrypt(encoded: str) -> str:
    encrypted = base64.urlsafe_b64decode(encoded.encode())
    return fernet.decrypt(encrypted).decode()

# --- Database Setup ---
DATABASE = "quantumtrust.db"
def init_db():
    conn = sqlite3.connect("quantumtrust.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            device_id TEXT,
            last_login TEXT,
            qr_code BLOB
        )
    ''')
    conn.commit()
    conn.close()

# --- Add User to DB and Generate QR ---
def add_user_and_generate_qr(name, email, device_id):
    session_id = os.urandom(6).hex()
    timestamp = datetime.datetime.now().astimezone().isoformat()
    payload = f"{email}|{device_id}|{timestamp}|{session_id}"
    encrypted_payload = pqc_encrypt(payload)

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(encrypted_payload)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    

    # Save QR image to in-memory buffer
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    qr_bytes = buffer.getvalue()

    # Save user to DB
    conn = sqlite3.connect("quantumtrust.db")
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (name, email, device_id, last_login, qr_code)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, email, device_id, timestamp, qr_bytes))
    conn.commit()
    conn.close()

    print(f"✅ User '{name}' added and QR code stored in database.")
    return encrypted_payload

# --- Fetch All Users ---
def fetch_all_users():
    conn = sqlite3.connect("quantumtrust.db")
    c = conn.cursor()
    c.execute("SELECT id, name, email, device_id, last_login FROM users")
    rows = c.fetchall()
    conn.close()
    return rows

# --- API: Get QR Image by Email ---
def get_user_by_email(email):
    conn = sqlite3.connect("quantumtrust.db")
    c = conn.cursor()
    c.execute("SELECT name, email, device_id, last_login FROM users WHERE email=?", (email,))
    result = c.fetchone()
    conn.close()
    return result


# --- Developer Login (Simple access control) ---
@app.route("/dev_login", methods=["GET", "POST"])
def dev_login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == "admin123":
            session["developer"] = True
            return redirect(url_for("dashboard"))
        return "Invalid Password"
    return render_template("dev_login.html")

@app.route("/get_qr", methods=["GET"])
def get_qr():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email parameter is required"}), 400

    conn = sqlite3.connect("quantumtrust.db")
    c = conn.cursor()
    c.execute("SELECT qr_code FROM users WHERE email=?", (email,))
    result = c.fetchone()
    conn.close()

    if result and result[0]:
        return send_file(io.BytesIO(result[0]), mimetype="image/png")
    else:
        return jsonify({"error": "QR code not found for email"}), 404

# --- API: Add New User ---
@app.route("/add_user", methods=["POST"])
def api_add_user():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    device_id = data.get("device_id")

    if not name or not email or not device_id:
        return jsonify({"error": "Missing required fields"}), 400

    encrypted = add_user_and_generate_qr(name, email, device_id)
    return jsonify({"message": "User added", "encrypted_payload": encrypted})

# --- API: Get All Users ---
@app.route("/users", methods=["GET"])
def api_users():
    users = fetch_all_users()
    return jsonify(users)

# --- Web Dashboard: Display Users ---
@app.route("/dashboard")
def dashboard():
    users = fetch_all_users()
    return render_template("dashboard.html", users=users)

# --- Web Form: Register and Show QR ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        device_id = request.form.get("device_id")
        encrypted = add_user_and_generate_qr(name, email, device_id)
        return redirect(url_for("show_qr", data=encrypted))

    return render_template("register.html")

# --- Show QR and link to view details ---
@app.route("/show_qr")
def show_qr():
    data = request.args.get("data")
    try:
        if data is None:
            raise ValueError("No data provided")
        decoded = pqc_decrypt(data)
        email = decoded.split("|")[0]
    except:
        email = ""
    return render_template("show_qr.html", data=data, email=email)
   
# --- Upload QR and Fetch Details ---
@app.route("/upload_qr", methods=["GET", "POST"])
def upload_qr():
    if request.method == "POST":
        file = request.files['qrfile']
        if file:
            filename = secure_filename(file.filename if file.filename else "uploaded_qr.png")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            img = cv2.imread(filepath)
            detector = cv2.QRCodeDetector()
            data, _, _ = detector.detectAndDecode(img)

            if data:
                return redirect(url_for("scan", data=data))
            else:
                return "Could not decode QR code."

    return render_template("upload_qr.html")



# --- Scan QR and fetch user info ---
@app.route("/scan")
def scan():
    encrypted = request.args.get("data")
    if not encrypted:
        return "No data provided."
    try:
        decoded = pqc_decrypt(encrypted)
        email = decoded.split("|")[0]
        user = get_user_by_email(email)
        if user:
            return f"""
                <h2>User Details</h2>
                Name: {user[0]}<br>
                Email: {user[1]}<br>
                Device ID: {user[2]}<br>
                Last Login: {user[3]}<br>
            """
        else:
            return "User not found"
    except:
        return "Invalid QR or decryption failed."
    
# --- Homepage Route: Choose Role ---
@app.route("/")
def home():
    return render_template("home.html")

# --- Main Runner ---
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=8080)
