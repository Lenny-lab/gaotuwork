# 下一步工作计划 · 角色化登录与分区分权

> 状态:**未开始**,等用户决定启动时间
>
> 目标:把当前"所有用户看同一个页面"改成"学生/教师/教务三种身份登录后看各自对应的页面和功能"
>
> 配套要求:深度融合飞书,登录用飞书身份,不另建用户系统

---

## 一、为什么要做这个改动(背景)

当前系统所有用户(无论是学生、教师还是教务)打开 `classmind-feishu.onrender.com` 看到的都是**完全一样的页面**——决策驾驶舱 + 智能排课 + 调课中心 + 资源概览 + 飞书多维表格,5 个 tab 全部可见,所有 API 全部可调。

这在**演示场景**够用,但在**真实业务场景**有几个问题:

1. **信息过载**:学生看"决策驾驶舱"和"调课中心"完全无感,看不明白
2. **权限泄露**:学生能调 `/api/solve` 跑排课 / 改数据,但学生本不该有这能力
3. **体验割裂**:教师应该看到"我的课表 / 我的学生",教务才应该看"全部课表 / 三套方案 / 资源总览"
4. **飞书集成不深**:没用飞书的"通讯录"和"身份信息",等于浪费了飞书最大优势

---

## 二、目标效果

### 登录前

用户点击飞书工作台里的 **Gaotutable** 应用 → 第一次进入**登录/角色选择页**(类似 SSO)→ 选择身份进入对应主页。

### 登录后(三种身份看到不同内容)

| 身份 | 主页面 | 侧栏 tab | 可用 API |
|---|---|---|---|
| **学生** | "我的课表" | 我的课表 / 我的考试 / 选课申请 / 个人中心 | `GET /api/student/{id}/schedule` |
| **教师** | "我的课表" | 我的课表 / 我的学生 / 调课申请 / 个人中心 | `GET /api/teacher/{id}/schedule` / `POST /api/teacher/leave` |
| **教务** | "决策驾驶舱"(现状) | 决策驾驶舱 / 智能排课 / 调课中心 / 资源概览 / 飞书多维表格 / 用户管理 | **全部**现有 API |

---

## 三、整体架构(给"下一个 AI / 我自己"看的实施蓝图)

### 3.1 新增模块

```
gaotuwork/
├── auth/                                    [新] 鉴权模块
│   ├── __init__.py
│   ├── feishu_oauth.py                      [新] 飞书 OAuth 登录(扫码)
│   ├── session.py                           [新] 服务端 session 管理
│   ├── role.py                              [新] 角色识别(从飞书通讯录查身份)
│   └── decorator.py                         [新] @require_role("teacher") 装饰器
├── classmind/
│   ├── users.py                             [新] 学生/教师/教务用户模型 + demo 数据
│   ├── student_api.py                       [新] 学生端 API
│   └── teacher_api.py                       [新] 教师端 API
├── data/
│   └── users.json                           [新] 演示用学生/教师/教务数据
├── web/
│   ├── login.html                           [新] 登录页(角色选择 / 飞书扫码)
│   ├── student/
│   │   ├── dashboard.html                   [新] 学生主页
│   │   ├── my-schedule.html                 [新] 我的课表
│   │   └── exams.html                       [新] 我的考试
│   ├── teacher/
│   │   ├── dashboard.html                   [新] 教师主页
│   │   ├── my-schedule.html                 [新] 我的课表
│   │   └── leave.html                       [新] 请假申请
│   └── (现有 index.html / schedule.html / reschedule.html / resources.html 保留为"教务端")
└── app.py                                   [改] 加 session middleware + 角色路由
```

### 3.2 飞书鉴权流程

