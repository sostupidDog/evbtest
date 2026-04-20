# evb-test 项目构建流程

> 从零到完整框架的 AI 辅助开发历程
> 技术栈：Python 3.10+ / paramiko / Click / Rich / PyYAML / asyncio

---

## 全局架构

```
┌─────────────────────────────────────────────────────────┐
│                        evb-test                          │
│  轻量级远程设备自动化测试框架                              │
│  SSH + Talent 网口转串口 │ YAML + Python 用例            │
│  多设备并行执行          │ 内核替换/固件烧写/驱动验证      │
└─────────────────────────────────────────────────────────┘
```

---

## 开发流程图

```mermaid
flowchart TD
    START([需求分析: 远程设备自动化测试框架]) --> S1

    subgraph Phase1["阶段一: 基础框架"]
        S1[Step 1: 项目骨架\npyproject.toml / config / CLI]
        S2[Step 2: 连接层\nSSH invoke_shell + TCP串口\n后台读线程 + OutputBuffer]
        S3[Step 3: 命令执行引擎\nCommandExecutor + echo剥离]
        S4[Step 4: Python API\nDeviceHandle + TestCase]
        S5[Step 5: YAML 运行器\nphase → step 解释执行]
        S6[Step 6: Python 运行器\n动态导入 + 子类发现]
        S7[Step 7: 多设备并行\nasyncio + run_in_executor]
        S8[Step 8: 报告与日志\nRich 终端输出 + 汇总表格]
        S9[Step 9: CLI 入口\nrun / connect / check / init]
        S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8 --> S9
    end

    S9 --> S10[首次端到端验证 ✅\nSSH 连接 + YAML 用例通过]

    S10 --> FIX1[修复: 日志顺序错乱\nsend 同步 vs append 异步\n→ 移到 executor 层结构化记录]
    FIX1 --> FIX2[修复: --no-log 选项\n跳过 session log 文件生成]
    FIX2 --> FIX3[增强: 目录级用例发现\ndefault testcases/ 循环执行\n全量结果统计]

    FIX3 --> PERF{性能优化审查}
    PERF -->|H2| P1[正则预编译\n_default_prompt 编译一次]
    PERF -->|H3| P2[连接池\n同设备复用一条连接]
    PERF -->|H4| P3[列表式缓冲\nOutputBuffer list 替代字符串拼接]
    PERF -->|M1| P4[SSH Condition 等待\n替代 polling]
    PERF -->|M3| P5[合并正则 wait_for_any\n单次 read_until]
    P1 & P2 & P3 & P4 & P5 --> PDONE[性能优化完成 ✅]

    PDONE --> Phase2

    subgraph Phase2["阶段二: 生产可用性"]
        R1[连接健康检查 + 自动重连\nis_connected() → reconnect]
        R2[expect_not 负断言\n多行结果中不能出现 fail/error]
        R3[Preflight 前置环境检查\n失败则 SKIP 该设备所有用例]
        R1 --> R2 --> R3
    end

    R3 --> DOC1[更新 README + SKILL.md\nv0.2.0]

    DOC1 --> Phase3

    subgraph Phase3["阶段三: 内核替换场景"]
        F1[文件传输 API\nupload/download via SFTP]
        F2[reboot + 自动重连\n发送 reboot → 断连检测 → 重试重连\nSSH 自动检测 prompt]
        F3[修复: 首次连接 drain\nDeviceHandle 构造时 drain 残余输出]
        F1 --> F2 --> F3
    end

    F3 --> FIX4[修复: Python 多用例丢失\n一个文件多个 TestCase\n→ 每个 subclass 创建独立 task]
    FIX4 --> DOC2[更新 README + SKILL.md\nv0.3.0]

    DOC2 --> Phase4

    subgraph Phase4["阶段四: 双通道与健壮性"]
        D1[双通道测试\nSSH + serial 同设备同时使用\nsecondary_connection + use_secondary]
        D2[ANSI 转义序列修复\n\x1b[m 干扰 prompt 匹配\n→ wait_for_pattern 匹配前剥 ANSI]
        D1 --> D2
    end

    D2 --> DOC3[更新 README + SKILL.md\nv0.4.0]

    DOC3 --> DONE([框架完成 ✅])

    style START fill:#4CAF50,color:white
    style DONE fill:#4CAF50,color:white
    style PERF fill:#FF9800,color:white
    style Phase1 fill:#E3F2FD
    style Phase2 fill:#FFF3E0
    style Phase3 fill:#E8F5E9
    style Phase4 fill:#F3E5F5
```

