import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import random
from typing import Optional
# from cbr_daily_fetcher import get_rates, clean_data_cbr
from cbr_daily_fetcher import get_valute_to_rub_selenium,inicilize_driver
from mongo_manager.db_manager import db_manager
from constants import NOTIFICATION_DELAY, NOTIFICATION_PERIOD
from error_notifications import send_error_to_admins
from Tools.beget_api import get_account_days_left
import asyncio
from selenium.common.exceptions import WebDriverException, TimeoutException

scheduler = AsyncIOScheduler()


async def send_notifications(bot):
    try:
        groups = await db_manager.db.settings.find_one({"notifications": {"$exists": True}})
        if not groups or "notifications" not in groups:
            logging.info("No notification groups found or notifications not configured.")
            return

        try:
            rate = await db_manager.get_exchange_rate()
            percentage = await db_manager.get_markup_percentage()
        except Exception as e:
            logging.error(f"Failed to get exchange rate or markup percentage: {str(e)}")
            await send_error_to_admins(f"Не удалось получить обменный курс или комиссию")
            return

        notification_count = 0
        for group in groups["notifications"]:
            try:
                group_id = group["id"]
                await bot.send_message(
                    group_id,
                    f"Текущий курс $USD: <code>{round(rate * (1 + percentage / 100), 2)}</code> RUB"
                )
                notification_count += 1
                logging.debug(f"Notification sent to group {group_id}")
            except Exception as e:
                logging.error(f"Failed to send notification to group {group.get('id', 'unknown')}: {str(e)}")
                await send_error_to_admins(f"Не удалось отправить уведомление для группы: {group_id}")
                continue

        logging.info(f"Successfully sent notifications to {notification_count} groups")
    except Exception as e:
        logging.error(f"Error in send_notifications: {str(e)}")
        await send_error_to_admins(f"Непредвиденная ошибка во время рассылки уведомлений для групп: {e}")


async def start_notifications(bot, period=NOTIFICATION_PERIOD):
    job_id = "notifications_task"
    try:
        if scheduler.get_job(job_id):
            try:
                scheduler.remove_job(job_id)
                logging.info(f"Removed existing job with id '{job_id}'")
            except Exception as e:
                logging.error(f"Error removing existing job '{job_id}': {str(e)}")

        scheduler.add_job(send_notifications,
                          "interval",
                          args=[bot],
                          seconds=period,
                          id=job_id,
                          next_run_time=datetime.now() + timedelta(seconds=NOTIFICATION_DELAY),
                          replace_existing=True)
        logging.info(f"Notifications scheduled every {period} seconds with delay of {NOTIFICATION_DELAY} seconds.")
        return True
    except Exception as e:
        logging.error(f"Failed to schedule notifications: {str(e)}")
        await send_error_to_admins(f"Не удалось запустить отложенные уведомления: {e}")

        return False



def _fetch_rates_sequentially():

    
   
    # -----------------------------------------------------------
    active_driver,err = inicilize_driver()
    try:
        # 2. Используем драйвер внутри блока try/except для отлова ошибок соединения
        usd_rate, usd_err, thb_rate, thb_err = get_valute_to_rub_selenium(active_driver, 'usd-rub', 'thb-rub')
        return usd_rate, usd_err, thb_rate, thb_err
    except Exception as e:
        # 3. Если произошла ошибка, связанная с драйвером, закрываем его и обнуляем
        logging.error(f"Сбой WebDriver: {e}. Попытка закрыть и обнулить active_driver.")
        # Возвращаем None, чтобы вызвать повтор в цикле update_rates
        return None, f"Ошибка при парсинге: {e}", None, None
    finally:
        active_driver.quit()



MAX_RETRIES = 10
BASE_DELAY = 10  # секунд
MAX_DELAY = 300

async def update_rates():
    retries = 0
    last_error: Optional[Exception] = None

    while retries < MAX_RETRIES:
        try:
            logging.info("Fetching exchange rates...")
            
            usd_rate, usd_error, thb_rate, thb_error = await asyncio.to_thread(_fetch_rates_sequentially)

            if usd_rate is None or thb_rate is None:
                error_msg = f"Не удалось получить курс валют USD/RUB: {usd_error}\nTHB/RUB: {thb_error}"
                raise RuntimeError(error_msg)

            success = await db_manager.set_exchange_rate(usd_rate)
            thb_success = await db_manager.set_thb_exchange_rate(thb_rate)

            if not (success and thb_success):
                raise RuntimeError("Database update failed.")

            logging.info(f"Exchange rate updated successfully: USD = {usd_rate}, THB = {thb_rate}")
            return  # Успех — выходим

        except Exception as e:
            last_error = e
            logging.critical(f"Попытка {retries + 1} завершилась ошибкой: {e}", exc_info=True)
            await send_error_to_admins(f"Ошибка при обновлении курса (попытка {retries + 1}): {e}")

            delay = min(BASE_DELAY * (2 ** retries) + random.uniform(0, 1), MAX_DELAY)
            logging.info(f"Повтор через {delay:.2f} секунд...")
            await asyncio.sleep(delay)
            retries += 1

    # Все попытки исчерпаны
    if last_error is None:
        last_error = RuntimeError("Неизвестная ошибка: цикл завершился без исключений.")
    
    final_error_msg = f"Не удалось обновить курсы валют после {MAX_RETRIES} попыток. Последняя ошибка: {last_error}"
    logging.critical(final_error_msg)
    await send_error_to_admins(final_error_msg)


async def check_beget_days_left():
    try:
        days_left = get_account_days_left()
        if days_left is None:
            logging.warning("Failed to get Beget days left (returned None).")
            return

        if days_left < 22:
            msg = f"⚠️ На хостинге Beget(<a href='https://cp.beget.com'>beget.com</a>) осталось {days_left} дней до блокировки аккаунта!"
            logging.warning(msg)
            await send_error_to_admins(msg)
        else:
            logging.info(f"Beget days left: {days_left} (OK)")
    except Exception as e:
        logging.error(f"Error checking Beget days left: {e}", exc_info=True)
        await send_error_to_admins(f"Ошибка при проверке оставшихся дней на Beget: {e}")


async def on_startup():
    try:
        await db_manager.ensure_default_admins()

        if not scheduler.running:
            await update_rates()
            # scheduler.add_job(update_rates, "cron", hour=9)
            # scheduler.add_job(update_rates, "cron", hour=15)
            # scheduler.add_job(update_rates, "cron", hour=21)
            # scheduler.add_job(update_rates, "cron", hour=3)
            scheduler.add_job(update_rates, "interval", minutes=1)
            scheduler.add_job(check_beget_days_left, "cron", hour=10)
            scheduler.start()
            # logging.info("APScheduler started with daily jobs at 3,9,15,21 o'clock")
            logging.info("APScheduler started with daily jobs at every minute")

    except Exception as e:
        logging.critical(f"Error in on_startup(): {e}", exc_info=True)
        await send_error_to_admins(f"Ошибка при запуске отложенных заданий: {e}")

