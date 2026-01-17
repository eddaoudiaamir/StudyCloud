import os
from flask import Flask, jsonify, request, render_template, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import logging

# 1. Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 2. Database Configuration
db_uri = os.environ.get('DATABASE_URL')
if db_uri and db_uri.startswith('postgres://'):
    db_uri = db_uri.replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri or 'sqlite:///study_cloud.db'

# 3. Initialize Extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_message = "Please log in to access this page"
login_manager.login_view = "ui"

# 4. Configure Logging for User Activity
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 5. Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='medium')
    deadline = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# 6. User Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 7. Create Tables
with app.app_context():
    db.create_all()

# 8. Basic Routes
@app.route("/")
def home():
    return "StudyCloud API is running! Go to /ui to login."

@app.route("/ui")
def ui():
    return render_template("index.html")

# 9. Auth Routes
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
    
    logger.info(f"New user registered: {user.email}")
    return jsonify({"message": "User created successfully"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    user = User.query.filter_by(email=data.get('email')).first()
    if user and user.check_password(data.get('password')):
        login_user(user)
        logger.info(f"User logged in: {user.email} at {datetime.now()}")
        return jsonify({"message": "Logged in", "email": user.email}), 200
    
    logger.warning(f"Failed login attempt for: {data.get('email')}")
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logger.info(f"User logged out: {current_user.email}")
    logout_user()
    return jsonify({"message": "Logged out"})

# 10. Task Routes
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

# 11. USER STATS ROUTE (NEW)
@app.route("/stats")
@login_required
def get_stats():
    total_tasks = Task.query.filter_by(user_id=current_user.id).count()
    completed = Task.query.filter_by(user_id=current_user.id, done=True).count()
    pending = total_tasks - completed
    high_priority = Task.query.filter_by(user_id=current_user.id, priority='high', done=False).count()
    
    return jsonify({
        "user_email": current_user.email,
        "total_tasks": total_tasks,
        "completed": completed,
        "pending": pending,
        "high_priority": high_priority,
        "member_since": current_user.created_at.strftime("%d/%m/%Y") if current_user.created_at else "N/A"
    })

# 12. ADMIN ROUTE - View All Users (NEW)
@app.route("/admin/users")
@login_required
def view_users():
    # WARNING: Add admin role check in production!
    users = User.query.all()
    user_list = [{
        "id": u.id,
        "email": u.email,
        "total_tasks": Task.query.filter_by(user_id=u.id).count(),
        "registered": u.created_at.strftime("%d/%m/%Y %H:%M") if u.created_at else "N/A"
    } for u in users]
    return jsonify({"total_users": len(user_list), "users": user_list})

# 13. Health Check
@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_users": User.query.count(),
        "total_tasks": Task.query.count()
    })

# 14. Run App
if __name__ == "__main__":
    app.run(debug=True)
