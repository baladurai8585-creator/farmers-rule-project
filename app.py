import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os

# --- App and Database Setup ---

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_change_this'
DATABASE = 'farmers_market.db'

# Vegetable List with Categories
VEGETABLES = {
    'Fruiting Vegetables': [{'name': 'Tomato'}, {'name': 'Brinjal'}, {'name': 'Capsicum'}, {'name': 'Chilli'}],
    'Root Vegetables': [{'name': 'Potato'}, {'name': 'Onion'}, {'name': 'Carrot'}, {'name': 'Beetroot'}],
    'Leafy Greens': [{'name': 'Spinach'}, {'name': 'Coriander'}, {'name': 'Mint'}]
}

# --- Database Helper Functions ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE); conn.row_factory = sqlite3.Row; return conn

def create_tables():
    conn = get_db_connection()
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, place TEXT NOT NULL, dob TEXT NOT NULL, mobile_number TEXT UNIQUE NOT NULL, password TEXT NOT NULL, user_type TEXT NOT NULL, latitude REAL, longitude REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS listings (id INTEGER PRIMARY KEY AUTOINCREMENT, farmer_id INTEGER NOT NULL, vegetable_name TEXT NOT NULL, quantity_kg REAL NOT NULL, rate_per_kg REAL NOT NULL, is_sold INTEGER DEFAULT 0, FOREIGN KEY (farmer_id) REFERENCES users (id))')
    conn.commit(); conn.close()

# --- User Authentication and Welcome Routes ---
@app.route('/')
def index(): return redirect(url_for('welcome'))

@app.route('/welcome')
def welcome():
    if 'user_id' in session: return redirect(url_for('market'))
    return render_template('welcome.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_type = request.form['user_type']; name = request.form['name']; place = request.form['place']; dob = request.form['dob']; mobile_number = request.form['mobile_number']; password = request.form['password']
        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (user_type, name, place, dob, mobile_number, password) VALUES (?, ?, ?, ?, ?, ?)',(user_type, name, place, dob, mobile_number, hashed_password))
            conn.commit(); flash('Registration successful! Please login.', 'success'); return redirect(url_for('login'))
        except sqlite3.IntegrityError: flash('This mobile number is already registered.', 'error')
        finally: conn.close()
    return render_template('register_user.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile_number = request.form['mobile_number']; password = request.form['password']
        conn = get_db_connection(); user = conn.execute('SELECT * FROM users WHERE mobile_number = ?', (mobile_number,)).fetchone(); conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']; session['user_name'] = user['name']; session['user_type'] = user['user_type']
            flash(f"Welcome back, {user['name']}!", 'success'); return redirect(url_for('market'))
        else: flash('Invalid mobile number or password. Please try again.', 'error'); return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('You have been logged out successfully.', 'success'); return redirect(url_for('welcome'))

# --- Password Reset Routes ---
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        mobile_number = request.form['mobile_number']; dob = request.form['dob']
        conn = get_db_connection(); user = conn.execute('SELECT * FROM users WHERE mobile_number = ? AND dob = ?', (mobile_number, dob)).fetchone(); conn.close()
        if user: session['reset_user_id'] = user['id']; return redirect(url_for('reset_password'))
        else: flash('Invalid mobile number or date of birth.', 'error')
    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if 'reset_user_id' not in session: return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form['password']; confirm_password = request.form['confirm_password']
        if password != confirm_password: flash('Passwords do not match!', 'error'); return render_template('reset_password.html')
        hashed_password = generate_password_hash(password); user_id = session['reset_user_id']
        conn = get_db_connection(); conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id)); conn.commit(); conn.close()
        session.pop('reset_user_id', None); flash('Password updated successfully! Please login.', 'success'); return redirect(url_for('login'))
    return render_template('reset_password.html')

