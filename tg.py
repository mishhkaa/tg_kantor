import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
from concurrent.futures import ThreadPoolExecutor
import re

from dotenv import load_dotenv
import os

load_dotenv()  # Завантажує .env файл
TOKEN = os.getenv("TOKEN")
# Джерела обмінників
EXCHANGE_SOURCES = {
    "kantor_live": "https://kantor.live/kantory/lublin/{}",
    "kantor_annajanek": "https://kantorannajanek.pl/",
    "kantor_olimp": "https://www.kantorolimp.pl/"
}

CURRENCIES = [
    "USD", "EUR", "GBP", "CZK", "NOK", "DKK", "HRK", "HUF", "SEK", "TRY", "UAH",
    "LTL", "THB", "HKD", "ILS", "MOP", "SCR", "MXN", "CVE", "RUB", "ZAR", "SAR",
    "MYR", "QAR", "AED", "CLP", "RSD", "KES", "AZN", "AUD", "BGN", "TWD", "COP",
    "CRC", "BHD", "TND", "OMR", "MVR", "RON", "JOD", "CHF", "CAD", "GEL", "LKR",
    "MDL", "EEK", "NZD", "VND", "PEN", "UZS", "BRL", "EGP", "PHP", "ISK", "MUR",
    "CNY", "BAM", "INR", "ALL", "MAD", "AMD", "KRW", "DOP", "MKD", "KWD", "TZS",
    "BYN", "KZT", "SGD", "JPY", "LVL"
]
HEADERS = {"User-Agent": "Mozilla/5.0"}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)


def clean_rate(rate):
    """Очищення чисел, перетворення коми в крапку."""
    rate = rate.replace(",", ".")
    match = re.search(r"\d+(\.\d+)?", rate)
    return float(match.group()) if match else None


def fetch_kantor_live(currency):
    """Парсинг kantor.live"""
    url = EXCHANGE_SOURCES["kantor_live"].format(currency)
    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        if response.status_code != 200:
            return []
    except requests.exceptions.RequestException as e:
        print(f"⚠ Не вдалося отримати дані з {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    kantors = soup.find_all("tr", class_="d-flex flex-column d-md-table-row w-100 card-wrapper card-simple")
    data = []
    for kantor in kantors:
        try:
            name = kantor.find("a", class_="kantor-name").text.strip()
            address = kantor.find("td", class_="border-0 align-middle kantor-address").text.strip().split("\n")[0]
            rates = kantor.find_all("div", class_="currency-rate-value")
            if len(rates) >= 2:
                sell_rate = clean_rate(rates[0].text.strip())
                buy_rate = clean_rate(rates[1].text.strip())
                if sell_rate and buy_rate:
                    data.append([name, address, currency, sell_rate, buy_rate])
        except:
            continue
    return data


def get_all_rates():
    """Отримання всіх курсів валют"""
    all_data = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_kantor_live, CURRENCIES)
        for result in results:
            all_data.extend(result)

    return all_data


def get_profitable_opportunities():
    """Аналіз найвигідніших пропозицій"""
    all_data = get_all_rates()
    opportunities = []

    for currency in CURRENCIES:
        filtered_data = [x for x in all_data if x[2] == currency]
        if not filtered_data:
            continue

        best_buy = min(filtered_data, key=lambda x: x[4], default=None)
        best_sell = max(filtered_data, key=lambda x: x[3], default=None)

        if best_buy and best_sell and best_buy[0] != best_sell[0] and best_sell[3] > best_buy[4]:
            profit = ((best_sell[3] - best_buy[4]) / best_buy[4]) * 100
            opportunities.append([
                currency, best_buy[0], best_buy[1], best_buy[4],
                best_sell[0], best_sell[1], best_sell[3], round(profit, 2)
            ])

    return opportunities


def main_menu():
    """Головне меню з кнопками"""
    keyboard = [
        [InlineKeyboardButton("📈 Ринок", callback_data="market")],
        [InlineKeyboardButton("💰 Профітні пропозиції", callback_data="profit")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: CallbackContext) -> None:
    """Відображення головного меню"""
    await update.message.reply_text(
        "👋 Вітаю в боті обміну валют!\n\n"
        "🔹 Натисни кнопку, щоб отримати курси валют або знайти найвигідніші пропозиції.",
        reply_markup=main_menu()
    )


async def market(update: Update, context: CallbackContext) -> None:
    """Надсилання всіх курсів валют"""
    query = update.callback_query
    await query.answer()

    all_data = get_all_rates()
    message = "📊 <b>Курси валют</b>:\n\n"

    for item in all_data[:10]:  # Топ-10 обмінників
        message += (
            f"🏦 <b>{item[0]}</b>\n📍 {item[1]}\n"
            f"💰 <b>{item[2]}</b> | 🔵 Купівля: <b>{item[4]}</b> | 🔴 Продаж: <b>{item[3]}</b>\n\n"
        )

    await query.edit_message_text(message if message else "❌ Дані недоступні", parse_mode="HTML", reply_markup=main_menu())


async def profit(update: Update, context: CallbackContext) -> None:
    """Надсилання найвигідніших пропозицій"""
    query = update.callback_query
    await query.answer()

    opportunities = get_profitable_opportunities()
    message = "💰 <b>Найвигідніші арбітражні пропозиції</b>:\n\n"

    if opportunities:
        for item in opportunities[:5]:  # Топ-5 вигідних варіантів
            message += (
                f"💰 <b>{item[0]}</b>\n"
                f"🔵 Купити в <b>{item[1]}</b> ({item[2]}) за <b>{item[3]}</b>\n"
                f"🔴 Продати в <b>{item[4]}</b> ({item[5]}) за <b>{item[6]}</b>\n"
                f"📈 Прибуток: <b>{item[7]}%</b>\n\n"
            )
    else:
        message += "❌ Вигідних можливостей немає."

    await query.edit_message_text(message, parse_mode="HTML", reply_markup=main_menu())


def main():
    """Запуск Telegram-бота"""
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(market, pattern="market"))
    app.add_handler(CallbackQueryHandler(profit, pattern="profit"))

    print("Бот запущено 🚀")
    app.run_polling()


if __name__ == "__main__":
    main()
