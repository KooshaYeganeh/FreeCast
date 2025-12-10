# Tutorial: Setting Up Your Own Media Server with FreeCast

FreeCast (also referred to as CASTBOX or FMhost in some files) is an open-source Flask-based application designed to turn old PCs or mini PCs into a YouTube-style mini media server. It supports video hosting, streaming, user authentication, video uploads, management, and basic analytics. The server can run on a local LAN network, making it ideal for personal or small-scale use. It uses a MySQL database for user and video metadata storage, with videos served directly from a configured directory on your filesystem.

This tutorial provides step-by-step instructions to set up and use FreeCast on a Linux system (tested on Ubuntu). It's based on the GitHub repository at https://github.com/KooshaYeganeh/FreeCast, the provided project structure, and analysis of the code and scripts.

## Prerequisites
Before starting, ensure you have:
- A Linux machine (e.g., Ubuntu 20.04+ or similar). Old PCs or mini PCs work well.
- Python 3.11 installed (the install script checks for this).
- Git installed (`sudo apt install git`).
- MySQL server installed and running (`sudo apt install mysql-server`).
- Basic command-line knowledge.
- Administrative access (sudo) for system services.
- A directory with videos (e.g., MP4, AVI, MKV, MOV, WEBM files) to serve.

**Note on Security:** The code hardcodes MySQL credentials (user: 'koosha', password: 'K102030k', database: 'kygnus_video_library'). In a production setup, change these and consider using environment variables or a separate config file for security. User passwords are hashed, but default admin credentials ('admin'/'admin123') should be changed immediately.

## Step 1: Clone the Repository
Clone the FreeCast repository from GitHub to your local machine. Replace `/path/to/install` with your desired installation directory (e.g., `/home/yourusername/FreeCast`).

```bash
git clone https://github.com/KooshaYeganeh/FreeCast.git /path/to/install/FreeCast
cd /path/to/install/FreeCast
```

This will download the project files, including the app code, templates, static assets, install script, runner script, systemd service file, and more.

## Step 2: Set Up MySQL Database
FreeCast uses MySQL to store user accounts and video metadata (e.g., views, upload dates, covers).

1. Start and secure MySQL if not already done:
   ```bash
   sudo systemctl start mysql
   sudo mysql_secure_installation
   ```

2. Log in to MySQL as root:
   ```bash
   sudo mysql -u root -p
   ```

3. Create the database and user (update credentials as needed):
   ```sql
   CREATE DATABASE kygnus_video_library;
   CREATE USER 'koosha'@'localhost' IDENTIFIED BY 'K102030k';
   GRANT ALL PRIVILEGES ON kygnus_video_library.* TO 'koosha'@'localhost';
   FLUSH PRIVILEGES;
   EXIT;
   ```

   **Important:** If you change the username, password, or database name, update them in `app/main.py` (search for `app.config['MYSQL_...']`).

4. The app will automatically initialize tables (users and video_metadata) on first run, including a default admin user ('admin' / 'admin123').

## Step 3: Configure the Video Directory
Edit `app/config.py` to set the path to your video storage folder. This is where videos will be served from and uploads will go to.

```python
# app/config.py
SHAREFOLDER = "/path/to/your/videos"  # e.g., "/home/yourusername/Videos/Hosting"
```

Ensure the folder exists and is writable by the user running the app (e.g., your username).

The app also creates `static/covers` and `static/thumbnails` for video covers/thumbnails if they don't exist.

## Step 4: Install Dependencies and Set Up the Environment
The project includes an `install` script that automates virtual environment creation, dependency installation, and systemd service setup.

1. Make the install script executable:
   ```bash
   chmod +x install
   ```

2. Run the install script:
   ```bash
   ./install
   ```

   This script:
   - Checks for Python 3.11 and `python3.11-venv`.
   - Creates a virtual environment (`venv`) if it doesn't exist.
   - Activates the venv and installs dependencies from `requirements.txt` (e.g., Flask 3.1.0, Gunicorn 23.0.0, Flask-Login 0.6.3, PyMySQL 1.1.2, etc.).
   - Copies `FMhost.service` to `/etc/systemd/system/` and enables/starts the service.

   **Expected Output:** Green success messages. If errors occur (e.g., missing packages), follow the script's suggestions.

