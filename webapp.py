from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
import json
import requests
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import pandas as pd
import re

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

# Модель для избранных торговых точек
class FavoriteStore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    store_name = db.Column(db.String(200), nullable=False)
    mcc = db.Column(db.String(10), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=0)  # Поле для порядка

    def __repr__(self):
        return f"FavoriteStore('{self.store_name}', '{self.mcc}')"

# Загрузка данных
with open("all_mcc_categories.json", "r", encoding="utf-8") as f:
    all_mcc_categories = json.load(f)

def parse_range(mcc):
    """Парсит MCC-коды, включая диапазоны."""
    if isinstance(mcc, list):
        # Если MCC уже список, возвращаем его как есть
        return mcc
    elif '-' in mcc:
        # Если MCC — диапазон, преобразуем в список
        start, end = map(int, mcc.split('-'))
        return range(start, end + 1)
    else:
        # Если MCC — одиночное значение, преобразуем в список
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

    # Перебираем банки пользователя
    for bank, user_categories in user_cashback_categories.items():
        # Перебираем категории банка
        for category, cashback in user_categories.items():
            # Получаем список MCC-кодов для категории из базы
            mcc_list = all_mcc_categories.get(bank, {}).get(category, [])

            if "*" in mcc_list:
                # Универсальная категория
                if cashback > max_cashback:
                    max_cashback = cashback
                    best_bank = bank
                    best_category = category
            else:
                # Проверяем MCC-код в списке
                for code in mcc_list:
                    if mcc in parse_range(code):
                        if cashback > max_cashback:
                            max_cashback = cashback
                            best_bank = bank
                            best_category = category

    return best_bank, best_category, max_cashback

def get_mcc_codes(store_name):
    base_url = "https://mcc-codes.ru/search"
    headers = {"User-Agent": "Mozilla/5.0"}
    all_data = []
    page = 1
    data_found = False  # Флаг для проверки наличия данных

    while True:
        params = {"q": store_name, "extended": 0, "sortBy": "date", "sortDir": "desc", "page": page}
        response = requests.get(base_url, params=params, headers=headers)

        if response.status_code != 200:
            print("Ошибка запроса:", response.status_code)
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", class_="table")
        
        if not table:
            if not data_found:
                print("Таблица не найдена. Возможно, данных для данного запроса нет.")
            break
        
        data_found = True  # Данные найдены хотя бы на одной странице
        table_headers = [th.text.strip() for th in table.find_all("th")]
        rows = table.find_all("tr")[1:]  # Пропускаем заголовок таблицы
        
        for row in rows:
            cols = row.find_all("td")
            all_data.append([col.text.strip() for col in cols])
        
        page += 1  # Переход к следующей странице
    
    if not all_data:
        return None
    
    df = pd.DataFrame(all_data, columns=table_headers)
    return df

def get_mcc_description(mcc_code):
    """Получает описание MCC-кода с сайта merchantpoint.ru."""
    url = f"https://merchantpoint.ru/mcc/{mcc_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Проверяем, что запрос успешен
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе описания для MCC {mcc_code}: {e}")
        return "Описание не найдено"
    
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("h1")
    
    if title_tag:
        # Извлекаем описание из заголовка
        description = title_tag.text.strip().split("-", 1)[-1].strip()
        return description
    else:
        return "Описание не найдено"

def get_mcc_data(store_name):
    df = get_mcc_codes(store_name)
    if df is None:
        return pd.DataFrame(columns=["Название точки", "mcc", "Описание"])
    
    # Извлекаем название точки и число подтверждений
    def extract_store_name(value):
        parts = value.split("\n")
        return parts[0].strip() if len(parts) > 0 else value.strip()
    
    def extract_confirmations(value):
        match = re.search(r"\+\d+", value)
        return int(match.group(0)[1:]) if match else 0
    
    df["Название точки"] = df["Название точкиАдрес оплаты"].apply(extract_store_name)
    df["Подтверждения"] = df["Актуально"].apply(extract_confirmations)
    df["Число повторений"] = 1 + df["Подтверждения"]
    
    # Вычисляем число повторений MCC-кодов с учетом подтверждений
    mcc_counts = df.groupby("MCC")["Число повторений"].sum().reset_index()
    mcc_counts.columns = ["mcc", "Число повторений"]
    
    # Находим торговую точку с максимальным числом подтверждений для каждого MCC
    df_sorted = df.sort_values(by=["MCC", "Подтверждения"], ascending=[True, False])
    max_confirmations = df_sorted.drop_duplicates(subset=["MCC"], keep="first")[["MCC", "Название точки", "Подтверждения"]]
    
    # Объединяем данные
    result = mcc_counts.merge(max_confirmations, left_on="mcc", right_on="MCC")
    result = result.drop(columns=["MCC"])  # Убираем дублирующий столбец
    
    # Добавляем описание MCC-кода
    result["Описание"] = result["mcc"].apply(get_mcc_description)
    
    # Сортируем по убыванию числа повторений
    result = result.sort_values(by="Число повторений", ascending=False)
    
    # Возвращаем DataFrame с нужными колонками
    return result[["Название точки", "mcc", "Описание"]]

