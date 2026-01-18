from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///studycloud.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for Render's postgres:// URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth'

# Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='incomplete')
    priority = db.Column(db.String(20), default='medium')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Health check for Render
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth'))

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'register':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists!', 'danger')
                return redirect(url_for('auth'))
            
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth'))
        
        else:  # login
            username = request.form.get('username')
            password = request.form.get('password')
            
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password!', 'danger')
                return redirect(url_for('auth'))
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    return render_template('auth.html')

@app.route('/dashboard')
@login_required
def dashboard():
    filter_status = request.args.get('status', 'all')
    filter_priority = request.args.get('priority', 'all')
    
    query = Task.query.filter_by(user_id=current_user.id)
    
    if filter_status != 'all':
        query = query.filter_by(status=filter_status)
    
    if filter_priority != 'all':
        query = query.filter_by(priority=filter_priority)
    
    tasks = query.order_by(Task.created_at.desc()).all()
    
    all_count = Task.query.filter_by(user_id=current_user.id).count()
    complete_count = Task.query.filter_by(user_id=current_user.id, status='complete').count()
    incomplete_count = Task.query.filter_by(user_id=current_user.id, status='incomplete').count()
    
    return render_template('dashboard.html', 
                         tasks=tasks,
                         filter_status=filter_status,
                         filter_priority=filter_priority,
                         all_count=all_count,
                         complete_count=complete_count,
                         incomplete_count=incomplete_count)

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title')
    description = request.form.get('description')
    priority = request.form.get('priority', 'medium')
    
    task = Task(title=title, description=description, priority=priority, user_id=current_user.id)
    db.session.add(task)
    db.session.commit()
    
    flash('Task added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/toggle_task/<int:task_id>')
@login_required
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Unauthorized action!', 'danger')
        return redirect(url_for('dashboard'))
    
    task.status = 'complete' if task.status == 'incomplete' else 'incomplete'
    db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/delete_task/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Unauthorized action!', 'danger')
        return redirect(url_for('dashboard'))
    
    db.session.delete(task)
    db.session.commit()
    
    flash('Task deleted successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/analytics')
@login_required
def analytics():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    
    total_tasks = len(tasks)
    completed = len([t for t in tasks if t.status == 'complete'])
    incomplete = len([t for t in tasks if t.status == 'incomplete'])
    
    high_priority = len([t for t in tasks if t.priority == 'high'])
    medium_priority = len([t for t in tasks if t.priority == 'medium'])
    low_priority = len([t for t in tasks if t.priority == 'low'])
    
    return render_template('analytics.html',
                         total_tasks=total_tasks,
                         completed=completed,
                         incomplete=incomplete,
                         high_priority=high_priority,
                         medium_priority=medium_priority,
                         low_priority=low_priority)

@app.route('/admin')
@login_required
def admin():
    if current_user.username != 'admin':
        flash('Access denied! Admin only.', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    tasks = Task.query.all()
    
    total_users = len(users)
    total_tasks = len(tasks)
    completed_tasks = Task.query.filter_by(status='complete').count()
    
    return render_template('admin.html', 
                         users=users, 
                         tasks=tasks,
                         total_users=total_users,
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth'))

if __name__ == '__main__':
    app.run(debug=True)
