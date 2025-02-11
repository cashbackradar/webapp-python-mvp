import requests
from bs4 import BeautifulSoup
import pandas as pd

def get_mcc_codes(store_name):
    url = "https://mcc-codes.ru/search/"
    params = {"q": store_name}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, params=params, headers=headers)
    
    if response.status_code != 200:
        print("Ошибка запроса:", response.status_code)
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_="table")
    
    if not table:
        print("Таблица не найдена.")
        return None
    
    headers = [th.text.strip() for th in table.find_all("th")]
    rows = table.find_all("tr")[1:]  # Пропускаем заголовок таблицы
    data = []
    
    for row in rows:
        cols = row.find_all("td")
        data.append([col.text.strip() for col in cols])
    
    df = pd.DataFrame(data, columns=headers)
    return df

store_name = "Магнит"
df = get_mcc_codes(store_name)
if df is not None:
    print(df.columns)
    for index, row in df.head(2).iterrows():
        print(row)
