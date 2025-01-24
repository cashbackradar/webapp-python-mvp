from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import json
import requests
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # Срок действия сессии
db = SQLAlchemy(app)

# Модель пользователя
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    cashback_categories = db.Column(db.String, nullable=True)

# Загрузка данных
with open("all_mcc_categories.json", "r", encoding="utf-8") as f:
    all_mcc_categories = json.load(f)

def parse_range(mcc):
    """Парсит MCC-коды, включая диапазоны."""
    if '-' in mcc:
        start, end = map(int, mcc.split('-'))
        return range(start, end + 1)
    return [int(mcc)]

def find_category(bank_data, mcc):
    """Находит категорию по MCC-коду."""
    for category, mcc_list in bank_data.items():
        for code in mcc_list:
            if mcc in parse_range(code):
                return category
    return None

def find_best_cashback(all_mcc_categories, user_cashback_categories, mcc):
    """Находит лучший банк и категорию для заданного MCC."""
    best_bank = None
    best_category = None
    max_cashback = 0

    universal_categories = {"Все покупки", "На все покупки", "Любые покупки"}

    # Проходим по всем банкам
    for bank, categories in all_mcc_categories.items():
        # Собираем все категории, которые подходят для данного MCC
        matching_categories = []
        for category, mcc_list in categories.items():
            for code in mcc_list:
                if mcc in parse_range(code):
                    matching_categories.append(category)
                    break  # Если MCC найден в категории, переходим к следующей категории

        # Если найдены подходящие категории, проверяем кешбэк
        if matching_categories and bank in user_cashback_categories:
            for category in matching_categories:
                cashback = user_cashback_categories[bank].get(category, 0)
                if cashback > max_cashback:
                    max_cashback = cashback
                    best_bank = bank
                    best_category = category

    # Если не найдено подходящих категорий, проверяем универсальные категории
    if not best_bank:
        for bank, categories in user_cashback_categories.items():
            for category, cashback in categories.items():
                if category in universal_categories and cashback > max_cashback:
                    max_cashback = cashback
                    best_bank = bank
                    best_category = category

    return best_bank, best_category, max_cashback

def get_mcc_from_site(query):
    """Ищет MCC-код для заданной торговой точки через сайт mcc-codes.ru."""
    url = "https://mcc-codes.ru/search/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    params = {"q": query}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return f"Ошибка при подключении к сайту: {e}\nПроверьте соединение с интернетом или доступность сайта https://mcc-codes.ru."

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find("table")
    if not table:
        return f"Для '{query}' MCC-коды не найдены. Проверьте правильность названия торговой точки."

    rows = table.find_all("tr")[1:]
    if not rows:
        return f"MCC-коды для '{query}' не найдены. Проверьте название торговой точки."

    first_row = rows[0]
    columns = first_row.find_all("td")
    if len(columns) >= 1:
        mcc_code = columns[0].text.strip()
        if mcc_code.isdigit() and len(mcc_code) == 4:
            return int(mcc_code)

    return f"MCC-код для '{query}' не найден или имеет неверный формат."

@app.route('/')
def index():
    if 'username' in session:
        return render_template('index.html', username=session['username'])
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = request.form.get('remember')  # Проверяем, выбран ли флажок "Запомнить меня"

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['username'] = username
            if remember:  # Если флажок "Запомнить меня" выбран
                session.permanent = True  # Делаем сессию постоянной
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация прошла успешно. Пожалуйста, войдите.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/search', methods=['GET', 'POST'])
def search():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'GET':
        return render_template('search.html')

    query = request.form.get('query')
    if not query:
        return render_template('search.html', error="Введите название торговой точки")

    mcc_result = get_mcc_from_site(query)

    if isinstance(mcc_result, str):
        return render_template('search.html', error=mcc_result)

    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}

    best_bank, best_category, max_cashback = find_best_cashback(all_mcc_categories, user_cashback_categories, mcc_result)

    if best_bank:
        return render_template(
            'search_result.html',
            bank=best_bank.upper(),
            category=best_category.upper(),
            cashback=max_cashback
        )
    else:
        return render_template(
            'search_result.html',
            message="Кешбэк для указанной точки не найден"
        )

@app.route('/view_categories', methods=['GET'])
def view_categories():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}
    return render_template('view_categories.html', categories=user_cashback_categories)

@app.route('/add_bank', methods=['GET', 'POST'])
def add_bank():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}

    available_banks = [bank for bank in all_mcc_categories.keys() if bank not in user_cashback_categories]

    if request.method == 'GET':
        if not available_banks:
            return render_template('add_bank.html', error="Все поддерживаемые банки уже добавлены.")
        return render_template('add_bank.html', banks=available_banks)

    elif request.method == 'POST':
        bank_name = request.form.get('bank_name')
        if not bank_name:
            return render_template('add_bank.html', error="Выберите банк.", banks=available_banks)

        user_cashback_categories[bank_name] = {}
        user.cashback_categories = json.dumps(user_cashback_categories)
        db.session.commit()

        return render_template('add_bank.html', success=f"Банк '{bank_name}' успешно добавлен.", banks=available_banks)

@app.route('/update_categories', methods=['GET', 'POST'])
def update_categories():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}

    banks = list(user_cashback_categories.keys())

    if request.method == 'GET':
        if not banks:
            return render_template('update_categories.html', error="Нет доступных банков для обновления.")
        return render_template('update_categories.html', banks=banks)

    elif request.method == 'POST':
        bank_name = request.form.get('bank_name')
        category = request.form.get('category')
        cashback = request.form.get('cashback')

        if not (bank_name and category and cashback):
            return render_template('update_categories.html', error="Заполните все поля.", banks=banks)

        try:
            cashback = float(cashback)
        except ValueError:
            return render_template('update_categories.html', error="Кешбэк должен быть числом.", banks=banks)

        if bank_name in user_cashback_categories:
            user_cashback_categories[bank_name][category] = cashback
            user.cashback_categories = json.dumps(user_cashback_categories)
            db.session.commit()
            return render_template('update_categories.html', success=f"Категория '{category}' обновлена для банка '{bank_name}'.", banks=banks)
        else:
            return render_template('update_categories.html', error=f"Банк '{bank_name}' не найден.", banks=banks)

@app.route('/delete_bank', methods=['GET', 'POST'])
def delete_bank():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}

    banks = list(user_cashback_categories.keys())

    if request.method == 'GET':
        if not banks:
            return render_template('delete_bank.html', error="Нет доступных банков для удаления.")
        return render_template('delete_bank.html', banks=banks)

    elif request.method == 'POST':
        bank_name = request.form.get('bank_name')
        if not bank_name:
            return render_template('delete_bank.html', error="Выберите банк для удаления.", banks=banks)

        if bank_name in user_cashback_categories:
            del user_cashback_categories[bank_name]
            user.cashback_categories = json.dumps(user_cashback_categories)
            db.session.commit()
            banks = list(user_cashback_categories.keys())
            return render_template('delete_bank.html', success=f"Банк '{bank_name}' успешно удалён.", banks=banks)
        else:
            return render_template('delete_bank.html', error=f"Банк '{bank_name}' не найден.", banks=banks)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
