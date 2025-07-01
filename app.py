# QuantumTrust DB Integration + QR Code Generator + QR Retrieval API + Web Dashboard
# Uses SQLite, Fernet encryption for QR payloads, and Bootstrap‑like themed HTML pages.
# Install requirements: pip install qrcode[pil] flask opencv-python cryptography

import os, io, base64, datetime, sqlite3, cv2
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
import qrcode

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-key")

# -------------------- Paths --------------------
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DB_PATH = os.path.join(app.root_path, 'quantumtrust.db')
KEY_FILE = os.path.join(app.root_path, 'fernet.key')

# -------------------- Encryption --------------------

def load_or_create_fernet():
    # Load existing encryption key or create a new one
    if os.path.exists(KEY_FILE):
        key = open(KEY_FILE, 'rb').read()
    else:
        key = Fernet.generate_key()
        open(KEY_FILE, 'wb').write(key)
    return Fernet(key)

# Load Fernet instance
fernet = load_or_create_fernet()

def pqc_encrypt(data: str) -> str:
    # Encrypt the data and return base64-encoded string
    return base64.urlsafe_b64encode(fernet.encrypt(data.encode())).decode()

def pqc_decrypt(token: str) -> str:
    # Decode base64 and decrypt the token
    return fernet.decrypt(base64.urlsafe_b64decode(token)).decode()

# -------------------- Database --------------------

def init_db():
    # Initialize SQLite database with users table
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        phone NUMERIC NOT NULL,
                        device_id TEXT,
                        payment_method TEXT,
                        upi_id TEXT,
                        loyalty_id TEXT,
                        last_login TEXT,
                        qr_code BLOB)
                  ''')
        conn.commit()

# -------------------- Helpers --------------------

def generate_qr_bytes(payload: str) -> bytes:
    # Generate QR code image in PNG format and return bytes
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------- Core Routes --------------------

@app.route('/')
def home():
    return render_template('home.html')

# -------- USER REGISTRATION (HTML form -> QR) --------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        return _process_registration()
    return render_template('register.html')

# Support legacy form action="/register_user"
@app.route('/register_user', methods=['POST'])
def register_user():
    return _process_registration()

def _process_registration():
    """Common logic for both /register and /register_user POST."""
    # Extract user data from form
    name  = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    payment_method = request.form.get('payment_method')
    upi_id = request.form.get('upi_id')
    loyalty_id = request.form.get('loyalty_id')
    timestamp = datetime.datetime.now().astimezone().isoformat()
    session_id = os.urandom(6).hex()

    # --- build payload & encrypt ---
    payload = f"{email}|{loyalty_id}|{timestamp}|{session_id}"
    encrypted_payload = pqc_encrypt(payload)
    qr_png = generate_qr_bytes(encrypted_payload)

    # --- store user in DB (QR as blob) ---
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO users
                     (name,email,phone,payment_method,upi_id,loyalty_id,last_login,qr_code)
                     VALUES (?,?,?,?,?,?,?,?)''',
                  (name,email,phone,payment_method,upi_id,loyalty_id,timestamp,qr_png))
        conn.commit()

    # Redirect to QR display page with encrypted token
    return redirect(url_for('show_qr', data=encrypted_payload))

# -------- SHOW & DOWNLOAD QR --------
@app.route('/show_qr')
def show_qr():
    token = request.args.get('data')
    if not token:
        return "No QR data", 400
    try:
        decoded = pqc_decrypt(token)
        email = decoded.split('|')[0]
    except Exception:
        return "Invalid QR data", 400
    # Fetch QR code from DB and encode as base64 for HTML rendering
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT qr_code FROM users WHERE email=?', (email,))
        row = c.fetchone()
    qr_data_b64 = base64.b64encode(row[0]).decode() if row else None
    return render_template('show_qr.html', qr_data=qr_data_b64, token=decoded)

@app.route('/download_qr/<email>')
def download_qr(email):
    # Fetch and send QR code as downloadable PNG
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT qr_code FROM users WHERE email=?', (email,))
        row = c.fetchone()
    if not row:
        return 'QR not found', 404
    return send_file(io.BytesIO(row[0]), mimetype='image/png', as_attachment=True, download_name=f'{email}_qr.png')

# -------- UPLOAD & SCAN QR --------
@app.route('/upload_qr', methods=['GET', 'POST'])
def upload_qr():
    user = error = None
    if request.method == 'POST':
        file = request.files.get('qrfile')
        if file and file.filename and allowed_file(file.filename):
            path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(path)
            img = cv2.imread(path)
            data, *_ = cv2.QRCodeDetector().detectAndDecode(img)
            if data:
                try:
                    decoded = pqc_decrypt(data)
                    email = decoded.split('|')[0]
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute('SELECT name,email,phone,last_login FROM users WHERE email=?', (email,))
                        user = c.fetchone()
                    if not user:
                        error = 'User not found in DB.'
                except Exception:
                    error = 'Invalid or corrupted QR code.'
            else:
                error = 'Could not decode QR.'
        else:
            error = 'Invalid file type.'
    return render_template('upload_qr.html', user=user, error=error)

# -------- DEVELOPER & DASHBOARD --------
@app.route('/dev_login', methods=['GET', 'POST'])
def dev_login():
    if request.method == 'POST':
        if request.form.get('password') == 'admin123':
            session['developer'] = True
            return redirect(url_for('dashboard'))
        return 'Invalid Password', 401
    return render_template('dev_login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('developer'):
        return redirect(url_for('home'))
    # Fetch all user records for admin dashboard
    with sqlite3.connect(DB_PATH) as conn:
        users = conn.execute('SELECT id,name,email,phone,last_login FROM users').fetchall()
    return render_template('dashboard.html', users=users)

@app.route('/logout')
def logout():
    # Clear developer session and return home
    session.pop('developer', None)
    return redirect(url_for('home'))

# -------------------- Main --------------------
if __name__ == '__main__':
    init_db()  # Ensure database and tables exist
    app.run(debug=True, port=8080)  # Start Flask app
