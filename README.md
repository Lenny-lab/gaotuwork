# 高途排课脑 ClassMind（第一阶段 MVP）

这是一个以 OR-Tools CP-SAT 为核心的可运行智能排课系统。AI 认知层负责理解与解释的产品设计，约束求解器负责可靠地产生零硬冲突课表。

## 已实现

- 教师、教室、班级、课程、时间槽数据模型
- 教师资质、教室容量、课程设备要求
- 教师、教室、班级不可用时间
- 教师/教室/班级同一时段零冲突
- 每门课程规定课次完整排入
- JSON 演示数据、结果输出与独立二次校验
- 正常、硬约束、不可行场景单元测试
- 学生体验、教师稳定、校区效率三套候选策略及评分卡
- 可视化教务驾驶舱与本地 REST API

## 一键运行

在 PowerShell 中执行：

```powershell
.\run.ps1
```

输出位于 `output/schedule.json`。成功标准是状态为 `OPTIMAL` 或 `FEASIBLE`，且 `hard_conflict_count` 为 `0`。

## 启动可视化驾驶舱

最简单的方式是直接双击项目根目录中的 `launch_classmind.bat`，它会检查环境、启动后端并自动打开浏览器。

停止应用时双击 `stop_classmind.bat`。

启动器会打开一个最小化的 `ClassMind Server` 服务窗口。使用应用期间请保持该窗口运行；关闭服务窗口即停止应用。若一键启动失败，可双击 `run_server.bat` 查看完整错误。

也可以在 PowerShell 中执行：

```powershell
.\serve.ps1
```

浏览器访问 `http://127.0.0.1:8766`。API 包括：

- `GET /api/health`：服务状态
- `GET /api/plans`：三套候选方案与评分卡
- `GET /api/dashboard`：平衡策略课表与教师负载
- `POST /api/solve`：提交与 `data/demo.json` 同结构的业务数据；可额外带 `strategy`
- `GET /api/demo`：前端资源选择器使用的演示业务数据
- `POST /api/reschedule`：教师请假后的最小影响局部重排与版本差异

前端采用统一侧栏母版与四个独立子页面：

- `/`：决策驾驶舱
- `/schedule.html`：08:00—17:30 全日周课表（12:00—13:30 午休）
- `/reschedule.html`：教师请假最小影响调课
- `/resources.html`：教师、教室、班级、课程资源明细

## 安装到其他电脑

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD"
.\.venv\Scripts\python -m classmind.cli
```

## 测试

当前工作区已安装 OR-Tools；可执行：

```powershell
$env:PYTHONPATH = "$PWD"
& "C:\Users\22314\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests -v
```

## 数据格式

演示数据见 `data/demo.json`。课程的 `qualified_teacher_ids` 是业务允许的教师名单；教师自身的 `qualifications` 是学科资质，两者必须同时满足。`required_equipment` 必须是教室 `equipment` 的子集。

## 下一阶段建议

加入软约束权重、三套策略方案、局部重排和版本差异；在算法稳定后再接入飞书多维表格、消息卡片、审批与大模型自然语言解析。
