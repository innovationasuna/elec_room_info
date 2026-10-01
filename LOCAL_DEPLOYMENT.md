# 本地部署记录

- 日期：2026-10-01
- 上游：https://github.com/sxdl/elec_room_info
- 上游基线：`c8e2cdd`（2025-03-25）
- 适配目标：广州国际校区；五山、大学城的实际兼容性未验证。
- Fork：https://github.com/innovationasuna/elec_room_info
- 本地目录：仓库根目录（以下命令均从该目录执行）。
- 本地环境：独立 `.venv`，Python 3.11.12，保留上游 requirements 中的版本；额外固定 NumPy 1.26.4 以兼容 pandas 2.0.3。上游文档的开发版本是 Python 3.8，本次没有替换系统 Python。
- 原项目是查询/CSV/提醒程序，没有网页服务。本轮先部署和验证采集，未开启定时任务、开机启动、推送或充值操作。

## 启动

从项目目录执行：

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
.venv/bin/python local_run.py init
.venv/bin/python local_run.py check
.venv/bin/python local_run.py set-token
.venv/bin/python local_run.py query
```

环境已经安装好时无需重复安装。`init` 仅在配置不存在时创建配置，不覆盖已有文件。`set-token` 在终端隐藏输入，不会回显或把 Token 放进命令行参数。也可以在本机编辑 `data/configs/config.yaml` 的 `query.bearer_token`，只填 Bearer 后的部分。新建配置权限为 0600，整个 `data/` 已被 Git 忽略。

Token 优先级为 `BEARER_TOKEN` 环境变量 > 根目录 `.env` 中的 `BEARER_TOKEN` > YAML。`.env` 被 Git 忽略，模板是 `.env.example`。环境变量和 `.env` 的 Token 不会被复制进 YAML。监控过程中更新 `.env` 可以在下一次请求生效；通过 `set-token` 更新 YAML 后需重启监控进程。

## 获取 Token

1. 打开企业微信的华工校园一卡通，进入电费查询/充值页面；确认已绑定自己的宿舍，且页面可以正常看到余额。
2. 若能在电脑浏览器打开对应 H5 页面，用开发者工具的 Network 查看 `getThirdDataByFeeItemId` 请求。
3. 在 Request Headers 找到 **`synjones-auth`**（不是猜测的 `Authorization` 字段），其值为 `Bearer ...`。使用隐藏输入命令保存在本机，不必发到聊天里。
4. 若页面只能在企业微信内打开，先确定可用的登录/调试路径；不能直接假定普通浏览器能复用登录。

Hashi-Club 还提供了[电脑版一卡通登录入口](https://ecardwxnew.scut.edu.cn/plat-pc/login)：完成统一认证和一卡通登录后，在开发者工具 Application → Session Storage 查看该站点的 `access_token`。此方法来自该分支 README，本轮尚未用真实账号验证。

## 验证与边界

- 未携带凭据的电费接口 GET 已实测返回 HTTP 401 和 `缺失令牌,鉴权失败`；证明当前网络能到达接口，不代表已取得余额。
- `check` 只验证依赖、配置和原始入口可导入，不发送请求。
- 本次 `check` 已通过：Python/requests/pandas/NumPy 正常、上游入口可导入，三个推送渠道均关闭；`query` 在未配置 Token 时按预期以退出码 2 停止，没有发送带假凭据的请求。新增脚本编译检查及 `git diff --check` 通过。
- `query` 复用上游 `ElecRoomQuery.query_elec_room_info(1)`，只查询电费，最多等待 30 秒，不发送通知。成功后把原始信息与读取时间保存到 `data/records/latest_electricity.json`，失败不覆写上次结果。
- 上游接口文字可能是“剩余电量”而非“余额元”，所以先保留原文，未将度数误标为人民币。
- 真实账户查询仍需要有效 Token；程序不会自动登录或刷新 Token。未验证长期运行稳定性。
- 上游原始循环仍会一起查询电费、空调和水费；三项绑定情况和响应都需要验证后，才适合长期运行。

取得真实数据后，如需启动上游原始循环：

```sh
.venv/bin/python local_run.py monitor
```

用 Ctrl+C 停止。保留上游连续循环和 CSV 格式；本 fork 在原循环上添加查询错误恢复：网络、鉴权或解析失败会跳过本轮写入和提醒，等待原查询间隔后再试。Token 失效仍需用户更新。CSV 写入失败、通知模块错误等不属于这次查询恢复的覆盖范围。当前本地配置查询间隔为 1200 秒，邮件、PushPlus、WxPusher 全部关闭。`local_run.py monitor` 的本地采集入口会拒绝已开启推送的配置；需要自行配置推送的使用者仍可运行上游 `main.py -c ...`。

回归测试（无真实登录、无外部通知）：

```sh
.venv/bin/python -m unittest discover -s tests -v
```

2026-10-01：13 项通过，包括鉴权错误、HTTP/JSON 异常、超时、余额单位解析、有效零值、失败不改写历史和下一轮恢复。原 CSV 读取中的未关闭文件警告也已修复，空 CSV 仅有表头时返回无记录。
