from main import app, update_all_station_wait_times, remove_completed_vehicles
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import time

def start_scheduler():
    print("Starting scheduler...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_station_wait_times, 'interval', minutes=1)
    scheduler.add_job(remove_completed_vehicles, 'interval', minutes=1)
    scheduler.start()
    return scheduler

if __name__ == "__main__":
    with app.app_context():
        scheduler = start_scheduler()
        print("Scheduler is running...")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()