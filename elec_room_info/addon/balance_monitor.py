"""余额监控插件"""
from datetime import datetime

from elec_room_info.utils.record_csv import CSVRecordHandler
from elec_room_info.utils.message_sender.mail import EmailSender
from elec_room_info.utils.message_sender.sender import Sender

from elec_room_info.utils.log import get_logger
logger = get_logger(__name__)


class BalanceMonitor:
    def __init__(self, **kwargs):
        self._config = kwargs.get('config')

        self.csv_file_path = self._config['record_csv']['csv_file_path']
        self.csv_handler = CSVRecordHandler(self.csv_file_path)
        self.threshold = self._config.to_dict(self._config['balance_monitor']['threshold'])
        self.sender = Sender(config=self._config)

        self._last_check_email_time = None

    def once(self):
        current_time = datetime.now()
        if self._config.addon.balance_monitor:
            if self._last_check_email_time is None or (current_time - self._last_check_email_time).seconds > 1800:
                self.check()
        if self._config.addon.deposit_monitor:
            self.deposit()

    def check(self):
        last_record = self.csv_handler.get_latest()
        if last_record is None:
            return
        logger.debug('last_record: %s', last_record)

        if last_record['water_balance'] < self.threshold['water_balance'] or \
                last_record['electricity_balance'] < self.threshold['electricity_balance'] or \
                last_record['air_conditioner_balance'] < self.threshold['air_conditioner_balance']:
            logger.info(f'余额不足: {last_record}')
            subject = '宿舍余额预警'
            message = (f"余额不足：\n 水费余额：{last_record['water_balance']}\n 电费余额：{last_record['electricity_balance']}\n "
                       f"空调余额：{last_record['air_conditioner_balance']}")
            self.sender.send(subject=subject, message=message)
            self._last_check_email_time = datetime.now()


    def deposit(self):
        # 充值检测
        last_record = self.csv_handler.get_latest()
        last_second_record = self.csv_handler.get_last_second()
        logger.debug('last_record: %s', last_record)
        logger.debug('last_second_record: %s', last_second_record)
        if last_record is None or last_second_record is None: return

        message = ''

        if last_record['water_balance'] > last_second_record['water_balance']:
            message += f"水费充值{last_record['water_balance'] - last_second_record['water_balance']}元\n"
        if last_record['electricity_balance'] > last_second_record['electricity_balance']:
            message += f"电费充值{last_record['electricity_balance'] - last_second_record['electricity_balance']}元\n"
        if last_record['air_conditioner_balance'] > last_second_record['air_conditioner_balance']:
            message += (f"空调充值{last_record['air_conditioner_balance'] - last_second_record['air_conditioner_balance']}"
                        f"元\n")

        if message != '':
            logger.info(f'检测到充值: {last_record}')
            subject = '宿舍充值检测'
            self.sender.send(subject=subject, message=message)


if __name__ == '__main__':
    from elec_room_info.utils.config import Config
    import os
    os.chdir('../..')
    test_config = Config()
    test_config.load('test_config.ini', encoding='utf-8')
    monitor = BalanceMonitor(config=test_config)
    monitor.check()
    monitor.deposit()
