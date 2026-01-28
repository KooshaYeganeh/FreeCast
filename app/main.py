from flask import Flask, send_from_directory, render_template, request, redirect, url_for, flash, jsonify , make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import getpass
import config
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor

username = getpass.getuser()
VIDEO_FOLDER = config.SHAREFOLDER
COVERS_FOLDER = os.path.join('static', 'covers')
THUMBNAILS_FOLDER = os.path.join('static', 'thumbnails')

app = Flask(__name__)
app.secret_key = 'Free Media'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# Database configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'koosha'
app.config['MYSQL_PASSWORD'] = 'K102030k'
app.config['MYSQL_DB'] = 'kygnus_video_library'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'error'
# Initialize Flask-Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Create necessary directories
os.makedirs(COVERS_FOLDER, exist_ok=True)
os.makedirs(THUMBNAILS_FOLDER, exist_ok=True)

# Database connection function
def get_db_connection():
    return pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB'],
        cursorclass=DictCursor
    )

# Initialize database tables
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                email VARCHAR(120),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Create video_metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS video_metadata (
                id INT AUTO_INCREMENT PRIMARY KEY,
                video_path VARCHAR(500) UNIQUE NOT NULL,
                cover_image VARCHAR(500),
                views INT DEFAULT 0,
                upload_date DATE,
                duration VARCHAR(20),
                uploaded_by INT,
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        ''')

        # Update the iptv_channels table creation in init_db() function:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS iptv_channels (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                stream_url VARCHAR(500) NOT NULL,
                category VARCHAR(100),
                group_title VARCHAR(100) DEFAULT 'General',
                logo_url VARCHAR(500),
                is_live BOOLEAN DEFAULT TRUE,
                quality VARCHAR(20) DEFAULT 'HD',
                country_code VARCHAR(10),
                added_by INT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (added_by) REFERENCES users(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS iptv_playlists (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                m3u_content TEXT,
                created_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')

        # ALTER TABLE iptv_channels ADD COLUMN group_title VARCHAR(100) DEFAULT 'General';
        # Create default admin user if not exists
        cursor.execute('SELECT * FROM users WHERE username = %s', ('admin',))
        admin_user = cursor.fetchone()
        
        if not admin_user:
            password_hash = generate_password_hash('admin123')
            cursor.execute(
                'INSERT INTO users (username, password_hash) VALUES (%s, %s)',
                ('admin', password_hash)
            )
            print("Default admin user created: admin/admin123")
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Database initialization error: {e}")

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, password_hash, email=None):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.email = email

    @staticmethod
    def get(user_id):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = %s AND is_active = TRUE', (user_id,))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data:
                return User(
                    id=user_data['id'],
                    username=user_data['username'],
                    password_hash=user_data['password_hash'],
                    email=user_data['email']
                )
            return None
        except Exception as e:
            print(f"Error getting user: {e}")
            return None

    @staticmethod
    def find_by_username(username):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = %s AND is_active = TRUE', (username,))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data:
                return User(
                    id=user_data['id'],
                    username=user_data['username'],
                    password_hash=user_data['password_hash'],
                    email=user_data['email']
                )
            return None
        except Exception as e:
            print(f"Error finding user by username: {e}")
            return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Metadata functions using database
def load_metadata():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM video_metadata')
        metadata = {row['video_path']: dict(row) for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return metadata
    except Exception as e:
        print(f"Error loading metadata: {e}")
        return {}

def save_metadata(video_path, metadata):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if record exists
        cursor.execute('SELECT id FROM video_metadata WHERE video_path = %s', (video_path,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record
            cursor.execute('''
                UPDATE video_metadata 
                SET cover_image = %s, views = %s, upload_date = %s, duration = %s 
                WHERE video_path = %s
            ''', (
                metadata.get('cover_image'),
                metadata.get('views', 0),
                metadata.get('upload_date'),
                metadata.get('duration', '10:30'),
                video_path
            ))
        else:
            # Insert new record
            cursor.execute('''
                INSERT INTO video_metadata (video_path, cover_image, views, upload_date, duration, uploaded_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                video_path,
                metadata.get('cover_image', '../static/images/video_player.gif'),
                metadata.get('views', 0),
                metadata.get('upload_date', datetime.now().strftime('%Y-%m-%d')),
                metadata.get('duration', '10:30'),
                metadata.get('uploaded_by', 1)  # Default to admin if not specified
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving metadata: {e}")
        return False

def get_video_metadata(video_path):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM video_metadata WHERE video_path = %s', (video_path,))
        metadata = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if metadata:
            return dict(metadata)
        else:
            return {
                'cover_image': '../static/images/video_player.gif',
                'views': 0,
                'upload_date': datetime.now().strftime('%Y-%m-%d'),
                'duration': '10:30'
            }
    except Exception as e:
        print(f"Error getting video metadata: {e}")
        return {
            'cover_image': '../static/images/video_player.gif',
            'views': 0,
            'upload_date': datetime.now().strftime('%Y-%m-%d'),
            'duration': '10:30'
        }

def update_video_metadata(video_path, updates):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if record exists
        cursor.execute('SELECT id FROM video_metadata WHERE video_path = %s', (video_path,))
        existing = cursor.fetchone()
        
        if existing:
            # Build update query dynamically
            set_clause = ', '.join([f"{key} = %s" for key in updates.keys()])
            values = list(updates.values())
            values.append(video_path)
            
            cursor.execute(f'UPDATE video_metadata SET {set_clause} WHERE video_path = %s', values)
        else:
            # Create new record with all updates
            updates['video_path'] = video_path
            columns = ', '.join(updates.keys())
            placeholders = ', '.join(['%s'] * len(updates))
            
            cursor.execute(f'INSERT INTO video_metadata ({columns}) VALUES ({placeholders})', list(updates.values()))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating metadata: {e}")
        return False

def get_video_structure(root_folder):
    video_structure = []
    
    try:
        for item in os.listdir(root_folder):
            item_path = os.path.join(root_folder, item)
            
            if os.path.isdir(item_path):
                folder_contents = []
                for subitem in os.listdir(item_path):
                    if subitem.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
                        video_rel_path = f"{item}/{subitem}"
                        video_meta = get_video_metadata(video_rel_path)
                        folder_contents.append({
                            "name": subitem,
                            "url": f"/videos/{video_rel_path}",
                            "cover": video_meta.get('cover_image', '../static/images/video_player.gif'),
                            "views": video_meta.get('views', 0),
                            "upload_date": video_meta.get('upload_date', datetime.now().strftime('%Y-%m-%d')),
                            "duration": video_meta.get('duration', '10:30')
                        })
                
                if folder_contents:
                    video_structure.append({
                        "type": "folder",
                        "name": item,
                        "contents": folder_contents,
                        "count": len(folder_contents)
                    })
            elif item.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
                video_meta = get_video_metadata(item)
                video_structure.append({
                    "type": "video",
                    "name": item,
                    "url": f"/videos/{item}",
                    "cover": video_meta.get('cover_image', '../static/images/video_player.gif'),
                    "views": video_meta.get('views', 0),
                    "upload_date": video_meta.get('upload_date', datetime.now().strftime('%Y-%m-%d')),
                    "duration": video_meta.get('duration', '10:30')
                })
    except Exception as e:
        print(f"Error getting video structure: {e}")
    
    return video_structure

def format_views(views):
    if views >= 1000000:
        return f"{views/1000000:.1f}M"
    elif views >= 1000:
        return f"{views/1000:.1f}K"
    return str(views)

def format_date(upload_date):
    try:
        date_obj = datetime.strptime(upload_date, '%Y-%m-%d')
        delta = datetime.now() - date_obj
        if delta.days == 0:
            return "today"
        elif delta.days == 1:
            return "1 day ago"
        elif delta.days < 7:
            return f"{delta.days} days ago"
        elif delta.days < 30:
            weeks = delta.days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        elif delta.days < 365:
            months = delta.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = delta.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
    except:
        return "recently"

# Template context processor
@app.context_processor
def utility_processor():
    return dict(format_views=format_views, format_date=format_date, current_user=current_user)

# Routes
@app.route("/")
def index():
    video_structure = get_video_structure(VIDEO_FOLDER)
    return render_template("videos.html", video_structure=video_structure)

@app.route("/login", methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        user = User.find_by_username(username)
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            flash('Login successful!', 'success')
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route("/register", methods=['GET', 'POST'])
@limiter.limit("3 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email', '').strip()
        
        # Validation
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template("register.html")
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template("register.html")
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template("register.html")
        
        if len(username) < 3 or len(username) > 20:
            flash('Username must be between 3 and 20 characters', 'error')
            return render_template("register.html")
        
        # Check if username exists in database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                flash('Username already exists', 'error')
                return render_template("register.html")
            
            # Create new user
            password_hash = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO users (username, password_hash, email) VALUES (%s, %s, %s)',
                (username, password_hash, email if email else None)
            )
            conn.commit()
            cursor.close()
            conn.close()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash('Error creating user. Please try again.', 'error')
            print(f"Registration error: {e}")
    
    return render_template("register.html")

@app.route("/upload", methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        folder = request.form.get('folder', '')
        new_folder = request.form.get('new_folder', '').strip()
        
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        # Use new folder if provided
        if new_folder:
            folder = new_folder
        
        if file and file.filename.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm')):
            filename = secure_filename(file.filename)
            
            if folder:
                target_folder = os.path.join(VIDEO_FOLDER, folder)
                os.makedirs(target_folder, exist_ok=True)
                file_path = os.path.join(target_folder, filename)
                video_rel_path = f"{folder}/{filename}"
            else:
                file_path = os.path.join(VIDEO_FOLDER, filename)
                video_rel_path = filename
            
            file.save(file_path)
            
            # Create metadata entry in database
            update_video_metadata(video_rel_path, {
                'upload_date': datetime.now().strftime('%Y-%m-%d'),
                'views': 0,
                'duration': '10:30',
                'uploaded_by': current_user.id
            })
            
            flash('Video uploaded successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid file type. Please upload a video file.', 'error')
    
    # Get existing folders for dropdown
    folders = []
    for item in os.listdir(VIDEO_FOLDER):
        if os.path.isdir(os.path.join(VIDEO_FOLDER, item)):
            folders.append(item)
    
    return render_template("upload.html", folders=folders)

@app.route("/manage")
@login_required
def manage():
    video_structure = get_video_structure(VIDEO_FOLDER)
    return render_template("manage.html", video_structure=video_structure)

@app.route("/analytics")
@login_required
def analytics():
    video_structure = get_video_structure(VIDEO_FOLDER)
    total_views = 0
    total_videos = 0
    
    # Calculate analytics
    for item in video_structure:
        if item['type'] == 'folder':
            for video in item['contents']:
                total_views += video['views']
                total_videos += 1
        else:
            total_views += item['views']
            total_videos += 1
    
    return render_template("analytics.html", 
                         total_views=total_views, 
                         total_videos=total_videos,
                         video_structure=video_structure)

@app.route("/update_cover", methods=['POST'])
@login_required
def update_cover():
    video_path = request.json.get('video_path')
    cover_url = request.json.get('cover_url')
    
    if video_path and cover_url:
        update_video_metadata(video_path, {'cover_image': cover_url})
        return jsonify({'success': True})
    
    return jsonify({'success': False})

@app.route("/increment_views", methods=['POST'])
def increment_views():
    video_path = request.json.get('video_path')
    
    if video_path:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE video_metadata SET views = views + 1 WHERE video_path = %s',
                (video_path,)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True})
        except Exception as e:
            print(f"Error incrementing views: {e}")
            return jsonify({'success': False})
    
    return jsonify({'success': False})

@app.route("/delete_video", methods=['POST'])
@login_required
def delete_video():
    video_path = request.json.get('video_path')
    
    if video_path:
        full_path = os.path.join(VIDEO_FOLDER, video_path)
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
                # Remove from database
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM video_metadata WHERE video_path = %s', (video_path,))
                conn.commit()
                cursor.close()
                conn.close()
                return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False})

@app.route("/videos/<path:filename>")
def serve_video(filename):
    path = Path(VIDEO_FOLDER) / filename
    directory = str(path.parent)
    filename = path.name
    return send_from_directory(directory, filename)

@app.route("/static/covers/<filename>")
def serve_cover(filename):
    return send_from_directory(COVERS_FOLDER, filename)

# Error handlers
@app.errorhandler(429)
def ratelimit_handler(e):
    flash('Too many requests. Please try again later.', 'error')
    return redirect(url_for('login'))

@login_manager.unauthorized_handler
def unauthorized_handler():
    flash('Please log in to access this page.', 'error')
    return redirect(url_for('login', next=request.url))
















if __name__ == "__main__":
    init_db()  # Initialize database tables
    app.run("0.0.0.0", port=5005, debug=True)
