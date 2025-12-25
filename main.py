import os
import threading

import uvicorn

from core.config import cfg
from core.print import print_warning
from driver.auth import *


if __name__ == "__main__":
    def _mask(v: str) -> str:
        s = str(v or "")
        if not s:
            return ""
        if len(s) <= 10:
            return s[:2] + "***"
        return s[:4] + "***" + s[-4:]

    print("环境变量(敏感信息已脱敏):")
    for k, v in os.environ.items():
        upper = str(k).upper()
        if any(x in upper for x in ("KEY", "TOKEN", "COOKIE", "PASSWORD", "SECRET")):
            print(f"{k}={_mask(v)}")
        else:
            print(f"{k}={v}")

    if cfg.args.init == "True":
        import init_sys as init

        init.init()

    if cfg.args.job == "True" and cfg.get("server.enable_job", False):
        from jobs import start_all_task

        threading.Thread(target=start_all_task, daemon=False).start()
    else:
        print_warning("未开启定时任务")

    print("启动服务器")
    AutoReload = cfg.get("server.auto_reload", False)
    thread = int(cfg.get("server.threads", 1) or 1)

    # IMPORTANT: this project uses in-process queues (thread workers). Running multiple uvicorn
    # workers (processes) would create multiple independent queues and duplicate schedulers.
    # Force workers=1 for correctness; scale refresh/insights via QUEUE_WORKERS instead.
    if thread != 1:
        print_warning(f"检测到 server.threads={thread}，将强制设置为 1（避免多进程导致队列/定时任务重复）")
        thread = 1

    uvicorn.run(
        "web:app",
        host="0.0.0.0",
        port=int(cfg.get("port", 8001)),
        reload=AutoReload,
        reload_dirs=[".", "core", "apis", "driver", "jobs", "tools", "schemas"],
        reload_excludes=["static", "data", "web_ui", "compose"],
        workers=thread,
    )
