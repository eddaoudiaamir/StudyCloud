from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
from sqlalchemy import inspect
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///studycloud.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for Render's postgres:// URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

# 📧 EMAIL CONFIGURATION (Gmail SMTP)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')  # Your Gmail
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')  # Your Gmail App Password
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth'
mail = Mail(app)

# Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
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
    
    # 🔔 NOTIFICATION METHODS
    def unread_notification_count(self):
        return self.notifications.filter_by(read=False).count()

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
    
    # 🔔 NOTIFICATION TRACKING
    notified_1day = db.Column(db.Boolean, default=False)
    notified_1hour = db.Column(db.Boolean, default=False)
    notified_10min = db.Column(db.Boolean, default=False)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    message = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

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
            
            # Add notification tracking columns
            if 'notified_1day' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(db.text('ALTER TABLE tasks ADD COLUMN notified_1day BOOLEAN DEFAULT FALSE'))
                    conn.execute(db.text('ALTER TABLE tasks ADD COLUMN notified_1hour BOOLEAN DEFAULT FALSE'))
                    conn.execute(db.text('ALTER TABLE tasks ADD COLUMN notified_10min BOOLEAN DEFAULT FALSE'))
                    conn.commit()
                    print('✅ Notification tracking columns added!')
        
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

# 📧 EMAIL NOTIFICATION FUNCTION
def send_email_notification(user_email, task_title, time_left):
    try:
        msg = Message(
            subject=f'⏰ Task Reminder: {task_title}',
            recipients=[user_email]
        )
        msg.body = f"""
Hello!

This is a reminder that your task is due soon:

📋 Task: {task_title}
⏰ Time Left: {time_left}

Don't forget to complete it on time!

Best regards,
StudyCloud Team
        """
        msg.html = f"""
<html>
<body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h2 style="color: #6366f1; margin-bottom: 20px;">⏰ Task Reminder</h2>
        <p style="font-size: 16px; color: #333; line-height: 1.6;">Hello!</p>
        <p style="font-size: 16px; color: #333; line-height: 1.6;">This is a reminder that your task is due soon:</p>
        
        <div style="background: linear-gradient(135deg, #6366f1, #a855f7); padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p style="color: white; margin: 0; font-size: 14px;">📋 <strong>Task:</strong></p>
            <p style="color: white; margin: 5px 0 15px 0; font-size: 18px; font-weight: bold;">{task_title}</p>
            <p style="color: white; margin: 0; font-size: 14px;">⏰ <strong>Time Left:</strong></p>
            <p style="color: white; margin: 5px 0 0 0; font-size: 18px; font-weight: bold;">{time_left}</p>
        </div>
        
        <p style="font-size: 16px; color: #333; line-height: 1.6;">Don't forget to complete it on time!</p>
        
        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
        
        <p style="font-size: 14px; color: #999; text-align: center;">Best regards,<br><strong>StudyCloud Team</strong></p>
    </div>
</body>
</html>
        """
        mail.send(msg)
        print(f'✅ Email sent to {user_email} for task: {task_title}')
        return True
    except Exception as e:
        print(f'❌ Email send error: {e}')
        return False

# 🔔 CHECK TASKS AND SEND NOTIFICATIONS
def check_task_notifications():
    with app.app_context():
        print('🔍 Checking for task notifications...')
        now = datetime.utcnow()
        
        # Get all incomplete tasks with due dates
        tasks = Task.query.filter(
            Task.status == 'incomplete',
            Task.due_date.isnot(None)
        ).all()
        
        for task in tasks:
            user = User.query.get(task.user_id)
            if not user:
                continue
            
            time_until_due = task.due_date - now
            
            # 1 DAY BEFORE (24 hours)
            if not task.notified_1day and timedelta(hours=23, minutes=50) <= time_until_due <= timedelta(hours=24, minutes=10):
                send_email_notification(user.email, task.title, "1 day")
                notif = Notification(
                    user_id=user.id,
                    task_id=task.id,
                    message=f"📋 Task '{task.title}' is due in 1 day!"
                )
                db.session.add(notif)
                task.notified_1day = True
                print(f'📧 1 day notification sent for: {task.title}')
            
            # 1 HOUR BEFORE
            elif not task.notified_1hour and timedelta(minutes=50) <= time_until_due <= timedelta(hours=1, minutes=10):
                send_email_notification(user.email, task.title, "1 hour")
                notif = Notification(
                    user_id=user.id,
                    task_id=task.id,
                    message=f"⚠️ Task '{task.title}' is due in 1 hour!"
                )
                db.session.add(notif)
                task.notified_1hour = True
                print(f'📧 1 hour notification sent for: {task.title}')
            
            # 10 MINUTES BEFORE
            elif not task.notified_10min and timedelta(minutes=5) <= time_until_due <= timedelta(minutes=15):
                send_email_notification(user.email, task.title, "10 minutes")
                notif = Notification(
                    user_id=user.id,
                    task_id=task.id,
                    message=f"🚨 Task '{task.title}' is due in 10 minutes!"
                )
                db.session.add(notif)
                task.notified_10min = True
                print(f'📧 10 min notification sent for: {task.title}')
        
        db.session.commit()

# 🕐 SCHEDULER - Run every 5 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_task_notifications, trigger="interval", minutes=5)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

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
    
    all_count = Task.query.filter_by(user_id=current_user.id).count()
    complete_count = Task.query.filter_by(user_id=current_user.id, status='complete').count()
    incomplete_count = Task.query.filter_by(user_id=current_user.id, status='incomplete').count()
    
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
    
    if task.status == 'incomplete':
        task.status = 'complete'
        
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

# 🔔 NOTIFICATION ROUTES
@app.route('/notifications')
@login_required
def notifications():
    notifs = current_user.notifications.order_by(Notification.timestamp.desc()).all()
    return render_template('notifications.html', notifications=notifs)

@app.route('/api/notifications/count')
@login_required
def notification_count():
    count = current_user.unread_notification_count()
    return jsonify({'count': count})

@app.route('/api/notifications/recent')
@login_required
def recent_notifications():
    notifs = current_user.notifications.order_by(Notification.timestamp.desc()).limit(5).all()
    return jsonify({
        'notifications': [{
            'id': n.id,
            'message': n.message,
            'timestamp': n.timestamp.strftime('%Y-%m-%d %H:%M'),
            'read': n.read
        } for n in notifs]
    })

@app.route('/notifications/mark_read/<int:notif_id>')
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id == current_user.id:
        notif.read = True
        db.session.commit()
    return redirect(url_for('notifications'))

@app.route('/notifications/mark_all_read')
@login_required
def mark_all_read():
    current_user.notifications.filter_by(read=False).update({'read': True})
    db.session.commit()
    return redirect(url_for('notifications'))

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
