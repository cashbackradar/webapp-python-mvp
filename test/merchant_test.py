import requests
from bs4 import BeautifulSoup

def get_mcc_description(mcc_code):
    url = f"https://merchantpoint.ru/mcc/{mcc_code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print("Ошибка запроса:", response.status_code)
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Ищем заголовок с MCC кодом и его описанием
    title_tag = soup.find("h1")
    if title_tag:
        description = title_tag.text.strip().split("-", 1)[-1].strip()
        return description
    else:
        print("Описание для MCC не найдено.")
        return None

mcc_code = "5411"  # Пример MCC-кода
mcc_description = get_mcc_description(mcc_code)

if mcc_description:
    print(mcc_description)
