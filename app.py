from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-12345678')
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
    tags = db.Column(db.Text)
    due_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    def get_tags(self):
        if self.tags:
            try:
                return json.loads(self.tags)
            except:
                return []
        return []
    
    def set_tags(self, tags_list):
        self.tags = json.dumps(tags_list)

# Initialize database (non-blocking)
db_initialized = False

def init_db():
    global db_initialized
    if not db_initialized:
        with app.app_context():
            try:
                db.create_all()
                print('✅ Database ready!')
                db_initialized = True
            except Exception as e:
                print(f'Database error: {e}')

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except:
        return None

# Health check endpoint (REQUIRED FOR RENDER)
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

# Routes
@app.route('/')
def index():
    init_db()
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth'))

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    init_db()
    
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
    
    query = Task.query.filter_by(user_id=current_user.id)
    if filter_status != 'all':
        query = query.filter_by(status=filter_status)
    
    tasks = query.order_by(Task.created_at.desc()).all()
    
    all_count = Task.query.filter_by(user_id=current_user.id).count()
    complete_count = Task.query.filter_by(user_id=current_user.id, status='complete').count()
    incomplete_count = Task.query.filter_by(user_id=current_user.id, status='incomplete').count()
    
    upcoming = Task.query.filter_by(user_id=current_user.id, status='incomplete').filter(Task.due_date.isnot(None)).order_by(Task.due_date.asc()).limit(5).all()
    
    recent_activities = []
    streak = 0
    weekly_rate = (complete_count / all_count * 100) if all_count > 0 else 0
    completion_data = [0, 0, 0, 0, 0, 0, 0]
    
    return render_template('dashboard.html', 
                         tasks=tasks, 
                         filter_status=filter_status,
                         filter_priority='all',
                         all_count=all_count,
                         complete_count=complete_count,
                         incomplete_count=incomplete_count,
                         upcoming=upcoming,
                         recent_activities=recent_activities,
                         streak=streak,
                         weekly_rate=weekly_rate,
                         completion_data=completion_data,
                         now=datetime.utcnow())

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title')
    description = request.form.get('description', '')
    priority = request.form.get('priority', 'medium')
    due_date_str = request.form.get('due_date')
    tags_str = request.form.get('tags', '')
    
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
        except:
            pass
    
    tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
    
    task = Task(title=title, description=description, priority=priority, due_date=due_date, user_id=current_user.id)
    task.set_tags(tags)
    db.session.add(task)
    db.session.commit()
    
    flash('Task added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/toggle_task/<int:task_id>')
@login_required
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Unauthorized!', 'danger')
        return redirect(url_for('dashboard'))
    
    if task.status == 'incomplete':
        task.status = 'complete'
        task.completed_at = datetime.utcnow()
    else:
        task.status = 'incomplete'
        task.completed_at = None
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_task/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Unauthorized!', 'danger')
        return redirect(url_for('dashboard'))
    
    db.session.delete(task)
    db.session.commit()
    
    flash('Task deleted!', 'success')
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
    overdue = len([t for t in tasks if t.due_date and t.due_date < datetime.utcnow() and t.status == 'incomplete'])
    
    return render_template('analytics.html',
                         total_tasks=total_tasks,
                         completed=completed,
                         incomplete=incomplete,
                         high_priority=high_priority,
                         medium_priority=medium_priority,
                         low_priority=low_priority,
                         overdue=overdue,
                         tasks=tasks)

@app.route('/admin')
@login_required
def admin():
    if current_user.username != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    tasks = Task.query.all()
    
    for user in users:
        user.status = 'active'
        user.last_active = datetime.utcnow()
    
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
