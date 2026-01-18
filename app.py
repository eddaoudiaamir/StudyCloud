from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
from sqlalchemy import inspect, text
import json

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
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
    status = db.Column(db.String(20), default='active')
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='owner', lazy=True, cascade='all, delete-orphan')
    activities = db.relationship('Activity', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def update_last_active(self):
        self.last_active = datetime.utcnow()
        time_diff = datetime.utcnow() - self.last_active
        if time_diff < timedelta(minutes=5):
            self.status = 'active'
        elif time_diff < timedelta(hours=1):
            self.status = 'away'
        else:
            self.status = 'offline'
        db.session.commit()

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='incomplete')
    priority = db.Column(db.String(20), default='medium')
    tags = db.Column(db.Text)
    due_date = db.Column(db.DateTime, nullable=True)
    time_spent = db.Column(db.Integer, default=0)
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

class Activity(db.Model):
    __tablename__ = 'activities'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200), nullable=False)
    task_title = db.Column(db.String(200))
    icon_type = db.Column(db.String(20), default='info')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# Database setup
with app.app_context():
    try:
        # Create all tables first
        db.create_all()
        print('✅ All tables created!')
        
        # Then add missing columns if needed
        inspector = inspect(db.engine)
        
        if 'tasks' in inspector.get_table_names():
            columns = [column['name'] for column in inspector.get_columns('tasks')]
            
            with db.engine.connect() as conn:
                if 'due_date' not in columns:
                    try:
                        conn.execute(text('ALTER TABLE tasks ADD COLUMN due_date TIMESTAMP'))
                        conn.commit()
                        print('✅ Added due_date')
                    except: pass
                
                if 'tags' not in columns:
                    try:
                        conn.execute(text('ALTER TABLE tasks ADD COLUMN tags TEXT'))
                        conn.commit()
                        print('✅ Added tags')
                    except: pass
                
                if 'time_spent' not in columns:
                    try:
                        conn.execute(text('ALTER TABLE tasks ADD COLUMN time_spent INTEGER DEFAULT 0'))
                        conn.commit()
                        print('✅ Added time_spent')
                    except: pass
                
                if 'completed_at' not in columns:
                    try:
                        conn.execute(text('ALTER TABLE tasks ADD COLUMN completed_at TIMESTAMP'))
                        conn.commit()
                        print('✅ Added completed_at')
                    except: pass
        
        if 'users' in inspector.get_table_names():
            columns = [column['name'] for column in inspector.get_columns('users')]
            
            with db.engine.connect() as conn:
                if 'status' not in columns:
                    try:
                        conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                        conn.commit()
                        print('✅ Added status')
                    except: pass
                
                if 'last_active' not in columns:
                    try:
                        conn.execute(text('ALTER TABLE users ADD COLUMN last_active TIMESTAMP'))
                        conn.commit()
                        print('✅ Added last_active')
                    except: pass
        
        print('✅ Database ready!')
    except Exception as e:
        print(f'❌ Database error: {e}')

@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
        if user:
            user.update_last_active()
        return user
    except:
        return None

def log_activity(action, task_title=None, icon_type='info'):
    try:
        if current_user.is_authenticated:
            activity = Activity(
                action=action,
                task_title=task_title,
                icon_type=icon_type,
                user_id=current_user.id
            )
            db.session.add(activity)
            db.session.commit()
    except:
        pass

def calculate_streak():
    try:
        if not current_user.is_authenticated:
            return 0
        
        completed_tasks = Task.query.filter_by(
            user_id=current_user.id, 
            status='complete'
        ).order_by(Task.completed_at.desc()).all()
        
        if not completed_tasks:
            return 0
        
        streak = 0
        current_date = datetime.utcnow().date()
        
        for task in completed_tasks:
            if task.completed_at:
                task_date = task.completed_at.date()
                if task_date == current_date or task_date == current_date - timedelta(days=1):
                    current_date = task_date
                    streak = (datetime.utcnow().date() - task_date).days + 1
                else:
                    break
        
        return streak if streak > 0 else 0
    except:
        return 0

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth'))

