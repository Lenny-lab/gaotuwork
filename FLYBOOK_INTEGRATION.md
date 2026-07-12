# 飞书深度集成 · 部署 & 配置操作手册

> 把 ClassMind 排课系统接入飞书:网页应用(在飞书里打开)+ 机器人(群聊 @ 出课表卡片)+ 多维表格(表格里点按钮触发排课)
>
> 预计 30-60 分钟完成全部配置。

---

## 0. 总览:你将得到什么

| 能力 | 用户体验 | 飞书侧能力 |
|---|---|---|
| **网页应用** | 在飞书里点击应用 → 直接打开 ClassMind 决策驾驶舱 | 网页应用 |
| **机器人** | 群聊里 @ClassMind + "排课" → 飞书群里出现一张排课结果卡片 | 机器人(消息事件) |
| **多维表格自动化** | 在多维表格里点按钮 → 自动跑排课 → 写回"状态/课表文本"列 | 多维表格 + 自动化 |

---

## 1. 准备工作(2 分钟)

- 一个飞书企业(自建应用需要企业管理员权限,或者你是租户 owner)
- 一个 GitHub 账号(已有:`Lenny-lab/gaotuwork`)
- 一个 Render 账号(免费注册 https://render.com,用 GitHub 登录)

---

## 2. 部署后端到 Render(15 分钟)

### 2.1 登录 Render

打开 https://dashboard.render.com,用 GitHub 登录。

### 2.2 创建 Web Service

1. 顶部 **New +** → **Blueprint**(关键:选这个,不是 Web Service)
2. 选 `Lenny-lab/gaotuwork` 仓库
3. Render 会自动读 `render.yaml`,识别出名为 `classmind-feishu` 的服务
4. 点 **Apply** 部署

第一次部署会跑 `pip install -r requirements.txt`,**OR-Tools 比较大,大概 5-10 分钟**,耐心等。

### 2.3 配置环境变量

部署完成后:

1. 进入服务页面 → 左侧 **Environment**
2. 点 **Add Environment Variable**,逐个填:

| Key | Value | 说明 |
|---|---|---|
| `APP_ID` | `cli_xxxxxxxxxxxx` | 飞书开发者后台"凭证与基础信息"里复制 |
| `APP_SECRET` | 你的 App Secret | 同上,**保密** |
| `FEISHU_HOST` | `https://open.feishu.cn` | 国内版固定值,海外版用 `https://open.larksuite.com` |
| `FEISHU_ENCRYPT_KEY` | (暂时留空) | 启用事件加密时填 |
| `FEISHU_VERIFICATION_TOKEN` | (暂时留空) | 启用事件加密时填 |
| `BITABLE_APP_TOKEN` | (暂时留空) | 用多维表格时填 |
| `BITABLE_TABLE_ID` | (暂时留空) | 用多维表格时填 |

3. 填完点 **Save Changes**,Render 会自动重新部署。

### 2.4 拿到公网 URL

部署成功后,Render 会给你一个 URL,类似:
```
https://classmind-feishu.onrender.com
```

**记下这个 URL**,后面所有配置都要用。

测试一下:浏览器打开 `https://classmind-feishu.onrender.com/healthz`,应该看到 `ok`。

---

## 3. 飞书开发者后台配置(15 分钟)

打开 https://open.feishu.cn/app,进入你的应用。

### 3.1 网页应用配置(必做)

1. 左侧 **应用能力** → **网页应用** → **启用网页应用**
2. **桌面端主页 URL** 和 **移动端主页 URL** 都填:
   ```
   https://classmind-feishu.onrender.com
   ```
3. 左侧 **安全设置**:
   - **重定向 URL**:`https://classmind-feishu.onrender.com`
   - 如果要求填写"可信域名",填 `classmind-feishu.onrender.com`(不要加 https)
4. 保存

### 3.2 机器人能力(做"群聊卡片"必做)

1. 左侧 **应用能力** → **机器人** → **启用机器人能力**
2. 左侧 **事件订阅**:
   - **请求 URL**:
     ```
     https://classmind-feishu.onrender.com/feishu/event
     ```
   - 飞书会发一个 `url_verification` 请求,我们的后端会自动 echo `challenge`,验证即可通过
3. **添加事件**:
   - 勾选 `im.message.receive_v1`(接收消息)
   - 权限范围选"所有成员"
4. 左侧 **权限管理**:
   - 搜索并开启以下权限:
     - `im:message` - 获取与发送消息
     - `im:message:send_as_bot` - 以应用身份发消息
     - `im:message.group_at_msg` - 接收群聊 @ 消息
     - `im:message.p2p_msg` - 接收单聊消息
     - `im:message:readonly` - 读取消息(可选)
5. **创建版本** → 提交审核(企业内部应用可免审,自建应用通常秒过)

### 3.3 多维表格(做"表格自动化"必做)

1. 左侧 **应用能力** → **多维表格** → 如果有,选"云文档"中开启
2. 左侧 **权限管理** → 搜索"多维表格",开启:
   - `bitable:app:readonly` - 读多维表格
   - `bitable:app:writeonly` - 写多维表格
   - `bitable:app` - 完全访问
3. 把机器人/网页应用加到你创建的多维表格的"协作者"(选"可编辑")

---

## 4. 验证 · 网页应用(5 分钟)

1. 飞书客户端 → 打开"工作台" → 找到你的应用
2. 点击应用,应该能打开 ClassMind 决策驾驶舱
3. 切换"策略"按钮应该能拉到三套方案数据
4. 如果打开是空白页,F12 看 Console,大概率是 CORS 或者 URL 配错

---

## 5. 验证 · 机器人(5 分钟)

1. 建一个测试群,把机器人拉进去
2. 在群里 @机器人 + 文字"排一下课"
3. 应该看到一张"ClassMind 排课结果"卡片飞回来
4. 如果没反应,看 Render 服务的 **Logs** 标签页,看 `feishu_event.handle` 有没有报错

**支持的触发关键词**:`排课` / `课表` / `排一下` / `排个`(任意一个就触发)

---

## 6. 验证 · 多维表格(10 分钟)

### 6.1 准备表格

1. 在飞书多维表格里新建一个表,字段:
   - `课程` (文本)
   - `班级` (文本)
   - `状态` (文本) ← 我们会写
   - `硬冲突数` (数字) ← 我们会写
   - `课表文本` (多行文本) ← 我们会写
   - `更新时间` (数字) ← 我们会写
2. 记下 URL,形如:
   ```
   https://xxx.feishu.cn/base/BITABLE_APP_TOKEN?table=BITABLE_TABLE_ID
   ```
   把 `BITABLE_APP_TOKEN` 和 `BITABLE_TABLE_ID` 填到 Render 的环境变量。

### 6.2 配自动化

1. 多维表格 → 顶部 **自动化** → **创建自动化流程**
2. 触发器选"按钮触发"(或"定时触发")
3. 动作选 **"调用 Webhook"**
4. URL 填:
   ```
   https://classmind-feishu.onrender.com/bitable/webhook
   ```
5. 方法 POST,Body 选"JSON":
   ```json
   {"action": "solve_all"}
   ```
6. 保存并启用

### 6.3 触发

1. 在表格里点你创建的"按钮触发"按钮
2. 等 1-2 秒,回到表格应该看到"状态"列被自动填写,课表文本也写进去了

---

## 7. 常见问题

### Q1:Render 第一次部署失败,提示 ortools 安装超时

去 Render 服务 → **Settings** → 找到 **Build Command**,改成:
```
pip install --timeout 300 -r requirements.txt
```
然后点 **Manual Deploy** 重新部署。

### Q2:网页应用能打开,但是页面调 API 报 CORS 错误

由于我们前端和后端是**同源部署**(都在 `classmind-feishu.onrender.com`),正常不会有 CORS 问题。
如果出现了,99% 是因为:
- 你直接用 `file://` 打开 HTML
- 或者 URL 配错,前后端不在一个域

### Q3:群里 @机器人没反应

1. 看 Render **Logs**,看 `feishu_event` 有没有被打到
2. 看飞书开放平台 → **事件订阅** → **请求日志**,看飞书侧有没有发请求
3. 看 **权限管理** → 机器人权限有没有勾

### Q4:多维表格写不进去

1. Render 环境变量 `BITABLE_APP_TOKEN` / `BITABLE_TABLE_ID` 填了吗?
2. 应用被加到多维表格的"可编辑协作者"了吗?
3. 表格里有"状态"、"课表文本"这些字段吗?(字段名一字不差)

### Q5:Render 免费版冷启动 30-50 秒,飞书消息要等一会儿

免费层 15 分钟无访问会休眠,冷启动慢。
- **方案 A**:升级到 7 美元/月的 Standard,无休眠
- **方案 B**:用 UptimeRobot(https://uptimerobot.com)免费 5 分钟 ping 一次,保活

---

## 8. 升级路径

| 你想要的 | 加什么 |
|---|---|
| 飞书日程同步(排课结果推送给老师飞书日程) | 加 `/feishu/calendar` 端点 + 权限 `calendar:calendar` |
| 飞书审批(请假触发自动重排) | 加 `/feishu/approval` 端点 + 权限 `approval:approval` |
| 飞书文档(排课报告导出) | 加 `/feishu/doc` 端点 + 权限 `docx:document` |
| 多个企业租户支持 | 把 APP_ID/SECRET 改成 multi-tenant 模式,从 token 解出 tenant_key 选配置 |

---

## 9. 文件结构

```
gaotuwork/
├── app.py                          # 统一 Flask 入口(部署入口)
├── requirements.txt                # 依赖
├── Procfile                        # gunicorn 启动命令
├── render.yaml                     # Render 部署配置
├── .env.example                    # 环境变量模板
├── classmind/                      # 排课引擎(原有)
├── feishuapi/python/
│   ├── auth.py                     # 飞书鉴权(原有)
│   ├── server.py                   # 原飞书网页应用入口(保留作参考)
│   ├── feishu_event.py             # [新] 机器人事件回调
│   ├── feishu_card.py              # [新] 消息卡片构造
│   └── bitable.py                  # [新] 多维表格自动化
└── web/                            # 前端(原有)
```

---

## 10. 一句话总结

> Render 部署后端 → 飞书开发者后台配 URL 和权限 → 群里 @机器人验证。

有报错就 Render **Logs** + 飞书 **请求日志** 一起看,基本都能定位。