```
[飞书工作台]
   ↓ 用户点开 Gaotutable
[Gaotutable web 页面] (https://classmind-feishu.onrender.com)
   ↓ 检测未登录 → 跳到 /login
[/login 页面]
   ↓ 展示两种登录方式
   ├── A. 飞书 OAuth 授权(推荐) → 跳到飞书授权页
   └── B. 演示账号登录(选"学生/教师/教务"三选一,适合评委/演示)
   ↓ 授权成功 / 选择角色成功
[/auth/callback] (后端)
   ├── 拿飞书 code 换 access_token
   ├── 调飞书 openAPI 拿用户信息(用户ID、姓名、头像、部门)
   ├── 根据"部门"或"角色字段"判断身份
   │   ├── 部门含"学生"→ role = student
   │   ├── 部门含"教师"或"老师"→ role = teacher
   │   └── 默认 + 是租户 owner/admin → role = academic_affairs(教务)
   ├── 写服务端 session(存 redis 或简单 dict)
   ├── 写前端 cookie / localStorage
   └── 重定向到对应主页(/student/dashboard 或 /teacher/dashboard 或 /)
```

### 3.3 飞书侧需要新增的能力和配置

| 飞书侧配置 | 为什么 | 怎么做 |
|---|---|---|
| **网页应用 - 免登录模式 vs 登录模式** | 飞书工作台打开是带用户身份的(免登录模式) | 飞书"网页应用"已经默认带 `login_identity` 参数,直接用 |
| **通讯录权限 `contact:user.id:readonly`** | 查用户身份用 | 飞书后台"权限管理"开 |
| **获取用户信息权限 `contact:user.profile:readonly`** | 拿用户姓名/头像 | 同上 |
| **可选:OAuth 2.0 授权(扫码登录)** | 给"非飞书工作台打开"的情况用 | 飞书后台"安全设置"配回调 URL |
| **可选:身份字段 / 自定义角色** | 区分学生/教师/教务 | 飞书通讯录里给用户加"部门"或"职位"字段 |

### 3.4 角色识别策略(简版先用,后续可换)

**简版**(先做):
- 飞书工作台打开 → 飞书侧 `login_identity` 自带用户 open_id
- 后端用 open_id 查本地 `users.json`,找到对应角色
- 找不到 → 默认当成"教务"看(因为评委 / 管理员没分角色)

**进版**(后续):
- 用飞书**通讯录 API** 查用户的"部门"或"自定义字段"
- 部门名包含"学生"→ student,包含"教师/老师"→ teacher
- 没匹配上 → 走"申请角色"流程(填表,教务审批)

---

## 四、详细实施步骤(给 AI/我自己的指令清单)

### 阶段 1:数据层(1-2 小时)

1. 扩展 `data/demo.json` 或新建 `data/users.json`,加三类用户:
   ```json
   {
     "users": [
       {"id": "U_S001", "feishu_open_id": "ou_xxxx", "name": "张三", "role": "student", "class_id": "C01", "email": "..."},
       {"id": "U_S002", "feishu_open_id": "ou_yyyy", "name": "李四", "role": "student", "class_id": "C02"},
       {"id": "U_T001", "feishu_open_id": "ou_zzzz", "name": "张老师", "role": "teacher", "teacher_id": "T01", "subjects": ["数学"]},
       {"id": "U_T002", "feishu_open_id": "ou_wwww", "name": "李老师", "role": "teacher", "teacher_id": "T02", "subjects": ["数学","物理"]},
       {"id": "U_A001", "feishu_open_id": "ou_vvvv", "name": "王教务", "role": "academic_affairs", "permissions": ["*"]}
     ]
   }
   ```
2. 写 `classmind/users.py`:
   - `class User: id, feishu_open_id, name, role, ...`
   - `def load_users() -> list[User]`
   - `def find_by_feishu_id(open_id) -> User | None`
   - `def find_by_role(role) -> list[User]`
3. 写单测 `tests/test_users.py`

### 阶段 2:鉴权层(2-3 小时)

1. 写 `auth/feishu_oauth.py`:
   - `def build_authorize_url(redirect_uri) -> str`(拼飞书 OAuth 授权页 URL)
   - `def exchange_code_for_token(code) -> dict`(code 换 access_token + 用户信息)
   - `def get_user_info(access_token) -> dict`(拿姓名/部门/open_id)
2. 写 `auth/session.py`:
   - 简版:用 Flask session(secret key 从环境变量读)
   - 存 `{open_id, role, name, avatar}` 进 session
   - `def current_user() -> User | None`
   - `def login_required(view_func)` 装饰器
   - `def require_role(role: str)` 装饰器
