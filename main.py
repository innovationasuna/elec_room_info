import argparse
import threading
import time

from elec_room_info.utils.query import ElecRoomQuery, QueryError
from elec_room_info.utils.config import Config
from omegaconf import DictConfig, OmegaConf
from elec_room_info.addon import BalanceMonitor

from elec_room_info.utils.log import get_logger
logger = get_logger(__name__)

# QUERY_INTERVAL = 120  # 2 * 60  # 2分钟，以秒为单位
# RECORD = True


class ElecRoomInfo:
    def __init__(self, conf: Config):
        self._cfg = conf
        self._query = ElecRoomQuery(config=self._cfg)
        self._monitor = BalanceMonitor(config=self._cfg)
        self._query_interval = self._cfg['record_csv']['query_interval']

    def run(self):
        while True:
            try:
                self._query.record_data()
            except QueryError as error:
                logger.warning('本轮查询失败，保留历史记录，下一轮重试：%s', error)
            else:
                self._monitor.once()
            logger.info(f"休眠 {self._query_interval} 秒，下次查询时间："
                        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + self._query_interval))}")
            time.sleep(self._query_interval)

    # def run(self):
    #     # 定义query线程函数
    #     def query_thread():
    #         while True:
    #             self._query.record_data()
    #             logger.info(f"查询线程休眠 {self._query_interval} 秒，下次查询时间："
    #                     f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + self._query_interval))}")
    #             time.sleep(self._query_interval)
        
    #     # 定义monitor线程函数
    #     def monitor_thread():
    #         while True:
    #             self._monitor.once()
    #             time.sleep(10)  # 可以根据需要调整monitor的执行间隔
        
    #     # 创建并启动线程
    #     query_t = threading.Thread(target=query_thread)
    #     monitor_t = threading.Thread(target=monitor_thread)
        
    #     query_t.daemon = True  # 设置为守护线程，主线程退出时自动结束
    #     monitor_t.daemon = True
        
    #     query_t.start()
    #     monitor_t.start()
        
    #     # 主线程保持运行
    #     try:
    #         while True:
    #             time.sleep(1)
    #     except KeyboardInterrupt:
    #         logger.info("接收到中断信号，停止运行")


def start_periodic_queries(conf: DictConfig):
    query = ElecRoomQuery(config=conf)
    monitor = BalanceMonitor(config=conf) if conf['addon']['balance_monitor'] else None
    while True:
        query.record_data()
        if monitor is not None:
            monitor.check()
            monitor.deposit()
        time.sleep(conf.record_csv.query_interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', help='config file', default="./data/configs/config.yaml")
    args = parser.parse_args()

    # config = Config()
    # config.load(args.config)

    config = Config(args.config)

    # if RECORD:
    #     thread = threading.Thread(target=start_periodic_queries, args=[config,])  # , daemon=True
    #     thread.start()

    ElecRoomInfo(config).run()
