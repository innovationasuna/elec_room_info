import math
import os
import re
from pathlib import Path
import requests
from datetime import datetime
from dotenv import dotenv_values

from .record_csv import CSVRecordHandler
from .config import Config

from .log import get_logger
logger = get_logger(__name__)
DOTENV_PATH = Path(__file__).resolve().parents[2] / '.env'


class QueryError(RuntimeError):
    """An unsuccessful query must not be recorded as a zero balance."""


class AuthenticationError(QueryError):
    pass


def get_bearer_token(config):
    """Keep credentials outside tracked config without changing YAML support."""
    file_token = dotenv_values(DOTENV_PATH).get('BEARER_TOKEN') if DOTENV_PATH.exists() else None
    token = os.getenv('BEARER_TOKEN') or file_token or config['query'].get('bearer_token', '')
    token = str(token or '').strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    if not token or token == '<token>' or token.lower() == 'bearer' or any(c.isspace() for c in token):
        raise AuthenticationError('未配置有效的一卡通 Token；请设置 BEARER_TOKEN、.env 或 query.bearer_token。')
    return token


def extract_balance(information, prefix, extract_last=False):
    """Parse the existing school text format, allowing units but not error text."""
    if not isinstance(information, str):
        raise QueryError('余额字段不是文字，学校接口结构可能已变化。')
    text = information.strip()
    if text.startswith(prefix):
        text = text[len(prefix):].strip()
    if extract_last:
        text = re.split('[,，]', text)[-1].strip()
    text = text.lstrip(':：').strip()
    match = re.fullmatch(r'[¥￥]?\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(?:元|度|kWh|千瓦时)?', text, re.IGNORECASE)
    if not match:
        raise QueryError('余额文本无法识别；未将解析失败记为 0。')
    value = float(match.group(1))
    if not math.isfinite(value):
        raise QueryError('余额不是有效的有限数值。')
    return value


# def create_query_form_data(info_json):
#     aids = ['0030000000004901', '0030000000011101', '0030000000011201']
#     aid = aids[eval(info_json['type'])]
#     area = '{"area":"","areaname":""}'
#     building = (f'{{"building":"{info_json["building"].split("&&&")[0]}","buildingid":'
#                 f'"{info_json["building"].split("&&&")[1]}"}}')
#     floor = f'{{"floor":"{info_json["floor"].split("&&&")[0]}","floorid":"{info_json["floor"].split("&&&")[1]}"}}'
#     room = f'{{"room":"{info_json["room"].split("&&&")[0]}","roomid":"{info_json["room"].split("&&&")[1]}"}}'
#     return {
#         'aid': aid,
#         'area': area,
#         'building': building,
#         'floor': floor,
#         'room': room
#     }


# def create_url(api_name):
#     v = random.randint(1, 100)  # 生成1到100的随机整数
#     return f'https://weixinchongzhi.scut.edu.cn/wechat/{api_name}.html?v={v}'


