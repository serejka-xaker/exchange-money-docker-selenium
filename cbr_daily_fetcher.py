import random
import logging
from selenium.webdriver.common.action_chains import ActionChains
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException,ElementClickInterceptedException
import time
import subprocess
import os

def inicilize_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')  # Фоновый режим
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument("--disable-crash-reporter")
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-images')
    chrome_options.add_argument('--disable-background-timer-throttling')
    chrome_options.add_argument('--disable-renderer-backgrounding')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.set_capability('pageLoadStrategy', "eager")
    # chrome_options.add_argument(f'--user-agent=Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)')
    chrome_options.add_argument(f'--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.183 Safari/537.36')
    chrome_options.add_argument('window-size=375,812') # Имитация реального размера экрана
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-backgrounding-occluded-windows')
    chrome_options.add_argument('--blink-settings=imagesEnabled=false') # Отключаем, если не нужны изображения
    chrome_options.add_argument("accept-language=ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7") # Установите язык
    driver = None
    try:
        driver = webdriver.Remote(command_executor='http://selenium:4444', options=chrome_options)
        # driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("""
            Object.defineProperty(Notification, 'permission', {
                get: () => 'default'
            });
        """)
    except WebDriverException as e:
        error_msg = f"Ошибка инициализации WebDriver: {e}"
        logging.error(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Критическая ошибка в get_valute_to_rub_selenium(): {e}"
        logging.critical(error_msg)
        return None, error_msg
    finally:
        driver.get("https://google.com/")
    return driver,None



def fetch_rate(driver, pair: str):
            try:
                # 1. ИСПРАВЛЕНИЕ: УДАЛЕН ПРОБЕЛ в URL
                url = f"https://ru.investing.com/currencies/{pair}" 
                driver.get(url)
                # Пауза, чтобы дать странице начать загрузку и появиться баннеру
                time.sleep(random.randint(5, 10)) 
                logging.info(f"Переход на URL: {url}")
                # check_and_click_cloudflare_captcha_sync(driver, timeout=30)

                try:
                    # Ожидаем кнопку "I Accept" с небольшим таймаутом (например, 10 секунд)
                    cookie_wait = WebDriverWait(driver, 15)
                    cookie_accept_button = cookie_wait.until(
                        EC.element_to_be_clickable((By.ID, 'onetrust-accept-btn-handler'))
                    )
                    # Клик, если кнопка найдена
                    cookie_accept_button.click()
                    logging.info("Баннер cookie успешно принят (клик по 'I Accept').")
                    time.sleep(2) # Пауза для исчезновения баннера и стабилизации DOM
                
                # 2. МЕХАНИЗМ ЗАЩИТЫ: Если кнопка не найдена за 10 секунд (TimeoutException),
                # этот блок перехватывает ошибку, и код продолжает работу
                except TimeoutException:
                    logging.info("Баннер cookie не обнаружен или загружается слишком долго. Продолжаем...")
                    pass # Просто пропускаем этот шаг и идем дальше
                except Exception as e:
                    # Обработка других возможных ошибок при клике (например, ElementClickInterceptedException)
                    logging.warning(f"Ошибка при взаимодействии с баннером cookie: {e}")
                    pass 
                
                # 3. УВЕЛИЧЕННЫЙ ТАЙМАУТ для основного элемента
                wait = WebDriverWait(driver, 60) 
                price_element = wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-test="instrument-price-last"]'))
                )
                rate = price_element.text.replace(',', '.')
                return round(float(rate), 4), None
                
            except TimeoutException as e:
                error_msg = f"Таймаут для {pair}: {e}"
                logging.error(error_msg)
                return None, error_msg
            except ValueError as e:
                error_msg = f"Ошибка преобразования для {pair}: {e}"
                logging.error(error_msg)
                return None, error_msg
            except Exception as e:
                error_msg = f"Неожиданная ошибка для {pair}: {e}"
                logging.error(error_msg)
                return None, error_msg





def get_valute_to_rub_selenium(active_driver, valute_pair: str,valute_pair_sec: str):

    usd_rate, usd_err = fetch_rate(active_driver, valute_pair)
    thb_rate, thb_err = fetch_rate(active_driver, valute_pair_sec)
    
    return usd_rate, usd_err, thb_rate, thb_err

    