**Note on Paths:** The `FMhost.service` and `FMhost_runner` files have hardcoded paths like `/home/koosha/w/FMhost`. Replace 'koosha' with your username and adjust the working directory to match your installation path (e.g., edit with `nano FMhost.service` and `nano FMhost_runner` before running install).

## Step 5: Customize the Systemd Service (If Needed)
If you skipped or modified the install script, manually set up the service:

1. Edit `FMhost_runner` to point to your installation:
   ```bash
   #!/bin/bash
   if [ "$1" = "stop" ]; then
       pkill -f "gunicorn -w 3 -b 127.0.0.1:5005"
       exit 0
   fi
   cd /path/to/install/FreeCast
   source venv/bin/activate
   cd app
   gunicorn -w 3 -b 127.0.0.1:5005 main:app
   ```

2. Edit `FMhost.service`:
   - Set `User=yourusername`.
   - Set `WorkingDirectory=/path/to/install/FreeCast`.
   - Set `ExecStart=/bin/bash /path/to/install/FreeCast/FMhost_runner`.
   - Set `ExecStop=/bin/bash /path/to/install/FreeCast/FMhost_runner stop`.
   - Add your venv to `Environment="PATH=..."`.

3. Copy and enable:
   ```bash
   sudo cp FMhost.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable FMhost.service
   sudo systemctl start FMhost.service
   ```

Check status: `sudo systemctl status FMhost.service`.

## Step 6: Run and Access the Server
- The server runs on `http://127.0.0.1:5005` (localhost, port 5005).
- For LAN access, edit the Gunicorn bind in `FMhost_runner` to `0.0.0.0:5005` (exposes to network).
- Access in a browser: `http://your-server-ip:5005`.

Default login: Username 'admin', Password 'admin123'. Change this immediately after first login.

## Usage Guide
FreeCast provides a web interface with the following features (based on templates and code routes):

### 1. Login/Register
- **/login**: Log in with username/password. Rate-limited to 5 attempts/minute.
- **/register**: Create a new account (username, password, email). Rate-limited to 3/hour.
- After login, you're redirected to the video list.

### 2. Video Browsing and Streaming (/videos.html)
- Lists videos and folders from your `SHAREFOLDER`.
- Supports nested folders (videos inside folders are grouped).
- Each video shows: Cover image (default: media.avif), views (formatted e.g., 1.2K), upload date (e.g., "2 days ago"), duration.
- Click to stream in a modal player (HTML5 video).
- Views are incremented on access and stored in the database.

### 3. Upload Videos (/upload.html, login required)
- Upload new videos (max 500MB per file).
- Secure filename handling.
- Metadata (upload date, duration, etc.) is saved to the database.
- Uploaded by the current user.

### 4. Manage Videos (/manage.html, login required)
- Likely allows editing/deleting videos, updating metadata (e.g., cover images), or organizing folders.
- Interact with video_metadata table (views, cover_image, etc.).

### 5. Analytics (/analytics.html, login required)
- Displays video stats: Views, upload dates, perhaps per-user analytics.
- Uses database queries for data.

### 6. Serving Videos (/videos/<path:filename>)
- Streams video files directly from `SHAREFOLDER`.
- Increments view count in metadata.

**Rate Limiting:** Global limits (200/day, 50/hour) to prevent abuse.

## Customization and Tips
- **Themes/UI:** Edit templates (e.g., base.html for layout, videos.html for video list).
- **Video Covers/Thumbnails:** The app uses static folders; integrate FFmpeg (mentioned in README) for auto-generation.
- **Database Migration:** If using JSON files (users.json, video_metadata.json), they might be legacy; the code prioritizes MySQL.
- **LAN Setup:** Ensure firewall allows port 5005 (`sudo ufw allow 5005`). Use NGINX/Apache as reverse proxy for production.
- **Screenshots:** View in repo (freemedia1.png to freemedia4.png) for UI previews: Video list, player, login, etc.
- **Debugging:** Check logs with `journalctl -u FMhost.service -f`. Edit `app/main.py` for custom features.
- **Scaling:** For multiple users, add more workers in Gunicorn (`-w` flag).

## Troubleshooting
- **Service Fails to Start:** Check paths in service/runner files match your setup.
- **Database Errors:** Verify MySQL credentials and table creation (run app once to init).
- **No Videos Listed:** Ensure `SHAREFOLDER` is correct and contains supported files.
- **Permission Issues:** Run as non-root; chown folders to your user.
- If issues persist, check GitHub issues or email kygnus.co@proton.me.