class ElecRoomQuery:
    """
    宿舍水电空调余额查询类
    """
    def __init__(self, **kwargs):
        """
        :param kwargs: 'session_id': 浏览器会话cookie, 'auth_link': 企业微信学生一卡通应用链接, 'csv_file_path': csv文件保存路径
        """
        self._config: Config = kwargs.get('config')

        self._bearer_token = get_bearer_token(self._config)
        self._timeout = float(self._config['query'].get('timeout_seconds', 20))
        if not math.isfinite(self._timeout) or self._timeout <= 0:
            raise ValueError('query.timeout_seconds 必须是正数。')

        # self._session = self._config['query']['session_id']
        # self._auth_link = self._cfg['query']['auth_link']

        # self._session = kwargs.get('session_id', None)
        # self._auth_link = kwargs.get('auth_link', None)

        # if self._session == '' and self._auth_link == '':
        #     logger.error('ElecRoomQuery needs session_id or auth_link')
        #     raise ValueError('ElecRoomQuery needs session_id or auth_link')

        self._headers = {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Host': 'ecardwxnew.scut.edu.cn',
            'Referer': 'https://ecardwxnew.scut.edu.cn/plat/shouyeUser',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/107.0.5304.110 Safari/537.36 Language/zh ColorScheme/Light wxwork/4.1.32 ('
                          'MicroMessenger/6.2) WindowsWechat  MailPlugin_Electron WeMail embeddisk wwmver/3.26.15.675',
            'synAccessSource': 'wechat-work',
            'sec-ch-ua': '"Chromium";v="107"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'synjones-auth': f"Bearer {self._bearer_token}"
        }
        # self._cookies = {'JSESSIONID': self._session}

        # self._WAT_FORM_DATA = create_query_form_data(self.auto_query(type=0))
        # self._ELE_FORM_DATA = create_query_form_data(self.auto_query(type=1))
        # self._AIR_FORM_DATA = create_query_form_data(self.auto_query(type=2))
        # logger.debug(f'WAT_FORM_DATA: {self._WAT_FORM_DATA}')
        # logger.debug(f'ELE_FORM_DATA: {self._ELE_FORM_DATA}')
        # logger.debug(f'AIR_FORM_DATA: {self._AIR_FORM_DATA}')

        self._CSV_FILE_PATH = self._config['record_csv']['csv_file_path']


    # def _get_session_from_auth_link(self, auth_link):
    #     """企业微信 > 校园一卡通， 分享的连接"""
    #     headers = {
    #         'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,'
    #                   '*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    #         'Accept-Encoding': 'gzip, deflate, br',
    #         'Accept-Language': 'zh-CN,zh;q=0.9',
    #         'Connection': 'keep-alive',
    #         'Host': 'ecardwxnew.scut.edu.cn',
    #         'referer': 'https://ecardwxnew.scut.edu.cn/plat/shouyeUser',
    #         'Sec-Fetch-Dest': 'empty',
    #         'Sec-Fetch-Mode': 'cors',
    #         'Sec-Fetch-Site': 'same-origin',
    #         'Sec-Fetch-User': '?1',
    #         'Upgrade-Insecure-Requests': '1',
    #         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
    #                       'Chrome/107.0.5304.110 Safari/537.36 Language/zh ColorScheme/Light wxwork/4.1.32 ('
    #                       'MicroMessenger/6.2) WindowsWechat  MailPlugin_Electron WeMail embeddisk wwmver/3.26.15.675',
    #         'sec-ch-ua': '"Chromium";v="107"',
    #         'sec-ch-ua-mobile': '?0',
    #         'sec-ch-ua-platform': '"Windows"',
    #         'synAccessSource': 'wechat-work',
    #     }
    #     try:
    #         response = requests.get(auth_link, headers=headers)
    #
    #         if response.status_code == 200:
    #             set_cookie = response.headers.get('Set-Cookie')
    #             if set_cookie:
    #                 logger.debug(f'set_cookie: {set_cookie}')
    #                 self._session = set_cookie.split(';')[0].split('=')[1]
    #             else:
    #                 logger.debug(f'set_cookie: None')
    #                 raise Exception("Set-Cookie header not found in the response")
    #         else:
    #             response.raise_for_status()  # 如果请求失败，会抛出异常
    #     except requests.RequestException as e:
    #         logger.error(f'Error: {e}')


    def refresh_session(self):
        """session失效刷新"""
        pass

    def query_elec_room_info(self, type):
        """余额查询 type: 1(电)，2(空调)，3(水)"""
        base_url = 'https://ecardwxnew.scut.edu.cn'
        url = base_url + '/charge/feeitem/getThirdDataByFeeItemId' + f'?feeitemid={type}' + '&synAccessSource=wechat-work'
        # params = {
        #     'aid': aid,
        #     'area': area,
        #     'building': building,
        #     'floor': floor,
        #     'room': room
        # }

        try:
            # Re-read env/.env credentials so a refreshed token can be used next round.
            self._headers['synjones-auth'] = f'Bearer {get_bearer_token(self._config)}'
            response = requests.get(url, headers=self._headers, timeout=self._timeout)
            if response.status_code in (401, 403):
                raise AuthenticationError('一卡通鉴权失败，Token 可能已过期；请更新 Token。')
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as e:
            raise QueryError(f'查询项目 {type} 失败（{e.__class__.__name__}），本轮不写入余额。') from e
        except ValueError as e:
            raise QueryError('学校接口未返回有效 JSON；请检查登录状态。') from e
        if not isinstance(payload, dict):
            raise QueryError('学校接口返回结构异常。')
        if str(payload.get('code')) in ('401', '403'):
            raise AuthenticationError('一卡通鉴权失败，Token 可能已过期；请更新 Token。')
        try:
            information = payload['map']['showData']['信息']
        except (KeyError, TypeError) as e:
            raise QueryError('学校接口未返回房间信息；请确认宿舍已绑定、Token 有效。') from e
        if not isinstance(information, str) or not information.strip():
            raise QueryError('学校接口返回了空的房间信息。')
        return information

    # def auto_query(self, type: int):
    #     """
    #     房间信息查询
    #     :param type: 0(水)，1(电)，2(空调)
    #     :return: {'account','building','floor','id','refreshTime','room','schoolId','type'}
    #     """
    #     url = create_url(api_name='icinfo/autoQuery')
    #     params = {
    #         'type': type
    #     }
    #
    #     try:
    #         response = requests.post(url, data=params, cookies=self._cookies, headers=self._headers)
    #         response.raise_for_status()
    #         response_json = response.json()
    #         logger.debug(f'autoQuery response: {response_json}')
    #         if response_json == 1:
    #             # session 过期
    #             # self._cfg.set('query', 'session_id', '')
    #             self._config.query.session_id = ''
    #             self._config.save()
    #             logger.critical(f'session expired, refresh your auth link')
    #         return response_json
    #     except requests.RequestException as e:
    #         logger.error('Error autoQuery:', e)

    def query_balance(self):
        """
        查询水电空调余额
        :return: {'timestamp'. 'water_balance', 'electricity_balance', 'air_conditioner_balance'}
        """
        query_response = self.query_elec_room_info(1), self.query_elec_room_info(
            2), self.query_elec_room_info(3)
        record_data = {
            'timestamp': datetime.now().isoformat(),
            'electricity_balance': extract_balance(query_response[0], '房间当前剩余电量'),
            'air_conditioner_balance': extract_balance(query_response[1], '房间当前剩余金额'),
            'water_balance': extract_balance(query_response[2], '剩余水费', extract_last=True)
        }
        return record_data

    def record_data(self):
        """disposed"""
        record_data = self.query_balance()
        recorder = CSVRecordHandler(csv_file_path=self._CSV_FILE_PATH)
        recorder.record(record_data)


if __name__ == '__main__':
    from pathlib import Path
    from elec_room_info.utils.config import Config

    CONFIG_PATH = Path(__file__).parents[2] / 'data' / 'configs' / 'config.yaml'
    query = ElecRoomQuery(config=Config(CONFIG_PATH))
    query.record_data()
