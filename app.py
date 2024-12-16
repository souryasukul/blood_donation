from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database initialization
DB_PATH = 'database/blood_donation.db'

def init_db():
    if not os.path.exists('database'):
        os.makedirs('database')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'customer'))
        )
    ''')

    # Create Appointments Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            hospital TEXT,
            date TEXT,
            time TEXT,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # Create Inventory Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blood_type TEXT NOT NULL,
            quantity INTEGER NOT NULL
        )
    ''')

    conn.commit()
    conn.close()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/add_inventory', methods=['POST'])
def add_inventory():
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied. Please log in as an admin.", "danger")
        return redirect(url_for('login'))

    blood_type = request.form['blood_type']
    quantity = int(request.form['quantity'])

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if the blood type already exists in the inventory
    cursor.execute('SELECT id FROM inventory WHERE blood_type = ?', (blood_type,))
    row = cursor.fetchone()

    if row:
        # If exists, update the quantity
        cursor.execute('UPDATE inventory SET quantity = quantity + ? WHERE id = ?', (quantity, row[0]))
    else:
        # If not, insert a new record
        cursor.execute('INSERT INTO inventory (blood_type, quantity) VALUES (?, ?)', (blood_type, quantity))

    conn.commit()
    conn.close()

    flash(f"Inventory updated: {quantity} units of {blood_type} added.", "success")
    return redirect(url_for('admin_home'))


# User Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                           (username, password, role))
            conn.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists. Please choose a different one.", "danger")
        finally:
            conn.close()
    return render_template('register.html')

# User Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            flash(f"Welcome, {user[1]}!", "success")
            if user[3] == 'admin':
                return redirect(url_for('admin_home'))
            else:
                return redirect(url_for('customer_home'))
        else:
            flash("Invalid credentials. Please try again.", "danger")
    return render_template('login.html')

# User Logout
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))

# Customer Home
@app.route('/customer')
def customer_home():
    if 'role' not in session or session['role'] != 'customer':
        flash("Access denied. Please log in as a customer.", "danger")
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM appointments WHERE user_id = ?', (session['user_id'],))
    appointments = cursor.fetchall()
    conn.close()
    return render_template('customer_home.html', appointments=appointments)

# Admin Home
@app.route('/admin', methods=['GET', 'POST'])
def admin_home():
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied. Please log in as an admin.", "danger")
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Fetch pending appointments
    cursor.execute('''
        SELECT appointments.id, users.username, users.role, appointments.hospital, appointments.date, appointments.time, appointments.status
        FROM appointments
        INNER JOIN users ON appointments.user_id = users.id
        WHERE appointments.status = "Pending"
    ''')
    pending_appointments = cursor.fetchall()

    # Fetch confirmed appointments
    cursor.execute('''
        SELECT appointments.id, users.username, appointments.hospital, appointments.date, appointments.time, appointments.status
        FROM appointments
        INNER JOIN users ON appointments.user_id = users.id
        WHERE appointments.status = "Confirmed"
    ''')
    confirmed_appointments = cursor.fetchall()

    # Fetch all blood inventory
    cursor.execute('SELECT * FROM inventory')
    blood_inventory = cursor.fetchall()

    conn.close()

    return render_template('admin_home.html', appointments=pending_appointments, inventory=blood_inventory)

@app.route('/accept_appointment/<int:appointment_id>', methods=['POST'])
def accept_appointment(appointment_id):
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied. Please log in as an admin.", "danger")
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Confirm the appointment
    cursor.execute('UPDATE appointments SET status = "Confirmed" WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()

    flash("Appointment accepted successfully!", "success")
    return redirect(url_for('admin_home'))

# Make Appointment
@app.route('/appointment', methods=['GET', 'POST'])
def make_appointment():
    if 'role' not in session or session['role'] != 'customer':
        flash("Access denied. Please log in as a customer.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        hospital = request.form['hospital']
        date = request.form['date']
        time = request.form['time']
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO appointments (user_id, hospital, date, time) VALUES (?, ?, ?, ?)',
                       (session['user_id'], hospital, date, time))
        conn.commit()
        conn.close()
        flash("Appointment created successfully!", "success")
        return redirect(url_for('customer_home'))

    # Default nearby hospitals
    default_hospitals = [
        {'name': 'Long Beach Memorial Medical Center', 'latitude': 33.8121, 'longitude': -118.1892},
        {'name': 'St. Mary Medical Center', 'latitude': 33.7853, 'longitude': -118.1897},
        {'name': 'Pacific Hospital of Long Beach', 'latitude': 33.7985, 'longitude': -118.2095}
    ]

    # Fetch hospitals using OpenCage API
    opencage_api_key = "YOUR_API_KEY"  # Replace with your OpenCage API key
    query = "Hospitals near Long Beach, CA"
    response = requests.get(f'https://api.opencagedata.com/geocode/v1/json?q={query}&key={opencage_api_key}')
    hospitals = []
    if response.status_code == 200:
        data = response.json()
        hospitals = [
            {
                'name': result['formatted'],
                'latitude': result['geometry']['lat'],
                'longitude': result['geometry']['lng']
            }
            for result in data['results'][:5]  # Limit to 5 hospitals
        ]

    # Combine fetched hospitals with default options (avoid duplicates)
    hospitals = hospitals or default_hospitals
    return render_template('appointment_form.html', hospitals=hospitals)

# Approve Appointment (Admin)
@app.route('/approve/<int:appointment_id>')
def approve_appointment(appointment_id):
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied. Please log in as an admin.", "danger")
        return redirect(url_for('login'))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE appointments SET status = "Approved" WHERE id = ?', (appointment_id,))
    conn.commit()
    conn.close()
    flash("Appointment approved successfully!", "success")
    return redirect(url_for('admin_home'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