@app.route('/auth')
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('auth.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    
    if User.query.filter_by(username=username).first():
        flash('Username already exists!', 'danger')
        return redirect(url_for('auth'))
    
    if User.query.filter_by(email=email).first():
        flash('Email already registered!', 'danger')
        return redirect(url_for('auth'))
    
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    flash('Registration successful! Please login.', 'success')
    return redirect(url_for('auth'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        login_user(user)
        user.update_last_active()
        log_activity(f"Logged in", icon_type='info')
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid username or password!', 'danger')
        return redirect(url_for('auth'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        filter_status = request.args.get('status', 'all')
        filter_priority = request.args.get('priority', 'all')
        
        query = Task.query.filter_by(user_id=current_user.id)
        
        if filter_status != 'all':
            query = query.filter_by(status=filter_status)
        
        if filter_priority != 'all':
            query = query.filter_by(priority=filter_priority)
        
        tasks = query.order_by(Task.due_date.asc().nullslast()).all()
        
        all_count = Task.query.filter_by(user_id=current_user.id).count()
        complete_count = Task.query.filter_by(user_id=current_user.id, status='complete').count()
        incomplete_count = Task.query.filter_by(user_id=current_user.id, status='incomplete').count()
        
        upcoming = Task.query.filter_by(
            user_id=current_user.id, 
            status='incomplete'
        ).filter(Task.due_date.isnot(None)).order_by(Task.due_date.asc()).limit(5).all()
        
        recent_activities = Activity.query.filter_by(
            user_id=current_user.id
        ).order_by(Activity.created_at.desc()).limit(5).all()
        
        streak = calculate_streak()
        
        week_ago = datetime.utcnow() - timedelta(days=7)
        week_completed = Task.query.filter_by(
            user_id=current_user.id, 
            status='complete'
        ).filter(Task.completed_at >= week_ago).count()
        week_total = Task.query.filter_by(user_id=current_user.id).filter(Task.created_at >= week_ago).count()
        weekly_rate = (week_completed / week_total * 100) if week_total > 0 else 0
        
        completion_data = []
        for i in range(6, -1, -1):
            date = datetime.utcnow() - timedelta(days=i)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = date.replace(hour=23, minute=59, second=59)
            count = Task.query.filter_by(
                user_id=current_user.id,
                status='complete'
            ).filter(Task.completed_at >= day_start, Task.completed_at <= day_end).count()
            completion_data.append(count)
        
        return render_template('dashboard.html', 
                             tasks=tasks, 
                             filter_status=filter_status,
                             filter_priority=filter_priority,
                             all_count=all_count,
                             complete_count=complete_count,
                             incomplete_count=incomplete_count,
                             upcoming=upcoming,
                             recent_activities=recent_activities,
                             streak=streak,
                             weekly_rate=weekly_rate,
                             completion_data=completion_data)
    except Exception as e:
        print(f"Dashboard error: {e}")
        flash('Error loading dashboard. Please try again.', 'danger')
        return redirect(url_for('auth'))

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title')
    description = request.form.get('description')
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
    
    log_activity(f"Created new task", task_title=title, icon_type='info')
    flash('Task added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/toggle_task/<int:task_id>')
@login_required
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Unauthorized action!', 'danger')
        return redirect(url_for('dashboard'))
    
    if task.status == 'incomplete':
        task.status = 'complete'
        task.completed_at = datetime.utcnow()
        log_activity(f"Completed task", task_title=task.title, icon_type='success')
    else:
        task.status = 'incomplete'
        task.completed_at = None
        log_activity(f"Reopened task", task_title=task.title, icon_type='warning')
    
    db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/delete_task/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Unauthorized action!', 'danger')
        return redirect(url_for('dashboard'))
    
    task_title = task.title
    db.session.delete(task)
    db.session.commit()
    
    log_activity(f"Deleted task", task_title=task_title, icon_type='warning')
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
    
    now = datetime.utcnow()
    overdue = len([t for t in tasks if t.due_date and t.due_date < now and t.status == 'incomplete'])
    
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
        flash('Access denied! Admin only.', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    tasks = Task.query.all()
    
    for user in users:
        if user.last_active:
            time_diff = datetime.utcnow() - user.last_active
            if time_diff < timedelta(minutes=5):
                user.status = 'active'
            elif time_diff < timedelta(hours=1):
                user.status = 'away'
            else:
                user.status = 'offline'
    db.session.commit()
    
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
    log_activity(f"Logged out", icon_type='info')
    logout_user()
    return redirect(url_for('auth'))

if __name__ == '__main__':
    app.run(debug=True)
