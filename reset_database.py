#!/usr/bin/env python3
import os
from app import app, db, User, Teacher, Student, Group, Course, Test, Question, TestResult
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

def reset_database():
    """Delete all data and recreate with default data"""
    print("🗑️ DATABASE RESET STARTING...")
    
    # Delete all existing data
    print("🗑️ Deleting existing data...")
    
    # Delete in correct order to avoid foreign key constraints
    db.session.query(TestResult).delete()
    db.session.query(Question).delete()
    db.session.query(Test).delete()
    db.session.query(Student).delete()
    db.session.query(Teacher).delete()
    db.session.query(Group).delete()
    db.session.query(Course).delete()
    db.session.query(User).delete()
    
    db.session.commit()
    print("✅ All existing data deleted")
    
    # Create default admin
    print("👑 Creating default admin...")
    admin_user = User(
        username='admin',
        password_hash=generate_password_hash('secure_admin_password_2024'),
        role='admin',
        full_name='System Administrator'
    )
    db.session.add(admin_user)
    db.session.commit()
    print("✅ Default admin created")
    
    # Create teachers
    print("👨‍🏫 Creating teachers...")
    teachers_data = [
        ('Aliyev Karim', 'teacher1'),
        ('Saidova Dilnoza', 'teacher2'),
        ('Rahimov Botir', 'teacher3'),
        ('Hoshimova Gulnora', 'teacher4')
    ]
    
    teacher_users = []
    for full_name, username in teachers_data:
        user = User(
            username=username,
            password_hash=generate_password_hash('teacher123'),
            role='teacher',
            full_name=full_name
        )
        db.session.add(user)
        db.session.commit()
        teacher_users.append(user)
        print(f"✅ Teacher user created: {username}")
    
    # Create courses
    print("📚 Creating courses...")
    courses_data = [
        ('Kompyuter savodxonligi', 'Computer Literacy'),
        ('Frontend', 'Frontend Development'),
        ('Backend', 'Backend Development'),
        ('Ingliz tili', 'English Language')
    ]
    
    courses = []
    for name, description in courses_data:
        course = Course(name=name, description=description)
        db.session.add(course)
        db.session.commit()
        courses.append(course)
        print(f"✅ Course created: {name}")
    
    # Create teachers
    print("👨‍🏫 Creating teacher profiles...")
    teachers = []
    for i, (user, course) in enumerate(zip(teacher_users, courses)):
        teacher = Teacher(
            user_id=user.id,
            course_id=course.id
        )
        db.session.add(teacher)
        db.session.commit()
        teachers.append(teacher)
        print(f"✅ Teacher profile created: {user.full_name} -> {course.name}")
    
    # Create groups
    print("👥 Creating groups...")
    groups = []
    for teacher in teachers:
        for i in range(2):  # 2 groups per teacher
            group = Group(
                name=f"{course.name.replace(' ', '')}_G{i+1}",
                teacher_id=teacher.id
            )
            db.session.add(group)
            db.session.commit()
            groups.append(group)
            print(f"✅ Group created: {group.name}")
    
    # Create students
    print("👨‍🎓 Creating students...")
    students = []
    student_counter = 1
    
    for group in groups:
        for i in range(10):  # 10 students per group
            user = User(
                username=f'student{student_counter:02d}',
                password_hash=generate_password_hash(f'student{student_counter:02d}'),
                role='student',
                full_name=f'O\'quvchi {student_counter}'
            )
            db.session.add(user)
            db.session.commit()
            
            student = Student(
                user_id=user.id,
                group_id=group.id
            )
            db.session.add(student)
            db.session.commit()
            students.append(student)
            print(f"✅ Student created: {user.username}")
            student_counter += 1
    
    # Create tests
    print("📝 Creating tests...")
    tests = []
    for group in groups:
        # Create 2 tests per group
        for i in range(2):  # 5 questions per test
            test = Test(
                title=f"{group.name} Test {i+1}",
                duration_minutes=30,
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow() + timedelta(days=30),
                group_id=group.id
            )
            db.session.add(test)
            db.session.commit()
            tests.append(test)
            print(f"✅ Test created: {test.title}")
            
            # Create questions for test
            for j in range(5):  # 5 questions per test
                question = Question(
                    test_id=test.id,
                    question_text=f"Savol {j+1} for {test.title}",
                    option_a=f"Variant A for question {j+1}",
                    option_b=f"Variant B for question {j+1}",
                    option_c=f"Variant C for question {j+1}",
                    option_d=f"Variant D for question {j+1}",
                    correct_answer='A'
                )
                db.session.add(question)
                db.session.commit()
    
    print("✅ DATABASE RESET COMPLETED!")
    print(f"📊 Summary:")
    print(f"   - Admin: 1 user")
    print(f"   - Teachers: {len(teachers)} users")
    print(f"   - Courses: {len(courses)} courses")
    print(f"   - Groups: {len(groups)} groups")
    print(f"   - Students: {len(students)} students")
    print(f"   - Tests: {len(tests)} tests")
    print(f"   - Questions: {len(tests) * 5} questions")

if __name__ == '__main__':
    with app.app_context():
        reset_database()
