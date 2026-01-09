from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import base64
import os
from functools import wraps
import psycopg2  # PostgreSQL support

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:password@localhost/education_system'  # PostgreSQL database URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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
    title = db.Column(db.String(100), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
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
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'teacher':
            flash('Access denied. Teacher privileges required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            flash('Access denied. Student privileges required.', 'danger')
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
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!', 'success')
            
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            elif user.role == 'student':
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Admin Routes
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    total_students = Student.query.count()
    total_teachers = Teacher.query.count()
    total_courses = Course.query.count()
    total_tests = Test.query.count()
    
    return render_template('admin/dashboard.html', 
                         total_students=total_students,
                         total_teachers=total_teachers,
                         total_courses=total_courses,
                         total_tests=total_tests,
                         current_time=datetime.utcnow())

@app.route('/admin/courses')
@admin_required
def admin_courses():
    courses = Course.query.all()
    return render_template('admin/courses.html', courses=courses)

@app.route('/admin/courses/add', methods=['GET', 'POST'])
@admin_required
def admin_add_course():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        course = Course(name=name, description=description)
        db.session.add(course)
        db.session.commit()
        
        flash('Course added successfully!', 'success')
        return redirect(url_for('admin_courses'))
    
    return render_template('admin/add_course.html')

@app.route('/admin/courses/edit/<int:course_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if request.method == 'POST':
        course.name = request.form.get('name')
        course.description = request.form.get('description')
        
        db.session.commit()
        flash('Course updated successfully!', 'success')
        return redirect(url_for('admin_courses'))
    
    return render_template('admin/edit_course.html', course=course)

@app.route('/admin/courses/delete/<int:course_id>', methods=['POST'])
@admin_required
def admin_delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted successfully!', 'success')
    return redirect(url_for('admin_courses'))

@app.route('/admin/teachers')
@admin_required
def admin_teachers():
    teachers = db.session.query(Teacher, User, Course).join(User).join(Course).all()
    return render_template('admin/teachers.html', teachers=teachers)

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
            flash('Username already exists!', 'danger')
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
        
        flash('Teacher added successfully!', 'success')
        return redirect(url_for('admin_teachers'))
    
    courses = Course.query.all()
    return render_template('admin/add_teacher.html', courses=courses)

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
        flash('Teacher updated successfully!', 'success')
        return redirect(url_for('admin_teachers'))
    
    courses = Course.query.all()
    return render_template('admin/edit_teacher.html', teacher=teacher, courses=courses)

@app.route('/admin/teachers/delete/<int:teacher_id>', methods=['POST'])
@admin_required
def admin_delete_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    user = teacher.user
    
    db.session.delete(teacher)
    db.session.delete(user)
    db.session.commit()
    flash('Teacher deleted successfully!', 'success')
    return redirect(url_for('admin_teachers'))

@app.route('/admin/students')
@admin_required
def admin_students():
    from sqlalchemy.orm import aliased
    
    # Create aliases for User table
    student_user = aliased(User, name='student_user')
    teacher_user = aliased(User, name='teacher_user')
    
    students = db.session.query(Student, student_user, Group, Teacher, teacher_user, Course)\
        .join(student_user, Student.user_id == student_user.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Teacher, Group.teacher_id == Teacher.id)\
        .join(teacher_user, Teacher.user_id == teacher_user.id)\
        .join(Course, Teacher.course_id == Course.id)\
        .all()
    return render_template('admin/students.html', students=students)

@app.route('/admin/results')
@admin_required
def admin_results():
    results = db.session.query(TestResult, Student, User, Group, Test)\
        .join(Student, TestResult.student_id == Student.id)\
        .join(User, Student.user_id == User.id)\
        .join(Group, Student.group_id == Group.id)\
        .join(Test, TestResult.test_id == Test.id)\
        .all()
    return render_template('admin/results.html', results=results)

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
    
    return render_template('admin/analytics.html', charts=charts)

# Teacher Routes
@app.route('/teacher/dashboard')
@teacher_required
def teacher_dashboard():
    from sqlalchemy.orm import joinedload
    
    teacher = db.session.query(Teacher)\
        .options(joinedload(Teacher.user))\
        .options(joinedload(Teacher.course))\
        .filter_by(user_id=current_user.id)\
        .first()
    
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    students_count = Student.query.filter(Student.group_id.in_([g.id for g in groups])).count()
    tests_count = Test.query.filter(Test.group_id.in_([g.id for g in groups])).count()
    
    return render_template('teacher/dashboard.html', 
                         groups=groups,
                         students_count=students_count,
                         tests_count=tests_count)

@app.route('/teacher/groups')
@teacher_required
def teacher_groups():
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    return render_template('teacher/groups.html', groups=groups)

@app.route('/teacher/groups/add', methods=['GET', 'POST'])
@teacher_required
def teacher_add_group():
    if request.method == 'POST':
        name = request.form.get('name')
        teacher = Teacher.query.filter_by(user_id=current_user.id).first()
        
        group = Group(name=name, teacher_id=teacher.id)
        db.session.add(group)
        db.session.commit()
        
        flash('Group added successfully!', 'success')
        return redirect(url_for('teacher_groups'))
    
    return render_template('teacher/add_group.html')

@app.route('/teacher/groups/edit/<int:group_id>', methods=['GET', 'POST'])
@teacher_required
def teacher_edit_group(group_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    group = Group.query.filter_by(id=group_id, teacher_id=teacher.id).first_or_404()
    
    if request.method == 'POST':
        group.name = request.form.get('name')
        db.session.commit()
        flash('Group updated successfully!', 'success')
        return redirect(url_for('teacher_groups'))
    
    return render_template('teacher/edit_group.html', group=group)

@app.route('/teacher/groups/delete/<int:group_id>', methods=['POST'])
@teacher_required
def teacher_delete_group(group_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    group = Group.query.filter_by(id=group_id, teacher_id=teacher.id).first_or_404()
    
    db.session.delete(group)
    db.session.commit()
    flash('Group deleted successfully!', 'success')
    return redirect(url_for('teacher_groups'))

@app.route('/teacher/students')
@teacher_required
def teacher_students():
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    students = db.session.query(Student, User, Group).join(User).join(Group).filter(Group.teacher_id == teacher.id).all()
    return render_template('teacher/students.html', students=students, groups=groups)

@app.route('/teacher/students/add', methods=['GET', 'POST'])
@teacher_required
def teacher_add_student():
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        group_id = request.form.get('group_id')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return redirect(url_for('teacher_add_student'))
        
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
        
        flash('Student added successfully!', 'success')
        return redirect(url_for('teacher_students'))
    
    return render_template('teacher/add_student.html', groups=groups)

@app.route('/teacher/students/edit/<int:student_id>', methods=['GET', 'POST'])
@teacher_required
def teacher_edit_student(student_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    student = db.session.query(Student, User, Group).join(User).join(Group).filter(Student.id == student_id, Group.teacher_id == teacher.id).first_or_404()
    student_obj, user_obj, group_obj = student
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    
    if request.method == 'POST':
        user_obj.full_name = request.form.get('full_name')
        student_obj.group_id = request.form.get('group_id')
        
        password = request.form.get('password')
        if password:  # Only update password if provided
            user_obj.password_hash = generate_password_hash(password)
        
        db.session.commit()
        flash('Student updated successfully!', 'success')
        return redirect(url_for('teacher_students'))
    
    return render_template('teacher/edit_student.html', student=student_obj, user=user_obj, groups=groups)

@app.route('/teacher/students/delete/<int:student_id>', methods=['POST'])
@teacher_required
def teacher_delete_student(student_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    student = db.session.query(Student, User, Group).join(User).join(Group).filter(Student.id == student_id, Group.teacher_id == teacher.id).first_or_404()
    student_obj, user_obj, group_obj = student
    
    db.session.delete(student_obj)
    db.session.delete(user_obj)
    db.session.commit()
    flash('Student deleted successfully!', 'success')
    return redirect(url_for('teacher_students'))

@app.route('/teacher/tests')
@teacher_required
def teacher_tests():
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    tests = db.session.query(Test, Group).join(Group).filter(Group.teacher_id == teacher.id).all()
    return render_template('teacher/tests.html', tests=tests, current_time=datetime.utcnow())

@app.route('/teacher/tests/add', methods=['GET', 'POST'])
@teacher_required
def teacher_add_test():
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    
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
        db.session.flush()  # Get the test ID
        
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
        flash('Test added successfully!', 'success')
        return redirect(url_for('teacher_tests'))
    
    return render_template('teacher/add_test.html', groups=groups)

@app.route('/teacher/tests/edit/<int:test_id>', methods=['GET', 'POST'])
@teacher_required
def teacher_edit_test(test_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    test = db.session.query(Test, Group).join(Group).filter(Test.id == test_id, Group.teacher_id == teacher.id).first_or_404()
    test_obj, group_obj = test
    groups = Group.query.filter_by(teacher_id=teacher.id).all()
    
    if request.method == 'POST':
        test_obj.title = request.form.get('title')
        test_obj.group_id = request.form.get('group_id')
        test_obj.start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
        test_obj.end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')
        test_obj.duration_minutes = int(request.form.get('duration_minutes'))
        
        # Update existing questions and add new ones
        Question.query.filter_by(test_id=test_obj.id).delete()
        
        question_count = int(request.form.get('question_count'))
        for i in range(1, question_count + 1):
            question = Question(
                test_id=test_obj.id,
                question_text=request.form.get(f'question_{i}_text'),
                option_a=request.form.get(f'question_{i}_a'),
                option_b=request.form.get(f'question_{i}_b'),
                option_c=request.form.get(f'question_{i}_c'),
                option_d=request.form.get(f'question_{i}_d'),
                correct_answer=request.form.get(f'question_{i}_correct')
            )
            db.session.add(question)
        
        db.session.commit()
        flash('Test updated successfully!', 'success')
        return redirect(url_for('teacher_tests'))
    
    return render_template('teacher/edit_test.html', test=test_obj, groups=groups)

@app.route('/teacher/tests/delete/<int:test_id>', methods=['POST'])
@teacher_required
def teacher_delete_test(test_id):
    teacher = Teacher.query.filter_by(user_id=current_user.id).first()
    test = db.session.query(Test, Group).join(Group).filter(Test.id == test_id, Group.teacher_id == teacher.id).first_or_404()
    test_obj, group_obj = test
    
    db.session.delete(test_obj)
    db.session.commit()
    flash('Test deleted successfully!', 'success')
    return redirect(url_for('teacher_tests'))

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
    return render_template('teacher/results.html', results=results)

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
            flash('Student profile not found!', 'danger')
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
        
        return render_template('student/dashboard.html', student=student, results=results, available_tests=available_tests, current_time=datetime.utcnow())
    except Exception as e:
        print(f"❌ Error in student dashboard: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error loading dashboard: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/student/test/<int:test_id>')
@student_required
def student_take_test(test_id):
    student = Student.query.filter_by(user_id=current_user.id).first()
    test = Test.query.get_or_404(test_id)
    
    # Check if student belongs to the test's group
    if student.group_id != test.group_id:
        flash('You are not authorized to take this test.', 'danger')
        return redirect(url_for('student_dashboard'))
    
    # Check if test is within time window
    now = datetime.utcnow()
    if now < test.start_time:
        flash('Test has not started yet.', 'warning')
        return redirect(url_for('student_dashboard'))
    elif now > test.end_time:
        flash('Test has expired.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    # Check if student already took the test
    existing_result = TestResult.query.filter_by(student_id=student.id, test_id=test.id).first()
    if existing_result:
        flash('You have already taken this test.', 'info')
        return redirect(url_for('student_dashboard'))
    
    questions = Question.query.filter_by(test_id=test.id).all()
    return render_template('student/take_test.html', test=test, questions=questions)

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
            flash('You have already taken this test.', 'danger')
            return redirect(url_for('student_dashboard'))
        
        # Check if test is still within time window
        now = datetime.utcnow()
        print(f"🔍 DEBUG: Now={now}, Test end={test.end_time}")
        
        if now > test.end_time:
            print("❌ DEBUG: Test time expired")
            flash('Test submission time has expired.', 'danger')
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
        
        flash(f'Test submitted! Your score: {correct_count}/{len(questions)} ({result.percentage:.1f}%)', 'success')
        
        redirect_url = url_for('student_dashboard')
        print(f"🔍 DEBUG: Redirect URL: {redirect_url}")
        
        return redirect(redirect_url)
        
    except Exception as e:
        print(f"❌ DEBUG: Error in test submit: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Error submitting test: {str(e)}', 'danger')
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
    
    # Production settings
    app.run(
        host='0.0.0.0',  # Allow external connections
        port=5000,
        debug=False,
        threaded=True  # Better for production
    )