# --- Core Application Routes ---
@app.route('/market')
def market():
    if 'user_id' not in session: flash('Please login to view the market.', 'error'); return redirect(url_for('login'))
    search_query = request.args.get('query', ''); category = request.args.get('category')
    conn = get_db_connection()
    base_query = '''SELECT l.*, u.id as farmer_id, u.name as farmer_name, u.place as farmer_place, u.mobile_number, u.latitude, u.longitude FROM listings l JOIN users u ON l.farmer_id = u.id'''
    conditions = []; params = []
    if category and category in VEGETABLES:
        veggie_names = [v['name'] for v in VEGETABLES[category]]; placeholders = ','.join('?' for _ in veggie_names)
        conditions.append(f'l.vegetable_name IN ({placeholders})'); params.extend(veggie_names)
    if search_query:
        conditions.append('l.vegetable_name LIKE ?'); params.append(f'%{search_query}%')
    if conditions: base_query += ' WHERE ' + ' AND '.join(conditions)
    base_query += ' ORDER BY l.is_sold ASC, l.id DESC'
    listings = conn.execute(base_query, tuple(params)).fetchall(); conn.close()
    return render_template('market.html', listings=listings, categories=VEGETABLES.keys(), active_category=category, search_query=search_query)

# ## ITHU THAAN MACHA MUKKIYAMAANA PUTHU FUNCTION ##
@app.route('/farmer/<int:farmer_id>')
def view_farmer(farmer_id):
    if 'user_id' not in session:
        flash('Please login to view farmer profiles.', 'error')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    farmer = conn.execute('SELECT * FROM users WHERE id = ? AND user_type = "farmer"', (farmer_id,)).fetchone()
    
    if not farmer:
        flash('Farmer not found.', 'error')
        return redirect(url_for('market'))
        
    listings = conn.execute(
        'SELECT * FROM listings WHERE farmer_id = ? AND is_sold = 0 ORDER BY id DESC', 
        (farmer_id,)
    ).fetchall()
    
    conn.close()
    return render_template('farmer_public_profile.html', farmer=farmer, listings=listings)

# --- Profile Routes ---
@app.route('/profile')
def profile():
    if 'user_id' not in session or session['user_type'] != 'farmer': flash('Access denied.', 'error'); return redirect(url_for('login'))
    user_id = session['user_id']; conn = get_db_connection(); user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone(); conn.close()
    return render_template('farmer_profile.html', user=user)
@app.route('/update_location', methods=['POST'])
def update_location():
    if 'user_id' not in session or session['user_type'] != 'farmer': return redirect(url_for('login'))
    user_id = session['user_id']; latitude = request.form['latitude']; longitude = request.form['longitude']
    conn = get_db_connection(); conn.execute('UPDATE users SET latitude = ?, longitude = ? WHERE id = ?', (latitude, longitude, user_id)); conn.commit(); conn.close()
    flash('Your farm location has been updated!', 'success'); return redirect(url_for('profile'))
@app.route('/buyer_profile')
def buyer_profile():
    if 'user_id' not in session or session['user_type'] != 'buyer': flash('Access denied.', 'error'); return redirect(url_for('login'))
    user_id = session['user_id']; conn = get_db_connection(); user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone(); conn.close()
    if user: return render_template('buyer_profile.html', user=user)
    else: return redirect(url_for('logout'))
@app.route('/update_buyer_location', methods=['POST'])
def update_buyer_location():
    if 'user_id' not in session or session['user_type'] != 'buyer': return redirect(url_for('login'))
    user_id = session['user_id']; latitude = request.form['latitude']; longitude = request.form['longitude']
    conn = get_db_connection(); conn.execute('UPDATE users SET latitude = ?, longitude = ? WHERE id = ?', (latitude, longitude, user_id)); conn.commit(); conn.close()
    flash('Your primary location has been updated!', 'success'); return redirect(url_for('buyer_profile'))

# --- Listing Routes ---
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session['user_type'] != 'farmer': flash('Access denied.', 'error'); return redirect(url_for('login'))
    user_id = session['user_id']; conn = get_db_connection(); 
    listings = conn.execute('SELECT * FROM listings WHERE farmer_id = ? ORDER BY is_sold ASC, id DESC', (user_id,)).fetchall()
    active_count = conn.execute("SELECT COUNT(id) FROM listings WHERE farmer_id = ? AND is_sold = 0", (user_id,)).fetchone()[0]
    sold_count = conn.execute("SELECT COUNT(id) FROM listings WHERE farmer_id = ? AND is_sold = 1", (user_id,)).fetchone()[0]
    earnings_result = conn.execute("SELECT SUM(quantity_kg * rate_per_kg) FROM listings WHERE farmer_id = ? AND is_sold = 0", (user_id,)).fetchone()[0]
    earnings = earnings_result if earnings_result is not None else 0
    conn.close()
    return render_template('dashboard.html', listings=listings, active_count=active_count, sold_count=sold_count, earnings=earnings)

