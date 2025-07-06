# app.py
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, g
from contextlib import closing

app = Flask(__name__)
app.config['DATABASE'] = 'todo.db'
app.config['SECRET_KEY'] = 'your-secret-key-here'

def connect_db():
    return sqlite3.connect(app.config['DATABASE'])

def init_db():
    with closing(connect_db()) as db:
        
        db.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )''')
        db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            category_id INTEGER DEFAULT 1,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )''')
        db.commit()
        

        try:
            db.execute("INSERT INTO categories (name) VALUES ('Важное'), ('Второстепенное')")
            db.commit()
        except sqlite3.IntegrityError:
            pass

@app.before_request
def before_request():
    g.db = connect_db()
    g.db.row_factory = sqlite3.Row

@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()

@app.route('/add_category', methods=['POST'])
def add_category():
    name = request.form['category_name'].strip()
    if name:
        try:
            g.db.execute('INSERT INTO categories (name) VALUES (?)', (name,))
            g.db.commit()
        except sqlite3.IntegrityError:
            pass
    return redirect(url_for('index'))

@app.route('/delete_category/<int:category_id>')
def delete_category(category_id):
    # Нельзя удалить категорию по умолчанию (id=1)
    if category_id == 1:
        return redirect(url_for('index'))
    
    try:
        # Перемещаем задачи в категорию по умолчанию
        g.db.execute('UPDATE tasks SET category_id = 1 WHERE category_id = ?', (category_id,))
        # Удаляем категорию
        g.db.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        g.db.commit()
    except Exception as e:
        print(f"Ошибка при удалении категории: {e}")
    
    return redirect(url_for('index'))

def get_tasks(category_id=None):
    query = '''
    SELECT tasks.*, categories.name as category_name 
    FROM tasks 
    LEFT JOIN categories ON tasks.category_id = categories.id
    '''
    params = ()

    if category_id:
        query += ' WHERE tasks.category_id = ?'
        params = (category_id,)

    query += ' ORDER BY tasks.id DESC'
    
    cursor = g.db.execute(query, params)
    return cursor.fetchall()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        content = request.form['content'].strip()
        if content:
            category_id = request.form.get('category', 1)
            g.db.execute('INSERT INTO tasks (content, category_id) VALUES (?, ?)', 
                        (content, category_id))
            g.db.commit()
        return redirect(url_for('index'))
    
    category_id = request.args.get('category', type=int)
    tasks = get_tasks(category_id)
    
    categories = g.db.execute('''
    SELECT categories.*, COUNT(tasks.id) as task_count 
    FROM categories 
    LEFT JOIN tasks ON categories.id = tasks.category_id 
    GROUP BY categories.id
    ORDER BY categories.id
    ''').fetchall()

    task_list = []
    for task in tasks:
        task_list.append(dict(task))

    category_list = []
    for category in categories:
        category_list.append(dict(category))

    return render_template('index.html', 
                         tasks=task_list,
                         categories=category_list,
                         current_category=category_id)

@app.route('/delete/<int:task_id>')
def delete(task_id):
    try:
        g.db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        g.db.commit()
    except Exception as e:
        print(f"Ошибка при удалении: {e}")
    return redirect(url_for('index'))

@app.route('/complete/<int:task_id>')
def complete(task_id):
    try:
        g.db.execute('UPDATE tasks SET completed = NOT completed WHERE id = ?', (task_id,))
        g.db.commit()
    except Exception as e:
        print(f"Ошибка при обновлении: {e}")
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)