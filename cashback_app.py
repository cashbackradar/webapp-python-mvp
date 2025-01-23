import json
import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import messagebox, simpledialog
from tkinter import ttk

def parse_range(mcc):
    """Парсит MCC-коды, включая диапазоны."""
    if '-' in mcc:
        start, end = map(int, mcc.split('-'))
        return range(start, end + 1)
    return [int(mcc)]

def load_data():
    """Загружает данные из файлов."""
    with open("all_mcc_categories.json", "r", encoding="utf-8") as f:
        all_mcc_categories = json.load(f)

    with open("cashback_categories.json", "r", encoding="utf-8") as f:
        cashback_categories = json.load(f)

    return all_mcc_categories, cashback_categories

def save_cashback_categories(data, file_path='cashback_categories.json'):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

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

    # Список ключевых слов для поиска универсальных категорий
    universal_categories = {"Все покупки", "На все покупки", "Любые покупки"}

    # Ищем максимальный кешбэк для конкретного MCC
    for bank, categories in all_mcc_categories.items():
        category = find_category(categories, mcc)
        if category and bank in cashback_categories:
            cashback = cashback_categories[bank].get(category, 0)
            if cashback > max_cashback:
                max_cashback = cashback
                best_bank = bank
                best_category = category

    # Если повышенного кешбэка не найдено, ищем универсальную категорию
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
        return f"Ошибка при подключении к сайту: {e}\n" \
               f"Проверьте соединение с интернетом или доступность сайта https://mcc-codes.ru."

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find("table")
    if not table:
        return f"Для '{query}' MCC-коды не найдены. Проверьте правильность названия торговой точки."

    rows = table.find_all("tr")[1:]  # Пропускаем заголовок таблицы
    if not rows:
        return f"MCC-коды для '{query}' не найдены. Проверьте название торговой точки."

    first_row = rows[0]
    columns = first_row.find_all("td")
    if len(columns) >= 1:
        mcc_code = columns[0].text.strip()
        if mcc_code.isdigit() and len(mcc_code) == 4:  # Проверяем, что MCC корректный
            return mcc_code

    return f"MCC-код для '{query}' не найден или имеет неверный формат."

def search_mcc():
    query = simpledialog.askstring("Поиск MCC", "Введите название торговой точки:")
    if not query:
        return

    mcc_result = get_mcc_from_site(query)

    if not mcc_result.isdigit():
        messagebox.showerror("Ошибка", mcc_result)
        return

    mcc = int(mcc_result)
    best_bank, best_category, max_cashback = find_best_cashback(all_mcc_categories, cashback_categories, mcc)

    if best_bank:
        result = f"Лучший банк: {best_bank}\nКатегория: {best_category}\nКэшбэк: {max_cashback}%"
        messagebox.showinfo("Результат поиска", result)
    else:
        messagebox.showinfo("Результат поиска", "Для заданного MCC не найдено подходящей категории. Попробуйте карту с универсальным кешбэком.")

def add_bank():
    window = tk.Toplevel()
    window.title("Добавить банк")

    label = tk.Label(window, text="Выберите банк для добавления:", font=("Helvetica", 14))
    label.pack(pady=10)

    for bank in all_mcc_categories.keys():
        if bank not in cashback_categories:
            tk.Button(window, text=bank, font=("Helvetica", 12), bg="#4caf50", fg="white",
                      command=lambda b=bank: confirm_add_bank(window, b)).pack(pady=5, padx=10, fill=tk.X)

def confirm_add_bank(window, bank):
    cashback_categories[bank] = {}
    save_cashback_categories(cashback_categories)
    messagebox.showinfo("Успех", f"Банк '{bank}' успешно добавлен.")
    window.destroy()

def delete_bank():
    if not cashback_categories:
        messagebox.showinfo("Информация", "Нет данных о банках для удаления.")
        return

    window = tk.Toplevel()
    window.title("Удалить банк")

    label = tk.Label(window, text="Выберите банк для удаления:", font=("Helvetica", 14))
    label.pack(pady=10)

    for bank in cashback_categories.keys():
        tk.Button(window, text=bank, font=("Helvetica", 12), bg="#ff5252", fg="white",
                  command=lambda b=bank: confirm_delete_bank(window, b)).pack(pady=5, padx=10, fill=tk.X)

def confirm_delete_bank(window, bank):
    del cashback_categories[bank]
    save_cashback_categories(cashback_categories)
    messagebox.showinfo("Успех", f"Банк '{bank}' успешно удалён.")
    window.destroy()

def update_categories():
    bank_name = simpledialog.askstring("Обновить категории", "Введите название банка для обновления категорий:")
    if not bank_name:
        return

    if bank_name not in cashback_categories:
        messagebox.showerror("Ошибка", f"Банк '{bank_name}' не найден. Добавьте его сначала через опцию 'Добавить банк'.")
        return

    while True:
        category = simpledialog.askstring("Обновить категории", "Введите название категории (или оставьте пустым для завершения):")
        if not category:
            break

        try:
            cashback_rate = float(simpledialog.askstring("Обновить категории", f"Введите ставку кешбэка для категории '{category}':"))
            cashback_categories[bank_name][category] = cashback_rate
            messagebox.showinfo("Успех", f"Категория '{category}' обновлена с кешбэком {cashback_rate}% для банка '{bank_name}'.")
        except (ValueError, TypeError):
            messagebox.showerror("Ошибка", "Ставка кешбэка должна быть числом.")

    save_cashback_categories(cashback_categories)

def view_categories():
    if not cashback_categories:
        messagebox.showinfo("Информация", "Нет данных о кешбэках.")
        return

    window = tk.Toplevel()
    window.title("Категории и кешбэк")

    style = ttk.Style()
    style.configure("Treeview", rowheight=30, font=("Helvetica", 12))
    style.configure("Treeview.Heading", font=("Helvetica", 14, "bold"))

    tree = ttk.Treeview(window, columns=("Категория", "Кешбэк"), show="headings")
    tree.heading("Категория", text="Категория")
    tree.heading("Кешбэк", text="Кешбэк (%)")

    for bank, categories in cashback_categories.items():
        tree.insert("", "end", values=(f"Банк: {bank}", ""), tags=("bank",))
        for category, cashback in categories.items():
            tree.insert("", "end", values=(category, f"{cashback}%"))

    tree.tag_configure("bank", background="#d3e0ea", font=("Helvetica", 12, "bold"))

    tree.pack(fill=tk.BOTH, expand=True)

def main():
    global all_mcc_categories, cashback_categories
    all_mcc_categories, cashback_categories = load_data()

    root = tk.Tk()
    root.title("MCC Cashback Manager")
    root.configure(bg="#f5f5f5")

    button_style = {
        "font": ("Helvetica", 14),
        "width": 35,
        "bg": "#4caf50",
        "fg": "white",
        "relief": "raised",
        "borderwidth": 2,
    }

    tk.Button(root, text="Поиск по торговой точке", command=search_mcc, **button_style).pack(pady=10)
    tk.Button(root, text="Посмотреть категории", command=view_categories, **button_style).pack(pady=10)
    tk.Button(root, text="Добавить банк", command=add_bank, **button_style).pack(pady=10)
    tk.Button(root, text="Обновить категории", command=update_categories, **button_style).pack(pady=10)
    tk.Button(root, text="Удалить банк", command=delete_bank, **button_style).pack(pady=10)
    tk.Button(root, text="Выход", command=root.destroy, **button_style).pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()