@app.route('/toggle_status/<int:listing_id>', methods=['POST'])
def toggle_status(listing_id):
    if 'user_id' not in session or session['user_type'] != 'farmer': flash('Access denied.', 'error'); return redirect(url_for('login'))
    conn = get_db_connection(); listing = conn.execute('SELECT * FROM listings WHERE id = ? AND farmer_id = ?', (listing_id, session['user_id'])).fetchone()
    if listing:
        new_status = 1 - listing['is_sold']; conn.execute('UPDATE listings SET is_sold = ? WHERE id = ?', (new_status, listing_id)); conn.commit()
        flash('Listing status updated successfully.', 'success')
    else: flash('You are not authorized to change this listing.', 'error')
    conn.close(); return redirect(url_for('dashboard'))

@app.route('/add_listing', methods=['GET', 'POST'])
def add_listing():
    if 'user_id' not in session or session['user_type'] != 'farmer': flash('You must be a farmer to add a listing.', 'error'); return redirect(url_for('login'))
    conn = get_db_connection(); user = conn.execute('SELECT latitude, longitude FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not user['latitude'] or not user['longitude']:
        conn.close(); flash('Please set your farm location on your profile before adding a listing.', 'error'); return redirect(url_for('profile'))
    if request.method == 'POST':
        all_veggies = [veg for sublist in VEGETABLES.values() for veg in sublist]; farmer_id = session['user_id']; items_added = 0
        for veg in all_veggies:
            veg_name = veg['name']; quantity = request.form.get(f'quantity_{veg_name}'); rate = request.form.get(f'rate_{veg_name}')
            if quantity and rate and float(quantity) > 0 and float(rate) > 0: 
                conn.execute('INSERT INTO listings (farmer_id, vegetable_name, quantity_kg, rate_per_kg) VALUES (?, ?, ?, ?)',(farmer_id, veg_name, float(quantity), float(rate)))
                items_added += 1
        conn.commit()
        if items_added > 0: flash(f'{items_added} item(s) posted successfully!', 'success')
        else: flash('No items were added. Please enter both quantity and rate.', 'error')
        conn.close(); return redirect(url_for('dashboard'))
    conn.close(); return render_template('add_listing.html', vegetables=VEGETABLES)

@app.route('/delete_listing/<int:listing_id>', methods=['POST'])
def delete_listing(listing_id):
    if 'user_id' not in session or session['user_type'] != 'farmer': return redirect(url_for('login'))
    user_id = session['user_id']; conn = get_db_connection(); listing = conn.execute('SELECT * FROM listings WHERE id = ? AND farmer_id = ?', (listing_id, user_id)).fetchone()
    if listing: conn.execute('DELETE FROM listings WHERE id = ?', (listing_id,)); conn.commit(); flash('Listing deleted successfully.', 'success')
    else: flash('You are not authorized to delete this listing.', 'error')
    conn.close(); return redirect(url_for('dashboard'))

# --- Other Routes ---
@app.route('/admin_stats')
def admin_stats():
    conn = get_db_connection()
    farmer_count = conn.execute("SELECT COUNT(id) FROM users WHERE user_type = 'farmer'").fetchone()[0]; buyer_count = conn.execute("SELECT COUNT(id) FROM users WHERE user_type = 'buyer'").fetchone()[0]; total_users = conn.execute("SELECT COUNT(id) FROM users").fetchone()[0]
    conn.close()
    return f"""<h1>STATS FOR ADMIN:</h1><h2>Total Registered Users:</h2><p>Total Farmers: {farmer_count}<br>Total Buyers: {buyer_count}<br><strong>Total Users: {total_users}</strong></p>"""

@app.after_request
def after_request_callback(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"; response.headers["Pragma"] = "no-cache"; response.headers["Expires"] = "0"
    return response

# --- Main Application Runner ---
if __name__ == '__main__':
    create_tables()
    app.run(debug=True)