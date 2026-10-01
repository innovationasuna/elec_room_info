"""Local setup and one-shot electricity query; reuse upstream query/monitor code."""
import argparse
import getpass
import json
import logging
import os
from pathlib import Path
import runpy
import signal
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)  # Upstream resolves logs and default CSV relative to cwd.
from elec_room_info.utils.config import Config
from elec_room_info.utils.query import (
    ElecRoomQuery, QueryError, AuthenticationError, get_bearer_token, extract_balance,
)

CONFIG = ROOT / "data/configs/config.yaml"


def require_token(config):
    try:
        return get_bearer_token(config)
    except AuthenticationError:
        raise ValueError("尚未配置一卡通 Token。运行 .venv/bin/python local_run.py set-token，在终端隐藏输入。")


def token_configured(config):
    try:
        get_bearer_token(config)
        return True
    except AuthenticationError:
        return False


def deadline(*_):
    raise TimeoutError("查询超过 30 秒，已停止此次请求。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "check", "set-token", "query", "monitor"])
    args = parser.parse_args()
    if args.action == "init":
        if CONFIG.exists():
            print("本地配置已存在，保持原样。")
            return
        previous_mask = os.umask(0o077)
        try:
            Config.auto_config(CONFIG)
            config = Config(CONFIG)
            config.record_csv.csv_file_path = './data/records/query_data.csv'
            config.record_csv.query_interval = 1200
            config.save()
        finally:
            os.umask(previous_mask)
        print("本地配置已创建，所有通知渠道默认关闭。")
        return
    if not CONFIG.exists():
        raise ValueError("请先运行 .venv/bin/python local_run.py init 创建本地配置。")
    config = Config(CONFIG)
    # Only the query result is displayed; no raw response payload logging here.
    logging.getLogger().setLevel(logging.WARNING)

    if args.action == "set-token":
        token = getpass.getpass("粘贴 synjones-auth 的 Token（输入隐藏）: ").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token or token.lower() == 'bearer' or token == '<token>' or any(c.isspace() for c in token):
            raise ValueError("Token 为空或含空白字符，未保存。")
        config.query.bearer_token = token
        config.save()
        CONFIG.chmod(0o600)
        print("Token 已保存到本机配置文件，未发起网络请求。")
        return

    if args.action == "check":
        import requests
        import pandas
        import numpy
        from main import ElecRoomInfo
        print(json.dumps({
            "python": sys.version.split()[0],
            "requests": requests.__version__, "pandas": pandas.__version__,
            "numpy": numpy.__version__, "upstream_entrypoint_import": "ok",
            "token_configured": token_configured(config),
            "notification_channels": {k: bool(config[k].enable)
                                      for k in ("email", "pushplus", "wxpusher")},
            "query_interval_seconds": config.record_csv.query_interval,
        }, ensure_ascii=False, indent=2))
        return

    require_token(config)
    if args.action == "monitor":
        # Preserve the original loop, CSV recording, balance and deposit monitors.
        # Notifications require separate explicit configuration/authorization.
        if any(config[k].enable for k in ("email", "pushplus", "wxpusher")):
            raise ValueError("当前本地部署仅验证采集；请关闭通知渠道后启动。")
        sys.argv = [str(ROOT / "main.py"), "-c", str(CONFIG)]
        runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
        return

    previous = signal.signal(signal.SIGALRM, deadline)
    signal.alarm(30)
    try:
        information = ElecRoomQuery(config=config).query_elec_room_info(1)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    if not isinstance(information, str) or not information.strip():
        raise ValueError("未取得有效电费信息；请检查 Token 是否过期、宿舍是否已绑定。")
    result = {
        "source": "SCUT ecard / feeitemid=1",
        "fetched_at": datetime.now().astimezone().isoformat(),
        "information": information,
        "value": extract_balance(information, '房间当前剩余电量'),
        "metric": "electricity_remaining",
    }
    destination = ROOT / "data/records/latest_electricity.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, TimeoutError, QueryError) as error:
        message = str(error) if isinstance(error, (ValueError, TimeoutError, QueryError)) else "学校响应结构与上游预期不符；需要检查登录状态或接口变化。"
        print(message, file=sys.stderr)
        sys.exit(2)
