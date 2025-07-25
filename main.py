import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, g, session, flash
from contextlib import closing
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['DATABASE'] = 'todo.db'
app.config['SECRET_KEY'] = os.urandom(24)  


PROTECTED_TASKS = []

def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

def init_db():
    with closing(connect_db()) as db:
       
        db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        db.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            user_id INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')
        
        db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            category_id INTEGER DEFAULT 1,
            user_id INTEGER NOT NULL,
            protected INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(category_id) REFERENCES categories(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')
        db.commit()
        
       
        try:
            db.execute("INSERT INTO categories (name, user_id) VALUES ('Важное', 0), ('Второстепенное', 0)")
            db.commit()
        except sqlite3.IntegrityError:
            pass
     
        cursor = db.cursor()
        for task_content in PROTECTED_TASKS:
            cursor.execute("SELECT 1 FROM tasks WHERE content = ?", (task_content,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO tasks (content, protected, user_id) VALUES (?, 1, 0)", 
                    (task_content,)
                )
        db.commit()

@app.before_request
def before_request():
    g.db = connect_db()
    g.db.row_factory = sqlite3.Row
    g.user = None
    
    if 'user_id' in session:
        user = g.db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if user:
            g.user = dict(user)

@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        confirm_password = request.form['confirm-password'].strip()
        
        errors = []
        
        if not username:
            errors.append('Имя пользователя обязательно')
        if not email:
            errors.append('Email обязателен')
        if not password:
            errors.append('Пароль обязателен')
        if password != confirm_password:
            errors.append('Пароли не совпадают')
        if len(password) < 6:
            errors.append('Пароль должен быть не менее 6 символов')
        

        if not errors:
            cursor = g.db.execute('SELECT 1 FROM users WHERE username = ?', (username,))
            if cursor.fetchone():
                errors.append('Это имя пользователя уже занято')
            
            cursor = g.db.execute('SELECT 1 FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                errors.append('Этот email уже зарегистрирован')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html')
        
     
        hashed_password = generate_password_hash(password)
        g.db.execute(
            'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
            (username, email, hashed_password)
        )
        g.db.commit()
        
   
        user = g.db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        
        flash('Регистрация прошла успешно!', 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        
        user = g.db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if not user or not check_password_hash(user['password'], password):
            flash('Неверный email или пароль', 'danger')
            return render_template('login.html')
        
        session['user_id'] = user['id']
        flash('Вход выполнен успешно!', 'success')
        return redirect(url_for('index'))
    
    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('welcome'))


@app.route('/')
def welcome():
    return render_template('welcome.html')


@app.route('/tasks')
def index():
    if not g.user:
        flash('Для доступа к задачам необходимо войти в систему', 'warning')
        return redirect(url_for('login'))
    
    category_id = request.args.get('category', type=int)
    tasks = get_tasks(category_id)
    
    categories = get_categories()
    
    return render_template('index.html', 
                         tasks=tasks,
                         categories=categories,
                         current_category=category_id,
                         protected_tasks=PROTECTED_TASKS)

def get_categories():

    query = '''
    SELECT categories.*, COUNT(tasks.id) as task_count 
    FROM categories 
    LEFT JOIN tasks ON categories.id = tasks.category_id 
    WHERE (categories.user_id = 0 OR categories.user_id = ?)
    GROUP BY categories.id
    ORDER BY categories.id
    '''
    cursor = g.db.execute(query, (g.user['id'],))
    categories = cursor.fetchall()

    category_list = []
    for category in categories:
        category_list.append(dict(category))
    
    return category_list

def get_tasks(category_id=None):
    query = '''
    SELECT tasks.*, categories.name as category_name 
    FROM tasks 
    LEFT JOIN categories ON tasks.category_id = categories.id
    WHERE tasks.user_id = ?
    '''
    params = [g.user['id']]

    if category_id:
        query += ' AND tasks.category_id = ?'
        params.append(category_id)

    query += ' ORDER BY tasks.id DESC'
    
    cursor = g.db.execute(query, params)
    tasks = cursor.fetchall()
    

    task_list = []
    for task in tasks:
        task_dict = dict(task)
        task_dict['is_protected'] = task_dict.get('protected', 0) == 1
        task_list.append(task_dict)
    
    return task_list

@app.route('/add_category', methods=['POST'])
def add_category():
    if not g.user:
        return redirect(url_for('login'))
    
    name = request.form['category_name'].strip()
    if name:
        try:
            g.db.execute('INSERT INTO categories (name, user_id) VALUES (?, ?)', (name, g.user['id']))
            g.db.commit()
            flash('Категория добавлена', 'success')
        except sqlite3.IntegrityError:
            flash('Категория с таким именем уже существует', 'danger')
    
    return redirect(url_for('index'))

@app.route('/delete_category/<int:category_id>')
def delete_category(category_id):
    if not g.user:
        return redirect(url_for('login'))
    

    if category_id == 1 or category_id == 2:
        flash('Системные категории нельзя удалить', 'danger')
        return redirect(url_for('index'))
    
    try:

        category = g.db.execute('SELECT user_id FROM categories WHERE id = ?', (category_id,)).fetchone()
        if category and category['user_id'] != g.user['id']:
            flash('Вы не можете удалить эту категорию', 'danger')
            return redirect(url_for('index'))
        
        
        g.db.execute('UPDATE tasks SET category_id = 1 WHERE category_id = ?', (category_id,))

        g.db.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        g.db.commit()
        flash('Категория удалена', 'success')
    except Exception as e:
        print(f"Ошибка при удалении категории: {e}")
        flash('Ошибка при удалении категории', 'danger')
    
    return redirect(url_for('index'))

@app.route('/add_task', methods=['POST'])
def add_task():
    if not g.user:
        return redirect(url_for('login'))
    
    content = request.form['content'].strip()
    if content:
        category_id = request.form.get('category', 1)
        
      
        is_protected = 1 if any(
            protected in content.lower() 
            for protected in [p.lower() for p in PROTECTED_TASKS]
        ) else 0
        
        g.db.execute(
            'INSERT INTO tasks (content, category_id, protected, user_id) VALUES (?, ?, ?, ?)', 
            (content, category_id, is_protected, g.user['id'])
        )
        g.db.commit()
        flash('Задача добавлена', 'success')
    
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>')
def delete(task_id):
    if not g.user:
        return redirect(url_for('login'))
    
    try:
        task = g.db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if task and task['protected'] == 1:
            flash('Эта задача защищена от удаления', 'warning')
            return redirect(url_for('index'))
        
     
        if task and task['user_id'] != g.user['id']:
            flash('Вы не можете удалить эту задачу', 'danger')
            return redirect(url_for('index'))
        
        g.db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        g.db.commit()
        flash('Задача удалена', 'success')
    except Exception as e:
        print(f"Ошибка при удалении: {e}")
        flash('Ошибка при удалении задачи', 'danger')
    
    return redirect(url_for('index'))

@app.route('/complete/<int:task_id>')
def complete(task_id):
    if not g.user:
        return redirect(url_for('login'))
    
   
    
    task = g.db.execute('SELECT user_id FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if task and task['user_id'] != g.user['id']:
        flash('Вы не можете изменить эту задачу', 'danger')
        return redirect(url_for('index'))
    
    g.db.execute('UPDATE tasks SET completed = NOT completed WHERE id = ?', (task_id,))
    g.db.commit()
    flash('Статус задачи обновлен', 'success')

  
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, port=os.getenv("PORT", default=5000))