# Версия RADAR Cashback
APP_VERSION = "1.0.8"

@app.route('/')
def index():
    if 'username' in session:
        return render_template('index.html', username=session['username'], app_version=APP_VERSION)
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

    user = User.query.filter_by(username=session['username']).first()
    favorites = FavoriteStore.query.filter_by(user_id=user.id).all()

    if request.method == 'GET':
        return render_template('search.html', favorites=favorites)

    query = request.form.get('query')
    if not query:
        return render_template('search.html', error="Введите название торговой точки", favorites=favorites)

    # Получаем данные о торговых точках
    mcc_data = get_mcc_data(query)

    if mcc_data is None or mcc_data.empty:
        return render_template('search.html', error="Торговые точки не найдены")

    # Преобразуем DataFrame в список словарей для передачи в шаблон
    stores = mcc_data.to_dict('records')

    # Передаем название торговой точки в шаблон
    return render_template('select_store.html', stores=stores, query=query)  # Добавляем query

@app.route('/select_store', methods=['POST'])
def select_store():
    if 'username' not in session:
        return redirect(url_for('login'))

    selected_mcc = request.form.get('mcc')
    store_name = request.form.get('store_name')
    query = request.form.get('query')  # Получаем исходный запрос пользователя

    if not selected_mcc or not store_name:
        return redirect(url_for('search'))

    # Сохраняем выбранный MCC и название точки в историю поиска
    if 'search_history' not in session:
        session['search_history'] = []
    
    # Добавляем новый запрос в историю (максимум 5 записей)
    session['search_history'].insert(0, {
        'store_name': store_name,  # Передаем название точки из формы
        'mcc': selected_mcc,
        'description': request.form.get('description')  # Передаем описание MCC из формы
    })
    
    # Ограничиваем историю 5 последними запросами
    if len(session['search_history']) > 5:
        session['search_history'] = session['search_history'][:5]
    
    # Помечаем сессию как измененную
    session.modified = True

    # Загружаем категории пользователя
    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}

    # Находим лучший банк и категорию
    best_bank, best_category, max_cashback = find_best_cashback(all_mcc_categories, user_cashback_categories, int(selected_mcc))

    if best_bank:
        # Если найден лучший банк, отображаем результат
        return render_template(
            'search_result.html',
            bank=best_bank.upper(),
            category=best_category.upper(),
            cashback=max_cashback,
            mcc=selected_mcc,
            store_name=query  # Передаем исходный запрос пользователя
        )
    else:
        # Если ничего не найдено
        return render_template(
            'search_result.html',
            message="Кешбэк для указанной точки не найден",
            mcc=selected_mcc
        )

@app.route('/remove_from_history', methods=['POST'])
def remove_from_history():
    if 'username' not in session:
        return redirect(url_for('login'))

    index = int(request.form.get('index'))
    if 'search_history' in session and 0 <= index < len(session['search_history']):
        session['search_history'].pop(index)
        session.modified = True  # Помечаем сессию как измененную

    return redirect(url_for('search'))

@app.route('/select_favorite', methods=['POST'])
def select_favorite():
    if 'username' not in session:
        return redirect(url_for('login'))

    selected_mcc = request.form.get('mcc')
    store_name = request.form.get('store_name')

    if not selected_mcc or not store_name:
        return redirect(url_for('search'))

    # Загружаем категории пользователя
    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}

    # Находим лучший банк и категорию
    best_bank, best_category, max_cashback = find_best_cashback(all_mcc_categories, user_cashback_categories, int(selected_mcc))

    if best_bank:
        # Если найден лучший банк, отображаем результат
        return render_template(
            'search_result.html',
            bank=best_bank.upper(),
            category=best_category.upper(),
            cashback=max_cashback,
            mcc=selected_mcc,
            store_name=store_name  # Передаем название торговой точки
        )
    else:
        # Если ничего не найдено
        return render_template(
            'search_result.html',
            message="Кешбэк для указанной точки не найден",
            mcc=selected_mcc
        )

