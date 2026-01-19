from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from sqlalchemy import inspect

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
    tasks = db.relationship('Task', backref='owner', lazy=True, cascade='all, delete-orphan')
    
    # 🎮 GAMIFICATION FIELDS
    points = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    badges = db.Column(db.String(500), default='')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # 🎮 GAMIFICATION METHODS
    def add_points(self, points):
        self.points += points
        self.level = (self.points // 100) + 1
        db.session.commit()
    
    def add_badge(self, badge_name):
        badges_list = self.badges.split(',') if self.badges else []
        if badge_name not in badges_list:
            badges_list.append(badge_name)
            self.badges = ','.join(badges_list)
            db.session.commit()
    
    def get_badges(self):
        return [b for b in self.badges.split(',') if b] if self.badges else []
    
    def points_to_next_level(self):
        next_level_points = self.level * 100
        return next_level_points - self.points

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='incomplete')
    priority = db.Column(db.String(20), default='medium')
    due_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# Database setup with migration
with app.app_context():
    try:
        inspector = inspect(db.engine)
        
        if inspector.has_table('tasks'):
            columns = [column['name'] for column in inspector.get_columns('tasks')]
            if 'due_date' not in columns:
                print('⚠️ Migrating database: Adding due_date column...')
                with db.engine.connect() as conn:
                    try:
                        conn.execute(db.text('ALTER TABLE tasks ADD COLUMN due_date TIMESTAMP'))
                        conn.commit()
                        print('✅ Database migration successful!')
                    except Exception as e:
                        print(f'❌ Migration error: {e}')
        
        # 🎮 ADD GAMIFICATION COLUMNS
        if inspector.has_table('users'):
            user_columns = [column['name'] for column in inspector.get_columns('users')]
            if 'points' not in user_columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text("ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0"))
                    conn.execute(db.text("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1"))
                    conn.execute(db.text("ALTER TABLE users ADD COLUMN badges VARCHAR(500) DEFAULT ''"))
                    conn.commit()
                    print('✅ Gamification columns added!')
        
        db.create_all()
        print('✅ Database tables ready!')
    except Exception as e:
        print(f'Database setup: {e}')
        db.create_all()

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except:
        return None

# Health check (REQUIRED FOR RENDER)
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

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
    
    # 🎮 ADD GAMIFICATION FIELDS
    user = User(username=username, email=email, points=0, level=1, badges='')
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
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid username or password!', 'danger')
        return redirect(url_for('auth'))

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
    
    # Count tasks
    all_count = Task.query.filter_by(user_id=current_user.id).count()
    complete_count = Task.query.filter_by(user_id=current_user.id, status='complete').count()
    incomplete_count = Task.query.filter_by(user_id=current_user.id, status='incomplete').count()
    
    # 🎮 GAMIFICATION DATA
    user_badges = current_user.get_badges()
    
    return render_template('dashboard.html', 
                         tasks=tasks,
                         filter_status=filter_status,
                         filter_priority=filter_priority,
                         all_count=all_count,
                         complete_count=complete_count,
                         incomplete_count=incomplete_count,
                         user_badges=user_badges)

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title')
    description = request.form.get('description')
    priority = request.form.get('priority', 'medium')
    due_date_str = request.form.get('due_date')
    
    # Parse due date
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
        except:
            pass
    
    task = Task(title=title, description=description, priority=priority, due_date=due_date, user_id=current_user.id)
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
    
    # 🎮 AWARD POINTS WHEN COMPLETING TASK
    if task.status == 'incomplete':
        task.status = 'complete'
        
        # Award points based on priority
        if task.priority == 'high':
            points = 30
            flash('🎉 Task completed! +30 points (High Priority)', 'success')
        elif task.priority == 'medium':
            points = 20
            flash('🎉 Task completed! +20 points (Medium Priority)', 'success')
        else:
            points = 10
            flash('🎉 Task completed! +10 points (Low Priority)', 'success')
        
        current_user.add_points(points)
        
        # 🏆 CHECK FOR BADGES
        completed_tasks = Task.query.filter_by(user_id=current_user.id, status='complete').count()
        
        if completed_tasks == 1:
            current_user.add_badge('First Step')
            flash('🏆 New Badge: First Step!', 'success')
        elif completed_tasks == 10:
            current_user.add_badge('Task Master')
            flash('🏆 New Badge: Task Master!', 'success')
        elif completed_tasks == 50:
            current_user.add_badge('Productivity Legend')
            flash('🏆 New Badge: Productivity Legend!', 'success')
        elif completed_tasks == 100:
            current_user.add_badge('Century Club')
            flash('🏆 New Badge: Century Club!', 'success')
    else:
        task.status = 'incomplete'
        flash('Task marked as incomplete.', 'info')
    
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
    # Get all user tasks
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    
    # Calculate statistics
    total_tasks = len(tasks)
    completed = len([t for t in tasks if t.status == 'complete'])
    incomplete = len([t for t in tasks if t.status == 'incomplete'])
    
    # Priority breakdown
    high_priority = len([t for t in tasks if t.priority == 'high'])
    medium_priority = len([t for t in tasks if t.priority == 'medium'])
    low_priority = len([t for t in tasks if t.priority == 'low'])
    
    # Overdue tasks
    now = datetime.utcnow()
    overdue = len([t for t in tasks if t.due_date and t.due_date < now and t.status == 'incomplete'])
    
    # 🎮 GAMIFICATION DATA
    user_badges = current_user.get_badges()
    
    return render_template('analytics.html',
                         total_tasks=total_tasks,
                         completed=completed,
                         incomplete=incomplete,
                         high_priority=high_priority,
                         medium_priority=medium_priority,
                         low_priority=low_priority,
                         overdue=overdue,
                         tasks=tasks,
                         user_badges=user_badges)

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
