import csv
import pandas as pd
from datetime import datetime
from pathlib import Path

from .log import get_logger
logger = get_logger(__name__)


# 文件路径
# CSV_FILE_PATH = './data/records/query_data.csv'
CSV_FILE_PATH = Path(__package__).absolute().parent / 'data' / 'records' / 'query_data.csv'


class CSVRecordHandler:
    def __init__(self, csv_file_path=None):
        if csv_file_path is None or csv_file_path == '':
            csv_file_path = CSV_FILE_PATH
        self._CSV_FILE_PATH = csv_file_path
        self.init_csv()

    def init_csv(self):
        # 检查文件是否存在
        if not Path(self._CSV_FILE_PATH).exists():
            # 如果文件不存在，则创建文件并写入表头
            Path(self._CSV_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
            with open(self._CSV_FILE_PATH, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['timestamp', 'water_balance', 'electricity_balance', 'air_conditioner_balance'])
            logger.debug(f'CSV file {self._CSV_FILE_PATH} created')
        else:
            logger.debug(f"CSV file {self._CSV_FILE_PATH} already exists.")

    def record(self, data):
        """
        :param data['timestamp','water_balance','electricity_balance','air_conditioner_balance']
        :return:
        """
        with open(self._CSV_FILE_PATH, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([
                data['timestamp'],
                data['water_balance'],
                data['electricity_balance'],
                data['air_conditioner_balance']
            ])

    def get_latest(self):
        # 读取CSV文件的最后一行
        csv_data = pd.read_csv(self._CSV_FILE_PATH)
        if csv_data.empty:
            return None
        last_row = csv_data.iloc[-1]
        return {
            'timestamp': last_row['timestamp'],
            'water_balance': last_row['water_balance'],
            'electricity_balance': last_row['electricity_balance'],
            'air_conditioner_balance': last_row['air_conditioner_balance']
        }

    def get_last_second(self):
        csv_data = pd.read_csv(self._CSV_FILE_PATH)
        if len(csv_data) < 2:
            return None
        line_data = csv_data.iloc[-2]
        return {
            'timestamp': line_data['timestamp'],
            'water_balance': line_data['water_balance'],
            'electricity_balance': line_data['electricity_balance'],
            'air_conditioner_balance': line_data['air_conditioner_balance']
        }


if __name__ == '__main__':
    CSV_FILE_PATH = '../records/test_data.csv'
    # 示例数据
    query_response = {
        'timestamp': datetime.now().isoformat(),
        'water_balance': 123.45,
        'electricity_balance': 67.89,
        'air_conditioner_balance': 45.67
    }

    # 初始化和记录数据
    recorder = CSVRecordHandler(csv_file_path=CSV_FILE_PATH)
    # recorder.record(query_response)

    print(recorder.get_latest())
