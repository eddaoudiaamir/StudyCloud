import os
from flask import Flask, jsonify, request, render_template, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# 1. Initialize Flask App FIRST
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 2. Database Configuration (Render Postgres or Local SQLite)
db_uri = os.environ.get('DATABASE_URL')
if db_uri and db_uri.startswith('postgres://'):
    db_uri = db_uri.replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri or 'sqlite:///study_cloud.db'

# 3. Initialize Extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_message = "Please log in to see your tasks"
login_manager.login_view = "ui"

# 4. Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    deadline = db.Column(db.String(50), nullable=True)  # Date string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# 5. User Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 6. Create Tables (Auto-create on startup)
with app.app_context():
    db.create_all()

# 7. Routes
@app.route("/")
def home():
    return "StudyCloud API is running! Go to /ui to login."

@app.route("/ui")
def ui():
    return render_template("index.html")

# --- Auth Routes ---
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Missing email or password"}), 400
    
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({"error": "Email already exists"}), 400
    
    user = User(email=data.get('email'))
    user.set_password(data.get('password'))
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User created"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    user = User.query.filter_by(email=data.get('email')).first()
    if user and user.check_password(data.get('password')):
        login_user(user)
        return jsonify({"message": "Logged in"}), 200
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})

# --- Task Routes (Enhanced with priority and deadline) ---
@app.route("/tasks", methods=["GET"])
@login_required
def get_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.created_at.desc()).all()
    return jsonify([{
        "id": t.id, 
        "title": t.title, 
        "done": t.done,
        "priority": t.priority,
        "deadline": t.deadline
    } for t in tasks])

@app.route("/tasks", methods=["POST"])
@login_required
def create_task():
    data = request.get_json()
    new_task = Task(
        title=data.get("title", ""),
        priority=data.get("priority", "medium"),
        deadline=data.get("deadline"),
        user_id=current_user.id
    )
    db.session.add(new_task)
    db.session.commit()
    return jsonify({
        "id": new_task.id,
        "title": new_task.title,
        "done": new_task.done,
        "priority": new_task.priority,
        "deadline": new_task.deadline
    }), 201

@app.route("/tasks/<int:task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    task.title = data.get("title", task.title)
    task.done = data.get("done", task.done)
    task.priority = data.get("priority", task.priority)
    task.deadline = data.get("deadline", task.deadline)
    db.session.commit()
    return jsonify({
        "id": task.id,
        "title": task.title,
        "done": task.done,
        "priority": task.priority,
        "deadline": task.deadline
    })

@app.route("/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({"message": "Task deleted"})

# 8. Run App
if __name__ == "__main__":
    app.run(debug=True)