3. 写 `auth/role.py`:
   - 简版:从 `users.json` 查 role
   - 进版:用飞书通讯录 API 查部门
4. 写 `app.py` 的 session middleware:
   ```python
   @app.before_request
   def load_user():
       g.user = current_user()
   ```

### 阶段 3:登录页 + 路由(2-3 小时)

1. 写 `web/login.html`:
   - 顶部飞书 logo
   - 两个大按钮:
     - **"用飞书账号登录"** → 跳到 `/auth/feishu` → 飞书授权页 → 回调
     - **"演示账号登录"** → 显示三个角色卡片(学生/教师/教务)→ 点哪个用哪个(便于评委快速体验)
2. 改 `app.py` 加路由:
   - `GET /login` → 返回 login.html
   - `GET /auth/feishu` → 重定向到飞书授权页
   - `GET /auth/callback?code=xxx` → 拿 token → 写 session → 重定向到对应主页
   - `GET /auth/demo?role=student|teacher|academic_affairs` → 直接写 session(不调飞书,演示用)
   - `GET /auth/logout` → 清 session → 重定向到 /login
3. 改 `app.py` 让所有页面路由先过 `login_required`(除了 `/login`、`/auth/*`、`/healthz`)

### 阶段 4:学生端页面 + API(3-4 小时)

1. 新建 `classmind/student_api.py`:
   - `GET /api/student/<student_id>/schedule` → 返回这个学生所在班级的课表
   - `GET /api/student/<student_id>/exams` → 返回考试安排(用排课结果 + 课程类型推断)
2. 新建 `web/student/`:
   - `dashboard.html` - 学生主页(今日课程 / 通知 / 个人中心入口)
   - `my-schedule.html` - 我的课表(本周视图,只看自己班的)
   - `exams.html` - 我的考试
3. 侧栏只显示学生相关 tab
4. 写一个**学生视角的飞书消息卡片**:`@机器人 我的课表` → 推一张本周课表卡片到私聊(已有 `feishu_card.py` 基础上加)

### 阶段 5:教师端页面 + API(3-4 小时)

1. 新建 `classmind/teacher_api.py`:
   - `GET /api/teacher/<teacher_id>/schedule` → 返回这个教师的课表
   - `GET /api/teacher/<teacher_id>/students` → 返回这个教师教的所有学生
   - `POST /api/teacher/leave` → 教师请假申请(body: {teacher_id, slot_id, reason}),触发调课
   - `GET /api/teacher/<teacher_id>/workload` → 教学工作量统计
2. 新建 `web/teacher/`:
   - `dashboard.html` - 教师主页(今日课程 / 待办)
   - `my-schedule.html` - 我的课表
   - `leave.html` - 请假申请表单
3. 飞书机器人扩展:教师私聊机器人 `@机器人 我的课表` / `@机器人 请假` → 触发对应动作

### 阶段 6:教务端(基本不动,但加用户管理)(1-2 小时)

1. 保留现有 4 个页面作为教务端
2. 新增 `web/admin/users.html` - 用户管理(看哪些飞书用户被识别为什么角色)
3. 改 `/auth/demo?role=academic_affairs` 让教务能直接进入

### 阶段 7:飞书侧配置(1 小时,需要用户手动操作)

1. 飞书后台 → **权限管理** → 加:
   - `contact:user.id:readonly`
   - `contact:user.profile:readonly`
2. 飞书后台 → **安全设置** → **重定向 URL** 加:
   - `https://classmind-feishu.onrender.com/auth/callback`
3. 飞书后台 → **权限管理** → 给"网页应用"加 `user_profile` 字段(拿用户姓名头像用)
4. 飞书通讯录里给用户加"部门"字段,部门名包含"学生"/"教师"做角色识别

### 阶段 8:测试 + 端到端验证(1-2 小时)

1. 测试矩阵:
   - 演示账号学生 → 看到学生页面
   - 演示账号教师 → 看到教师页面
   - 演示账号教务 → 看到完整决策驾驶舱
   - 飞书扫码登录 → 根据飞书用户身份自动路由