---

## 关键技术决策

### 1. SSH 用 `invoke_shell()` 而非 `exec_command()`

```
exec_command()  → 每条命令新建 channel，无法保持状态
invoke_shell()  → 持久终端会话，支持多步交互（U-Boot → Linux）
```

### 2. 后台读线程 + Condition 变量

```
SSH/Serial 连接各自启动 daemon 读线程
    → 持续 recv → append 到 OutputBuffer
    → Condition.notify_all() 唤醒等待者
    → wait_for_pattern() 阻塞等待，零 CPU 开销
```

### 3. 连接池：按设备分组复用

```
tasks 按 device_name 分组
同一设备的所有测试共享一条连接
不同设备并行执行，信号量控制并发数
```

### 4. asyncio + run_in_executor 桥接

```
连接层是阻塞 I/O (paramiko / socket)
用 run_in_executor 在线程池中运行
asyncio 负责协调多设备任务的并发和超时
```

### 5. YAML 解释执行 vs Python 动态加载

```
YAML:  yaml.safe_load → dict → 逐 step 解释 → StepResult
Python: importlib 动态导入 → inspect 发现子类 → setup/run/teardown
```

---

## 遇到的问题与解决

| 问题 | 原因 | 解决 |
|------|------|------|
| 日志中命令和输出交错 | send() 同步记录 vs reader 线程异步 append | 移到 executor 层 `log_command_block()` |
| echo 匹配导致提前返回 | `wait_for "hello"` 匹配到命令回显 `echo hello` | execute() 先等 prompt，再检查 wait_for |
| set_session_log 不生效 | 连接池中先 connect 后 set_session_log | SSH/TCP serial 重写 set_session_log 支持已连接状态 |
| reboot 后重连失败 | 固定 sleep 2s 太短 | 改为重试循环，deadline 内反复尝试 |
| Python 多用例只报第一个 | `results[0]` 丢弃其余 | CLI 发现类名，每个 subclass 创建独立 task |
| ANSI 转义破坏 prompt 匹配 | `\x1b[m` 夹在 `#` 和空格之间 | `wait_for_pattern()` 匹配前 strip ANSI |
| 首次命令输出为空 | 连接后 MOTD/banner 残留 | DeviceHandle 构造时 `drain()` |

---

## 项目结构

```
evbtest/
├── cli.py               # Click CLI
├── config/
│   ├── schema.py        # DeviceConfig, SSHConfig, SerialTCPConfig
│   └── loader.py        # YAML 配置加载 + secondary_connection
├── connection/
│   ├── base.py          # ConnectionBase ABC
│   ├── ssh.py           # SSH invoke_shell + 读线程
│   ├── serial_tcp.py    # TCP socket + 读线程
│   ├── output_buffer.py # 线程安全缓冲 + ANSI 容忍匹配
│   └── exceptions.py    # ConnectionError, PatternTimeoutError
├── execution/
│   ├── executor.py      # CommandExecutor + ANSI 剥离
│   └── sequence.py
├── api/
│   ├── device.py        # DeviceHandle (execute/upload/download/reboot)
│   └── testcase.py      # TestCase (device/secondary_device)
├── runner/
│   ├── yaml_runner.py   # YAML 解释器
│   ├── python_runner.py # Python 加载器 + 多类发现
│   └── parallel.py      # asyncio 并行 + 连接池 + preflight + 双通道
└── reporting/
    ├── result.py        # StepResult, TestResult, ParallelRunResult
    └── logger.py        # Rich 终端输出 + SKIP 展示
```

---

## 版本演进

| 版本 | 里程碑 | 核心能力 |
|------|--------|----------|
| v0.1.0 | 基础框架 | SSH/Serial 连接 + YAML/Python 用例 + 并行执行 |
| v0.2.0 | 生产加固 | expect_not + preflight + 连接池 + 自动重连 |
| v0.3.0 | 内核替换 | upload/download SFTP + reboot 自动重连 |
| v0.4.0 | 双通道 | SSH + serial 同设备 + ANSI 修复 |
