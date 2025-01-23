from flask import Flask, render_template, request, jsonify
import json
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# Загрузка данных
with open("all_mcc_categories.json", "r", encoding="utf-8") as f:
    all_mcc_categories = json.load(f)

with open("cashback_categories.json", "r", encoding="utf-8") as f:
    cashback_categories = json.load(f)


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


def find_best_cashback(all_mcc_categories, cashback_categories, mcc):
    """Находит лучший банк и категорию для заданного MCC."""
    best_bank = None
    best_category = None
    max_cashback = 0

    universal_categories = {"Все покупки", "На все покупки", "Любые покупки"}

    for bank, categories in all_mcc_categories.items():
        category = find_category(categories, mcc)
        if category and bank in cashback_categories:
            cashback = cashback_categories[bank].get(category, 0)
            if cashback > max_cashback:
                max_cashback = cashback
                best_bank = bank
                best_category = category

    if not best_bank:
        for bank, categories in cashback_categories.items():
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
    return render_template('index.html')


@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'GET':
        return render_template('search.html')

    query = request.form.get('query')
    if not query:
        return render_template('search.html', error="Введите название торговой точки")

    mcc_result = get_mcc_from_site(query)

    if isinstance(mcc_result, str):
        return render_template('search.html', error=mcc_result)

    best_bank, best_category, max_cashback = find_best_cashback(all_mcc_categories, cashback_categories, mcc_result)

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
    """Отображает кешбэк-категории для каждого банка."""
    # Передаем данные о банках и категориях напрямую в шаблон
    return render_template('view_categories.html', categories=cashback_categories)

@app.route('/add_bank', methods=['GET', 'POST'])
def add_bank():
    # Список банков из all_mcc_categories.json, которых нет в cashback_categories.json
    available_banks = [bank for bank in all_mcc_categories.keys() if bank not in cashback_categories]

    if request.method == 'GET':
        # Если нет доступных банков для добавления
        if not available_banks:
            return render_template('add_bank.html', error="Все поддерживаемые банки уже добавлены.")
        return render_template('add_bank.html', banks=available_banks)

    elif request.method == 'POST':
        # Получаем выбранный банк из формы
        bank_name = request.form.get('bank_name')
        if not bank_name:
            return render_template('add_bank.html', error="Выберите банк.", banks=available_banks)

        # Добавляем банк в cashback_categories
        cashback_categories[bank_name] = {}
        with open("cashback_categories.json", "w", encoding="utf-8") as f:
            json.dump(cashback_categories, f, ensure_ascii=False, indent=4)

        return render_template('add_bank.html', success=f"Банк '{bank_name}' успешно добавлен.", banks=available_banks)

@app.route('/update_categories', methods=['GET', 'POST'])
def update_categories():
    """Обновление категорий кешбэка для банка."""
    # Список доступных банков из cashback_categories
    banks = list(cashback_categories.keys())

    if request.method == 'GET':
        # Если нет банков для обновления
        if not banks:
            return render_template('update_categories.html', error="Нет доступных банков для обновления.")
        return render_template('update_categories.html', banks=banks)

    elif request.method == 'POST':
        # Получаем данные из формы
        bank_name = request.form.get('bank_name')
        category = request.form.get('category')
        cashback = request.form.get('cashback')

        # Проверяем заполнение полей
        if not (bank_name and category and cashback):
            return render_template('update_categories.html', error="Заполните все поля.", banks=banks)

        # Проверяем, что кешбэк — это число
        try:
            cashback = float(cashback)
        except ValueError:
            return render_template('update_categories.html', error="Кешбэк должен быть числом.", banks=banks)

        # Обновляем данные банка
        if bank_name in cashback_categories:
            cashback_categories[bank_name][category] = cashback
            # Сохраняем изменения
            with open("cashback_categories.json", "w", encoding="utf-8") as f:
                json.dump(cashback_categories, f, ensure_ascii=False, indent=4)
            return render_template('update_categories.html', success=f"Категория '{category}' обновлена для банка '{bank_name}'.", banks=banks)
        else:
            return render_template('update_categories.html', error=f"Банк '{bank_name}' не найден.", banks=banks)

@app.route('/delete_bank', methods=['GET', 'POST'])
def delete_bank():
    """Удаление банка из списка."""
    # Список доступных банков из cashback_categories
    banks = list(cashback_categories.keys())

    if request.method == 'GET':
        # Если нет банков для удаления
        if not banks:
            return render_template('delete_bank.html', error="Нет доступных банков для удаления.")
        return render_template('delete_bank.html', banks=banks)

    elif request.method == 'POST':
        # Получаем выбранный банк из формы
        bank_name = request.form.get('bank_name')
        if not bank_name:
            return render_template('delete_bank.html', error="Выберите банк для удаления.", banks=banks)

        # Удаляем банк из cashback_categories
        if bank_name in cashback_categories:
            del cashback_categories[bank_name]
            # Сохраняем изменения
            with open("cashback_categories.json", "w", encoding="utf-8") as f:
                json.dump(cashback_categories, f, ensure_ascii=False, indent=4)
            banks = list(cashback_categories.keys())  # Обновляем список банков
            return render_template('delete_bank.html', success=f"Банк '{bank_name}' успешно удалён.", banks=banks)
        else:
            return render_template('delete_bank.html', error=f"Банк '{bank_name}' не найден.", banks=banks)

#if __name__ == '__main__':
#    app.run(debug=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