2. 三种身份在飞书群里 @ 机器人:
   - 学生 → "我的课表" → 推学生版卡片
   - 教师 → "我的课表" → 推教师版卡片
   - 教师 → "请假" → 触发调课
3. 权限拦截测试:学生账号尝试调 `/api/solve` → 403

---

## 五、关键技术点提示

### 5.1 飞书 OAuth(给"非工作台打开"的情况)

**飞书工作台打开**是带 `login_identity` 参数的,后端可以拿,不用走 OAuth。
**浏览器直接打开**才需要 OAuth 扫码。

**简版实现**(只支持工作台打开):
- 后端读 `$_GET['login_identity']` 或请求头里的飞书身份
- 直接信,不二次验证

**进版**(浏览器也能扫码):
- 飞书 OAuth `https://passport.feishu.cn/suite/passport/oauth/authorize`
- 回调 URL: `https://classmind-feishu.onrender.com/auth/callback`
- 拿 code 换 `access_token`
- 调 `https://open.feishu.cn/open-apis/authen/v1/user_info` 拿用户信息

### 5.2 角色识别(从飞书通讯录查)

飞书通讯录 API:
- `GET /open-apis/contact/v3/users/:user_id` 拿单个用户详情
- 响应里有 `department` 字段(部门 ID 列表),可以查部门名

简版:让用户在 `data/users.json` 里维护映射(评委演示够用)
进版:用部门 ID 反查部门名,匹配"学生/教师"

### 5.3 角色权限拦截(Flask 装饰器)

```python
# auth/decorator.py
from functools import wraps
from flask import session, jsonify, redirect, url_for, g

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "open_id" not in session:
            if request.is_json:
                return jsonify({"error": "未登录"}), 401
            return redirect(url_for("login_page", next=request.path))
        return f(*args, **kwargs)
    return wrapper

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_role = session.get("role")
            if user_role not in roles and user_role != "academic_affairs":
                return jsonify({"error": "权限不足", "need_role": list(roles)}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# 用法
@app.route("/api/solve", methods=["POST"])
@require_role("academic_affairs")
def api_solve():
    ...
```

### 5.4 飞书机器人按角色路由

`feishu_event.py` 里扩展:
- 拿到消息时,查 `sender_id.open_id` → 找角色
- 学生 → 调 `student_card.schedule_card_for_student`
- 教师 → 调 `teacher_card.schedule_card_for_teacher`
- 教务 → 走现在的逻辑

### 5.5 飞书消息卡片 - 学生版 / 教师版

`feishu_card.py` 加:
- `student_schedule_card(name, schedule)` - 只显示"你班的本周课程"
- `teacher_schedule_card(name, schedule)` - 显示"你教的课 + 学生名单"
- 标题配色不同(学生蓝、教师绿、教务橙)

---

## 六、工作量评估

| 阶段 | 工作量 | 是否阻塞 |
|---|---|---|
| 1. 数据层 | 1-2 小时 | 否 |
| 2. 鉴权层 | 2-3 小时 | 是(后续所有阶段依赖) |
| 3. 登录页 + 路由 | 2-3 小时 | 是 |
| 4. 学生端 | 3-4 小时 | 否(可后做) |
| 5. 教师端 | 3-4 小时 | 否(可后做) |
| 6. 教务端微调 | 1-2 小时 | 否 |
| 7. 飞书侧配置 | 1 小时 | 阻塞(需要用户手动) |
| 8. 测试验证 | 1-2 小时 | — |
| **合计** | **14-21 小时** | 分 2-3 天做 |

**优先级建议**:
- **P0(必做)**:阶段 2 + 3 + 7 = 5-7 小时(先把鉴权打通,角色路由)
- **P1(必做)**:阶段 4 + 5(至少各做一个页面,演示三种身份的差异)
- **P2(选做)**:阶段 6(用户管理)

---

## 七、验证清单(做完后怎么知道成功了)