@app.route('/add_to_favorites', methods=['POST'])
def add_to_favorites():
    if 'username' not in session:
        return redirect(url_for('login'))

    store_name = request.form.get('store_name')
    mcc = request.form.get('mcc')

    if not store_name or not mcc:
        flash('Необходимо указать название торговой точки и MCC-код')
        return redirect(url_for('search'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return redirect(url_for('login'))

    # Проверяем, не добавлена ли уже эта торговая точка
    existing_store = FavoriteStore.query.filter_by(user_id=user.id, store_name=store_name).first()
    if existing_store:
        flash('Торговая точка уже добавлена в избранное')
        return redirect(url_for('search'))

    # Определяем следующий порядок
    max_order = db.session.query(db.func.max(FavoriteStore.order)).filter_by(user_id=user.id).scalar() or 0
    new_favorite = FavoriteStore(user_id=user.id, store_name=store_name, mcc=mcc, order=max_order + 1)

    db.session.add(new_favorite)
    db.session.commit()

    flash('Торговая точка добавлена в избранное')
    return redirect(url_for('search'))

@app.route('/edit_favorite/<int:favorite_id>', methods=['GET', 'POST'])
def edit_favorite(favorite_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    favorite = FavoriteStore.query.get_or_404(favorite_id)
    user = User.query.filter_by(username=session['username']).first()

    if favorite.user_id != user.id:
        flash('У вас нет прав на редактирование этой записи')
        return redirect(url_for('search'))

    if request.method == 'POST':
        store_name = request.form.get('store_name')
        mcc = request.form.get('mcc')

        if not store_name or not mcc:
            flash('Необходимо указать название торговой точки и MCC-код')
            return redirect(url_for('search'))

        favorite.store_name = store_name
        favorite.mcc = mcc
        db.session.commit()

        flash('Торговая точка успешно обновлена')
        return redirect(url_for('search'))

    return render_template('edit_favorite.html', favorite=favorite)

@app.route('/delete_favorite/<int:favorite_id>', methods=['POST'])
def delete_favorite(favorite_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    favorite = FavoriteStore.query.get_or_404(favorite_id)
    user = User.query.filter_by(username=session['username']).first()

    if favorite.user_id != user.id:
        flash('У вас нет прав на удаление этой записи')
        return redirect(url_for('search'))

    db.session.delete(favorite)
    db.session.commit()

    flash('Торговая точка удалена из избранного')
    return redirect(url_for('search'))

@app.route('/update_favorites_order', methods=['POST'])
def update_favorites_order():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    try:
        new_order = request.form.getlist('order[]')  # Получаем список ID
        for index, fav_id in enumerate(new_order):
            favorite = FavoriteStore.query.filter_by(id=int(fav_id), user_id=user.id).first()
            if favorite:
                favorite.order = index  # Обновляем порядок
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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

    # Загрузка данных из базы
    user = User.query.filter_by(username=session['username']).first()
    user_cashback_categories = json.loads(user.cashback_categories) if user.cashback_categories else {}
    banks = list(user_cashback_categories.keys())

    # Если GET-запрос, отобразим категории банка
    if request.method == 'GET':
        selected_bank = request.args.get('bank')
        categories = user_cashback_categories.get(selected_bank, {}) if selected_bank else {}
        
        # Загрузка всех доступных категорий для банка
        available_categories = []
        if selected_bank and selected_bank in all_mcc_categories:
            available_categories = list(all_mcc_categories[selected_bank].keys())
        
        return render_template(
            'update_categories.html',
            banks=banks,
            selected_bank=selected_bank,
            categories=categories,
            available_categories=available_categories
        )

    # Если POST-запрос, обработаем действия пользователя
    elif request.method == 'POST':
        action = request.form.get('action')
        bank_name = request.form.get('bank_name')

        # Удаление категории
        if action == 'delete_category':
            category_to_delete = request.form.get('category')
            if category_to_delete and bank_name in user_cashback_categories:
                user_cashback_categories[bank_name].pop(category_to_delete, None)
                user.cashback_categories = json.dumps(user_cashback_categories)
                db.session.commit()
                flash(f"Категория '{category_to_delete}' удалена.")

        # Добавление или обновление категории
        elif action == 'update_or_add':
            category = request.form.get('category')
            cashback = request.form.get('cashback')
            if category and cashback and bank_name in user_cashback_categories:
                try:
                    cashback = float(cashback)
                    user_cashback_categories[bank_name][category] = cashback
                    user.cashback_categories = json.dumps(user_cashback_categories)
                    db.session.commit()
                    flash(f"Категория '{category}' обновлена или добавлена.")
                except ValueError:
                    flash("Кешбэк должен быть числом.")

        return redirect(url_for('update_categories', bank=bank_name))

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
