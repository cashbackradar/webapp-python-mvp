import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

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
    url = f"https://merchantpoint.ru/mcc/{mcc_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        return "Описание не найдено"
    
    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.find("h1")
    if title_tag:
        return title_tag.text.strip().split("-", 1)[-1].strip()
    return "Описание не найдено"

def get_mcc_data(store_name):
    df = get_mcc_codes(store_name)
    if df is None:
        return pd.DataFrame(columns=["Название торговой точки", "mcc", "Описание"])
    
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

# Пример использования:
store_name = "Магнит"
mcc_data = get_mcc_data(store_name)
print(mcc_data.columns)
print(mcc_data[:10])