| 验证项 | 通过标准 |
|---|---|
| 未登录访问 `/` | 跳到 `/login` |
| 用演示账号点"学生" | 看到学生主页,只能访问学生 API |
| 用演示账号点"教师" | 看到教师主页,能请假 |
| 用演示账号点"教务" | 看到完整决策驾驶舱,能跑排课 |
| 学生账号访问 `/api/solve` | 返回 403 |
| 飞书工作台打开应用 | 自动识别身份进入对应主页(无需手动登录) |
| 群里 @ 机器人,学生身份 | 推学生版课表卡片 |
| 群里 @ 机器人,教师身份 | 推教师版课表卡片 |
| 教师私聊机器人 + "请假" | 触发调课,回执 |

---

## 八、给 AI 助手的具体 prompt(可直接复制粘贴用)

> 你是一个 Python / Flask / 飞书集成工程师。现在要在现有 `gaotuwork` 项目(已经部署到 Render,集成飞书机器人 + 多维表格)的基础上,加**角色化登录系统**。
>
> **目标**:让飞书工作台打开应用时,根据用户身份(学生/教师/教务)自动展示不同的页面和功能。
>
> **必读文件**(动手前先看):
> 1. `app.py` - 现有统一 Flask 后端
> 2. `classmind/api.py` - 现有排课 API
> 3. `data/demo.json` - 现有演示数据(teachers/classes/courses)
> 4. `feishuapi/python/feishu_event.py` - 飞书机器人事件
> 5. `feishuapi/python/feishu_card.py` - 飞书消息卡片
> 6. `web/index.html` - 现有"教务端"决策驾驶舱
> 7. `docs/worklog/2026-07-12.md` - 今日工作日志
> 8. `docs/worklog/NEXT_STEPS.md` - 本文件(下一步详细计划)
>
> **核心要求**:
> 1. 用**飞书身份**做登录,不另建账号系统(简化:飞书工作台打开时用 `login_identity` 参数直接信;浏览器打开才走 OAuth 扫码)
> 2. **三角色**:student / teacher / academic_affairs
> 3. **不重复造轮子**:现有 classmind 排课核心一字不动,只在前面加"鉴权层"和"角色路由"
> 4. **深度飞书融合**:
>    - 飞书消息卡片按角色区分(学生版/教师版/教务版)
>    - 群里 @ 机器人按角色返回不同内容
>    - 飞书通讯录 API 查用户身份(进版)
> 5. **演示账号**保留(评委/外部访客用,不调飞书直接选角色)
> 6. **代码风格**:沿用现有 dataclass + 纯函数风格,新加的 auth 模块用 Flask 装饰器
> 7. **部署**:保持 Render 自动部署,不要破坏现有 Procfile / render.yaml
>
> **不要做**:
> - 不要重写 classmind 排课引擎
> - 不要换 web 前端框架(继续用纯 HTML + vanilla JS)
> - 不要引入数据库(用 JSON 文件 + Flask session 就够)
> - 不要做"管理员后台"那种重型 UI
>
> **完成后**:
> 1. 更新 `docs/worklog/` 加当天日志
> 2. commit + push,Render 自动部署
> 3. 飞书侧需要的权限清单写到 `FLYBOOK_INTEGRATION.md` 让用户去勾

---

## 九、风险与坑(提前预知)

1. **飞书 `login_identity` 不是真的鉴权**,只是浏览器带的参数,理论上能伪造。如果用户安全要求高,必须走 OAuth 拿 `access_token` 调 `authen/v1/user_info` 验真。本项目是**比赛演示场景**,简版可接受,生产环境必须做。
2. **Render 免费层 session 是内存的**,重启服务会丢所有登录态。需要切到 Redis(免费有 Upstash)。当前阶段**先做内存版**,等用户量大了再切。
3. **飞书通讯录 API 限流** 60 次/分钟,缓存用户身份到 session/redis 里能解决大部分。
4. **多角色切换**:如果一个用户既是教师又是教务(比如教务主任),角色怎么定?建议**一人一角色** + 教务主任自动升级为教务(因为教务有最大权限)。或者在 users.json 里给个"主要角色"字段。
5. **历史数据兼容**:阶段 1 加 `users.json` 不要影响现有 `demo.json`,两个文件分开存。
