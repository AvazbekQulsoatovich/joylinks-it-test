import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import pytz
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import base64
import os

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///joylinks_test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = False  # For development
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # For development

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, teacher, student
    full_name = db.Column(db.String(100), nullable=False)
    
    # Relationships
    teacher_profile = db.relationship('Teacher', backref='user', uselist=False)
    student_profile = db.relationship('Student', backref='user', uselist=False)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    
    # Relationships
    groups = db.relationship('Group', backref='teacher', lazy=True)
    course = db.relationship('Course', backref='teachers', lazy=True)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    
    # Relationships
    students = db.relationship('Student', backref='group', lazy=True)
    tests = db.relationship('Test', backref='group', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    
    # Relationships
    results = db.relationship('TestResult', backref='student', lazy=True)

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)  
    duration_minutes = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    questions = db.relationship('Question', backref='test', lazy=True, cascade='all, delete-orphan')
    results = db.relationship('TestResult', backref='test', lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)  # A, B, C, or D

class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers = db.Column(db.Text)  # JSON string of student answers

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Role-based access control decorators
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Kirish taqiqlangan. Admin huquqlari kerak.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'teacher':
            flash('Kirish taqiqlangan. O\'qituvchi huquqlari kerak.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            flash('Kirish taqiqlangan. O\'quvchi huquqlari kerak.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        logger.info(f"🔍 Login attempt: username={username}")
        
        user = User.query.filter_by(username=username).first()
        
        logger.info(f"🔍 User found: {user is not None}")
        if user:
            logger.info(f"🔍 User role: {user.role}")
            logger.info(f"🔍 Password check: {check_password_hash(user.password_hash, password)}")
        
        if user and check_password_hash(user.password_hash, password):
            logger.info(f"✅ Login successful for {user.full_name}")
            login_user(user)
            session.permanent = True
            flash(f'Xush kelibsiz, {user.full_name}! Muvaffaqiyatli kirish!', 'success')
            
            # Debug info
            logger.info(f"🔐 User logged in: {user.full_name} ({user.role})")
            logger.info(f"🔐 Current user after login: {current_user.is_authenticated if current_user else 'No current_user'}")
            logger.info(f"🔐 Session data: {dict(session)}")
            
            if user.role == 'admin':
                logger.info("👑 Redirecting to admin dashboard")
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'teacher':
                logger.info("👨‍🏫 Redirecting to teacher dashboard")
                return redirect(url_for('teacher_dashboard'))
            elif user.role == 'student':
                logger.info("👨‍🎓 Redirecting to student dashboard")
                return redirect(url_for('student_dashboard'))
        else:
            logger.error("❌ Invalid login attempt")
            flash('Noto\'g\'ri login yoki parol', 'danger')
    
    return render_template('login_modern.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Siz tizimdan chiqdingiz.', 'info')
    return redirect(url_for('login'))

# Admin Routes
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    total_students = Student.query.count()
    total_teachers = Teacher.query.count()
    total_courses = Course.query.count()
    total_tests = Test.query.count()
    total_groups = Group.query.count()
    
    # Toshkent vaqtini olish (UTC+5)
    uzbekistan_tz = pytz.timezone('Asia/Tashkent')
    current_time = datetime.now(uzbekistan_tz)
    
    return render_template('admin/dashboard_modern.html', 
                         total_students=total_students,
                         total_teachers=total_teachers,
                         total_courses=total_courses,
                         total_tests=total_tests,
                         total_groups=total_groups,
                         current_time=current_time)

@app.route('/admin/courses')
@admin_required
def admin_courses():
    courses = Course.query.all()
    return render_template('admin/courses_modern.html', courses=courses)

@app.route('/admin/courses/add', methods=['GET', 'POST'])
@admin_required
def admin_add_course():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        course = Course(name=name, description=description)
        db.session.add(course)
        db.session.commit()
        
        flash('Kurs muvaffaqiyatli qo\'shildi!', 'success')
        return redirect(url_for('admin_courses'))
    
    return render_template('admin/add_course_modern.html')

@app.route('/admin/courses/edit/<int:course_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if request.method == 'POST':
        course.name = request.form.get('name')
        course.description = request.form.get('description')
        
        db.session.commit()
        flash('Kurs muvaffaqiyatli yangilandi!', 'success')
        return redirect(url_for('admin_courses'))
    
    return render_template('admin/edit_course_modern.html', course=course)

@app.route('/admin/courses/delete/<int:course_id>', methods=['POST'])
@admin_required
def admin_delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash('Kurs muvaffaqiyatli o\'chirildi!', 'success')
    return redirect(url_for('admin_courses'))

@app.route('/admin/groups/add', methods=['GET', 'POST'])
@admin_required
def admin_add_group():
    if request.method == 'POST':
        name = request.form.get('name')
        teacher_id = request.form.get('teacher_id')
        
        group = Group(name=name, teacher_id=teacher_id)
        db.session.add(group)
        db.session.commit()
        
        flash('Guruh muvaffaqiyatli qo\'shildi!', 'success')
        return redirect(url_for('admin_groups'))
    
    teachers = db.session.query(Teacher, User, Course).join(User).join(Course).all()
    return render_template('admin/add_group_modern.html', teachers=teachers)

@app.route('/admin/groups/edit/<int:group_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_group(group_id):
    group = Group.query.get_or_404(group_id)
    
    if request.method == 'POST':
        group.name = request.form.get('name')
        group.teacher_id = request.form.get('teacher_id')
        db.session.commit()
        flash('Guruh muvaffaqiyatli yangilandi!', 'success')
        return redirect(url_for('admin_groups'))
    
    teachers = db.session.query(Teacher, User, Course).join(User).join(Course).all()
    return render_template('admin/edit_group_modern.html', group=group, teachers=teachers)

@app.route('/admin/groups/delete/<int:group_id>', methods=['POST'])
@admin_required
def admin_delete_group(group_id):
    group = Group.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    flash('Guruh muvaffaqiyatli o\'chirildi!', 'success')
    return redirect(url_for('admin_groups'))

@app.route('/admin/groups')
@admin_required
def admin_groups():
    groups = db.session.query(Group, Teacher, User, Course).join(Teacher, Group.teacher_id == Teacher.id).join(User, Teacher.user_id == User.id).join(Course, Teacher.course_id == Course.id).all()
    return render_template('admin/groups_modern.html', groups=groups)

@app.route('/admin/tests/add', methods=['GET', 'POST'])
@admin_required
def admin_add_test():
    if request.method == 'POST':
        title = request.form.get('title')
        group_id = request.form.get('group_id')
        start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')
        duration_minutes = int(request.form.get('duration_minutes'))
        
        test = Test(
            title=title,
            group_id=group_id,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes
        )
        db.session.add(test)
        db.session.flush()  # Get test ID
        
        # Add questions
        question_count = int(request.form.get('question_count'))
        for i in range(1, question_count + 1):
            question = Question(
                test_id=test.id,
                question_text=request.form.get(f'question_{i}_text'),
                option_a=request.form.get(f'question_{i}_a'),
                option_b=request.form.get(f'question_{i}_b'),
                option_c=request.form.get(f'question_{i}_c'),
                option_d=request.form.get(f'question_{i}_d'),
                correct_answer=request.form.get(f'question_{i}_correct')
            )
            db.session.add(question)
        
        db.session.commit()
        flash('Test muvaffaqiyatli qo\'shildi!', 'success')
        return redirect(url_for('admin_tests'))
    
    groups = db.session.query(Group, Teacher, User).join(Teacher, Group.teacher_id == Teacher.id).join(User, Teacher.user_id == User.id).all()
    return render_template('admin/add_test_modern.html', groups=groups)

@app.route('/admin/tests')
@admin_required
def admin_tests():
    tests = db.session.query(Test, Group, Teacher, User).join(Group, Test.group_id == Group.id).join(Teacher, Group.teacher_id == Teacher.id).join(User, Teacher.user_id == User.id).all()
    return render_template('admin/tests_modern.html', tests=tests, current_time=datetime.utcnow())

@app.route('/admin/tests/delete/<int:test_id>', methods=['POST'])
@admin_required
def admin_delete_test(test_id):
    test = Test.query.get_or_404(test_id)
    db.session.delete(test)
    db.session.commit()
    flash('Test muvaffaqiyatli o\'chirildi!', 'success')
    return redirect(url_for('admin_tests'))

@app.route('/admin/students/add', methods=['GET', 'POST'])
@admin_required
def admin_add_student():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        group_id = request.form.get('group_id')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Ushbu username mavjud!', 'danger')
            return redirect(url_for('admin_add_student'))
        
        # Create user
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='student',
            full_name=full_name
        )
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create student profile
        student = Student(user_id=user.id, group_id=group_id)
        db.session.add(student)
        db.session.commit()
        
        flash('O\'quvchi muvaffaqiyatli qo\'shildi!', 'success')
        return redirect(url_for('admin_students'))
    
    groups = db.session.query(Group, Teacher, User).join(Teacher, Group.teacher_id == Teacher.id).join(User, Teacher.user_id == User.id).all()
    return render_template('admin/add_student_modern.html', groups=groups)

@app.route('/admin/students/edit/<int:student_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_student(student_id):
    from sqlalchemy.orm import aliased
    
    student_user = aliased(User, name='student_user')
    teacher_user = aliased(User, name='teacher_user')
    
    student = db.session.query(Student, student_user, Group, Teacher, teacher_user)\
        .join(student_user, Student.user_id == student_user.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Teacher, Group.teacher_id == Teacher.id)\
        .join(teacher_user, Teacher.user_id == teacher_user.id)\
        .filter(Student.id == student_id)\
        .first_or_404()
    
    student_obj, user_obj, group_obj, teacher_obj, teacher_user_obj = student
    
    if request.method == 'POST':
        user_obj.full_name = request.form.get('full_name')
        user_obj.username = request.form.get('username')
        student_obj.group_id = request.form.get('group_id')
        
        password = request.form.get('password')
        if password:  # Only update password if provided
            user_obj.password_hash = generate_password_hash(password)
        
        db.session.commit()
        flash('O\'quvchi ma\'lumotlari muvaffaqiyatli yangilandi!', 'success')
        return redirect(url_for('admin_students'))
    
    groups = db.session.query(Group, Teacher, User).join(Teacher, Group.teacher_id == Teacher.id).join(User, Teacher.user_id == User.id).all()
    return render_template('admin/edit_student_modern.html', student=student_obj, user=user_obj, groups=groups)

@app.route('/admin/students/delete/<int:student_id>', methods=['POST'])
@admin_required
def admin_delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    user = student.user
    
    db.session.delete(student)
    db.session.delete(user)
    db.session.commit()
    flash('O\'quvchi muvaffaqiyatli o\'chirildi!', 'success')
    return redirect(url_for('admin_students'))

@app.route('/admin/teachers')
@admin_required
def admin_teachers():
    teachers = db.session.query(Teacher, User, Course).join(User).join(Course).all()
    return render_template('admin/teachers_modern.html', teachers=teachers)

@app.route('/admin/teachers/add', methods=['GET', 'POST'])
@admin_required
def admin_add_teacher():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        course_id = request.form.get('course_id')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Ushbu login allaqachon mavjud!', 'danger')
            return redirect(url_for('admin_add_teacher'))
        
        # Create user
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            role='teacher',
            full_name=full_name
        )
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create teacher profile
        teacher = Teacher(user_id=user.id, course_id=course_id)
        db.session.add(teacher)
        db.session.commit()
        
        flash("O'qituvchi muvaffaqiyatli qo'shildi!", 'success')
        return redirect(url_for('admin_teachers'))
    
    courses = Course.query.all()
    return render_template('admin/add_teacher_modern.html', courses=courses)

@app.route('/admin/teachers/edit/<int:teacher_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    
    if request.method == 'POST':
        teacher.user.full_name = request.form.get('full_name')
        teacher.course_id = request.form.get('course_id')
        
        password = request.form.get('password')
        if password:  # Only update password if provided
            teacher.user.password_hash = generate_password_hash(password)
        
        db.session.commit()
        flash("O'qituvchi ma'lumotlari muvaffaqiyatli yangilandi!", 'success')
        return redirect(url_for('admin_teachers'))
    
    courses = Course.query.all()
    return render_template('admin/edit_teacher_modern.html', teacher=teacher, courses=courses)

@app.route('/admin/teachers/delete/<int:teacher_id>', methods=['POST'])
@admin_required
def admin_delete_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    user = teacher.user
    
    db.session.delete(teacher)
    db.session.delete(user)
    db.session.commit()
    flash("O'qituvchi muvaffaqiyatli o'chirildi!", 'success')
    return redirect(url_for('admin_teachers'))

@app.route('/admin/teachers/view/<int:teacher_id>')
@admin_required
def admin_view_teacher(teacher_id):
    teacher = db.session.query(Teacher, User, Course).join(User).join(Course).filter(Teacher.id == teacher_id).first_or_404()
    teacher_obj, user_obj, course_obj = teacher
    
    # Get teacher's groups and students
    groups = Group.query.filter_by(teacher_id=teacher_id).all()
    students = db.session.query(Student, User, Group).join(User).join(Group).filter(Group.teacher_id == teacher_id).all()
    
    return render_template('admin/view_teacher_modern.html', teacher=teacher_obj, user=user_obj, course=course_obj, groups=groups, students=students)

@app.route('/admin/students')
@admin_required
def admin_students():
    from sqlalchemy.orm import aliased
    
    # Create aliases for User table
    student_user = aliased(User, name='student_user')
    teacher_user = aliased(User, name='teacher_user')
    
    # Query students with their results
    students_data = db.session.query(Student, student_user, Group, Teacher, teacher_user, Course)\
        .join(student_user, Student.user_id == student_user.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Teacher, Group.teacher_id == Teacher.id)\
        .join(teacher_user, Teacher.user_id == teacher_user.id)\
        .join(Course, Teacher.course_id == Course.id)\
        .options(db.joinedload(Student.results))\
        .all()
    
    # Debug: Print query results to check structure
    print(f"DEBUG: students_data count = {len(students_data)}")
    if students_data:
        print(f"DEBUG: First student data structure: {type(students_data[0])}")
        print(f"DEBUG: First student data: {students_data[0]}")
    
    # Format data for template
    students = []
    for student_obj, user_obj, group_obj, teacher_obj, course_obj in students_data:
        students.append({
            'student': student_obj,
            'user': user_obj,
            'group': group_obj,
            'teacher': teacher_obj,
            'course': course_obj
        })
    
    return render_template('admin/students_modern.html', students=students)

@app.route('/admin/students/view/<int:student_id>')
@admin_required
def admin_view_student(student_id):
    from sqlalchemy.orm import aliased
    
    student_user = aliased(User, name='student_user')
    teacher_user = aliased(User, name='teacher_user')
    
    student = db.session.query(Student, student_user, Group, Teacher, teacher_user, Course)\
        .join(student_user, Student.user_id == student_user.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Teacher, Group.teacher_id == Teacher.id)\
        .join(teacher_user, Teacher.user_id == teacher_user.id)\
        .join(Course, Teacher.course_id == Course.id)\
        .options(db.joinedload(Student.results))\
        .filter(Student.id == student_id)\
        .first_or_404()
    
    return render_template('admin/view_student_modern.html', student=student)

@app.route('/admin/results')
@admin_required
def admin_results():
    results = db.session.query(TestResult, Student, User, Group, Test)\
        .join(Student, TestResult.student_id == Student.id)\
        .join(User, Student.user_id == User.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Test, TestResult.test_id == Test.id)\
        .all()
    return render_template('admin/results_modern.html', results=results)

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    # Get data for analytics
    test_results = db.session.query(TestResult, Test, Group)\
        .join(Test, TestResult.test_id == Test.id)\
        .join(Group, Test.group_id == Group.id)\
        .all()
    
    # Prepare data for visualization
    data = []
    group_scores = {}
    pass_count = 0
    fail_count = 0
    
    for result, test, group in test_results:
        data.append({
            'student_name': result.student.user.full_name,
            'group_name': group.name,
            'test_title': test.title,
            'score': result.score,
            'total_questions': result.total_questions,
            'percentage': result.percentage,
            'submitted_at': result.submitted_at
        })
        
        # Group statistics
        if group.name not in group_scores:
            group_scores[group.name] = []
        group_scores[group.name].append(result.percentage)
        
        # Pass/Fail statistics
        if result.percentage >= 60:
            pass_count += 1
        else:
            fail_count += 1
    
    # Generate simple text-based statistics
    charts = {}
    if data:
        # Group averages
        group_averages = {}
        for group_name, scores in group_scores.items():
            group_averages[group_name] = sum(scores) / len(scores)
        
        charts['group_averages'] = group_averages
        charts['pass_fail'] = {'pass': pass_count, 'fail': fail_count}
        charts['total_results'] = len(data)
        charts['average_score'] = sum([d['percentage'] for d in data]) / len(data)
    
    return render_template('admin/analytics_modern.html', charts=charts)

# Teacher Routes
@app.route('/teacher/dashboard')
@teacher_required
def teacher_dashboard():
    from sqlalchemy.orm import joinedload
    
    try:
        print(f"🔍 Current user: {current_user.id}, Username: {current_user.username}, Role: {current_user.role}")
        print(f"🔍 Is authenticated: {current_user.is_authenticated}")
        print(f"🔍 User object type: {type(current_user)}")
        
        # Check if user has teacher profile
        teacher = db.session.query(Teacher)\
            .options(joinedload(Teacher.user))\
            .options(joinedload(Teacher.course))\
            .filter_by(user_id=current_user.id)\
            .first()
        
        print(f"🔍 Teacher found: {teacher is not None}")
        if teacher:
            print(f"🔍 Teacher ID: {teacher.id}, User ID: {teacher.user_id}")
            print(f"🔍 Teacher user role: {teacher.user.role}")
        
        if not teacher:
            print("❌ Teacher profile not found!")
            flash('O\'qituvchi profili topilmadi! Admin bilan bog\'laning.', 'danger')
            return redirect(url_for('login'))
        
        groups = db.session.query(Group).options(joinedload(Group.teacher).joinedload(Teacher.course)).filter_by(teacher_id=teacher.id).all()
        
        # Har bir guruh uchun o'quvchilar sonini hisoblash
        for group in groups:
            group.students = Student.query.filter_by(group_id=group.id).all()
        
        students_count = Student.query.filter(Student.group_id.in_([g.id for g in groups])).count()
        tests_count = Test.query.filter(Test.group_id.in_([g.id for g in groups])).count()
        
        print(f"✅ Groups: {len(groups)}, Students: {students_count}, Tests: {tests_count}")
        
        return render_template('teacher/dashboard_modern.html', 
                             groups=groups,
                             students_count=students_count,
                             tests_count=tests_count,
                             teacher=teacher)
    except Exception as e:
        print(f"❌ Error in teacher dashboard: {e}")
        import traceback
        traceback.print_exc()
        flash('Panelni yuklashda xatolik!', 'danger')
        return redirect(url_for('login'))

# Teacher groups removed - now managed by admin

# Teacher students management removed - now managed by admin

# Teacher tests management removed - now managed by admin

@app.route('/teacher/results')
@teacher_required
def teacher_results():
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    results = db.session.query(TestResult, Student, User, Group, Test)\
        .join(Student, TestResult.student_id == Student.id)\
        .join(User, Student.user_id == User.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Test, TestResult.test_id == Test.id)\
        .filter(Group.teacher_id == teacher.id)\
        .all()
    return render_template('teacher/results_modern.html', results=results)

@app.route('/teacher/group/<int:group_id>')
@teacher_required
def teacher_group_students(group_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    group = Group.query.filter_by(id=group_id, teacher_id=teacher.id).first_or_404()
    
    # Guruhdagi o'quvchilar
    students = db.session.query(Student, User)\
        .join(User, Student.user_id == User.id)\
        .filter(Student.group_id == group_id)\
        .all()
    
    # Guruhdagi testlar
    tests = Test.query.filter_by(group_id=group_id).all()
    
    return render_template('teacher/group_students_modern.html', 
                         group=group, 
                         students=students, 
                         tests=tests)

# Student Routes
@app.route('/student/dashboard')
@student_required
def student_dashboard():
    try:
        # Debug print
        print(f"Current user ID: {current_user.id}, Username: {current_user.username}, Role: {current_user.role}")
        
        student = db.session.query(Student).filter_by(user_id=current_user.id).first()
        if not student:
            print("❌ Student profile not found for current user!")
            flash('O\'quvchi profili topilmadi!', 'danger')
            return redirect(url_for('login'))
        
        print(f"✅ Student found: {student.user.username}")
        print(f"Student group: {student.group.name if student.group else 'None'}")
        print(f"Student teacher: {student.group.teacher.user.full_name if student.group and student.group.teacher else 'None'}")
        
        # Test results (tugatilgan testlar)
        results = db.session.query(TestResult, Test).join(Test, TestResult.test_id == Test.id).filter(TestResult.student_id == student.id).order_by(TestResult.submitted_at.desc()).all()
        print(f"Test results count: {len(results)}")
        
        # Available tests (mavjud testlar)
        available_tests = Test.query.filter_by(group_id=student.group_id).all()
        print(f"Available tests count: {len(available_tests)}")
        
        # Calculate average score
        average_score = 0
        if results:
            average_score = sum(result[0].percentage for result in results) / len(results)
        
        # Toshkent vaqtini olish (UTC+5)
        uzbekistan_tz = pytz.timezone('Asia/Tashkent')
        current_time = datetime.now(uzbekistan_tz)
        
        return render_template('student/dashboard_modern.html', student=student, results=results, available_tests=available_tests, current_time=current_time, average_score=average_score)
    except Exception as e:
        print(f"❌ Error in student dashboard: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Panelni yuklashda xatolik: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/student/test/<int:test_id>')
@student_required
def student_take_test(test_id):
    student = Student.query.filter_by(user_id=current_user.id).first()
    test = Test.query.get_or_404(test_id)
    
    # Check if student belongs to the test's group
    if student.group_id != test.group_id:
        flash('Siz bu testni topshirishga ruxsat etilmagansiz.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    # Check if test is within time window
    now = datetime.utcnow()
    if now < test.start_time:
        flash('Test hali boshlanmagan.', 'warning')
        return redirect(url_for('student_dashboard'))
    elif now > test.end_time:
        flash('Test muddati tugagan.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Check if student already took the test
    existing_result = TestResult.query.filter_by(student_id=student.id, test_id=test.id).first()
    if existing_result:
        flash('Siz bu testni allaqachon topshirgansiz.', 'info')
        return redirect(url_for('student_dashboard'))
    
    questions = Question.query.filter_by(test_id=test.id).all()
    return render_template('student/take_test_modern.html', test=test, questions=questions)

@app.route('/student/test/<int:test_id>/submit', methods=['POST'])
@student_required
def student_submit_test(test_id):
    print(f"🔍 DEBUG: Submit route called for test_id={test_id}")
    
    try:
        print(f"🔍 DEBUG: Test submit started for test_id={test_id}")
        
        student = Student.query.filter_by(user_id=current_user.id).first()
        test = Test.query.get_or_404(test_id)
        
        print(f"🔍 DEBUG: Student={student.user.username}, Test={test.title}")
        
        # Check if student already took the test
        existing_result = TestResult.query.filter_by(student_id=student.id, test_id=test.id).first()
        if existing_result:
            print("❌ DEBUG: Student already took this test")
            flash('Siz bu testni allaqachon topshirgansiz.', 'danger')
            return redirect(url_for('student_dashboard'))
        
        # Check if test is still within time window
        now = datetime.utcnow()
        print(f"🔍 DEBUG: Now={now}, Test end={test.end_time}")
        
        if now > test.end_time:
            print("❌ DEBUG: Test time expired")
            flash('Testni topshirish muddati tugagan.', 'danger')
            return redirect(url_for('student_dashboard'))
        
        # Calculate score
        questions = Question.query.filter_by(test_id=test.id).all()
        print(f"🔍 DEBUG: Found {len(questions)} questions")
        
        correct_count = 0
        answers = {}
        
        for question in questions:
            student_answer = request.form.get(f'question_{question.id}')
            answers[str(question.id)] = student_answer
            print(f"🔍 DEBUG: Question {question.id}, Student answer={student_answer}, Correct={question.correct_answer}")
            
            if student_answer == question.correct_answer:
                correct_count += 1
        
        print(f"🔍 DEBUG: Correct answers={correct_count}/{len(questions)}")
        
        # Save result
        result = TestResult(
            student_id=student.id,
            test_id=test.id,
            score=correct_count,
            total_questions=len(questions),
            percentage=(correct_count / len(questions)) * 100,
            answers=str(answers)
        )
        db.session.add(result)
        db.session.commit()
        
        print("✅ DEBUG: Test result saved successfully")
        print("🔍 DEBUG: About to redirect to dashboard")
        
        flash(f'Test muvaffaqiyatli topshirildi! Ballingiz: {correct_count}/{len(questions)} ({result.percentage:.1f}%)', 'success')
        
        redirect_url = url_for('student_dashboard')
        print(f"🔍 DEBUG: Redirect URL: {redirect_url}")
        
        return redirect(redirect_url)
        
    except Exception as e:
        print(f"❌ DEBUG: Error in test submit: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Testni topshirishda xatolik: {str(e)}', 'danger')
        return redirect(url_for('student_dashboard'))
    
    print("❌ DEBUG: This should not be reached!")

# PDF Export Routes
@app.route('/admin/results/pdf/<int:result_id>')
@admin_required
def admin_export_result_pdf(result_id):
    result = TestResult.query.get_or_404(result_id)
    
    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "Test Result Report")
    
    # Student Information
    p.setFont("Helvetica", 12)
    p.drawString(100, 700, f"Student: {result.student.user.full_name}")
    p.drawString(100, 680, f"Group: {result.student.group.name}")
    p.drawString(100, 660, f"Test: {result.test.title}")
    
    # Score Information
    p.drawString(100, 620, f"Score: {result.score}/{result.total_questions}")
    p.drawString(100, 600, f"Percentage: {result.percentage:.1f}%")
    p.drawString(100, 580, f"Submitted: {result.submitted_at.strftime('%Y-%m-%d %H:%M')}")
    
    p.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name=f'result_{result.id}.pdf', mimetype='application/pdf')

@app.route('/teacher/results/pdf/<int:result_id>')
@teacher_required
def teacher_export_result_pdf(result_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    result = db.session.query(TestResult, Student, User, Group, Test)\
        .join(Student, TestResult.student_id == Student.id)\
        .join(User, Student.user_id == User.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Test, TestResult.test_id == Test.id)\
        .filter(TestResult.id == result_id, Group.teacher_id == teacher.id)\
        .first_or_404()
    result_obj, student_obj, user_obj, group_obj, test_obj = result
    
    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Title
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "Test Result Report")
    
    # Student Information
    p.setFont("Helvetica", 12)
    p.drawString(100, 700, f"Student: {user_obj.full_name}")
    p.drawString(100, 680, f"Group: {group_obj.name}")
    p.drawString(100, 660, f"Test: {test_obj.title}")
    
    # Score Information
    p.drawString(100, 620, f"Score: {result_obj.score}/{result_obj.total_questions}")
    p.drawString(100, 600, f"Percentage: {result_obj.percentage:.1f}%")
    p.drawString(100, 580, f"Submitted: {result_obj.submitted_at.strftime('%Y-%m-%d %H:%M')}")
    
    p.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name=f'result_{result_obj.id}.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create default admin if not exists
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                password_hash=generate_password_hash('secure_admin_password_2024'),
                role='admin',
                full_name='System Administrator'
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created: username=admin")
    
    # Production settings with debug mode for better error logging
    app.run(
        host='0.0.0.0',  # Allow external connections
        port=5000,
        debug=True,  # Enable debug mode
        threaded=True  # Better for production
    )
