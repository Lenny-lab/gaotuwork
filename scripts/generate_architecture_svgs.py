from __future__ import annotations

from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "thesis" / "figures_svg"

ORANGE = "#FF5A1F"
ORANGE_SOFT = "#FFF1EA"
NAVY = "#202733"
BLUE = "#356AE6"
BLUE_SOFT = "#EDF3FF"
GREEN = "#20A875"
GREEN_SOFT = "#EAF8F3"
GRAY = "#667085"
LIGHT = "#F6F8FB"
LINE = "#D9E0EA"
WHITE = "#FFFFFF"


class SVG:
    def __init__(self, title: str, subtitle: str, width: int = 1440, height: int = 900):
        self.width, self.height = width, height
        self.parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
  <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L10,5 L0,10 z" fill="{NAVY}"/></marker>
  <marker id="arrowOrange" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L10,5 L0,10 z" fill="{ORANGE}"/></marker>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#1D2939" flood-opacity="0.10"/></filter>
  <style>text{{font-family:'Microsoft YaHei','Noto Sans CJK SC','PingFang SC',Arial,sans-serif}} .title{{font-weight:700;fill:{NAVY}}} .muted{{fill:{GRAY}}} .label{{font-weight:600;fill:{NAVY}}} .small{{font-size:18px;fill:{GRAY}}}</style>
</defs>
<rect width="100%" height="100%" fill="{WHITE}"/>
<rect x="0" y="0" width="12" height="900" fill="{ORANGE}"/>
<text x="70" y="74" font-size="34" class="title">{escape(title)}</text>
<text x="70" y="108" font-size="18" class="muted">{escape(subtitle)}</text>
<line x1="70" y1="134" x2="1370" y2="134" stroke="{LINE}" stroke-width="2"/>
''']

    def text(self, x, y, value, size=22, color=NAVY, weight=400, anchor="start", cls=""):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" class="{cls}">{escape(str(value))}</text>')

    def multiline(self, x, y, lines, size=18, color=GRAY, weight=400, anchor="middle", gap=27):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">')
        for index, line in enumerate(lines):
            self.parts.append(f'<tspan x="{x}" dy="{0 if index == 0 else gap}">{escape(line)}</tspan>')
        self.parts.append('</text>')

    def box(self, x, y, w, h, title, lines=(), fill=WHITE, stroke=LINE, number=None, radius=16, title_size=22, shadow=False):
        extra = ' filter="url(#shadow)"' if shadow else ''
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"{extra}/>')
        if number is not None:
            self.parts.append(f'<circle cx="{x+28}" cy="{y+28}" r="17" fill="{ORANGE}"/><text x="{x+28}" y="{y+34}" font-size="15" fill="white" font-weight="700" text-anchor="middle">{number}</text>')
        title_x = x + (54 if number is not None else w/2)
        anchor = "start" if number is not None else "middle"
        self.text(title_x, y+37, title, title_size, NAVY, 700, anchor)
        if lines:
            self.multiline(x+w/2, y+70, list(lines), 17, GRAY, 400, "middle", 25)

    def pill(self, x, y, w, text, fill=ORANGE_SOFT, color=ORANGE):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="36" rx="18" fill="{fill}"/><text x="{x+w/2}" y="{y+24}" font-size="15" fill="{color}" font-weight="600" text-anchor="middle">{escape(text)}</text>')

    def arrow(self, x1, y1, x2, y2, label=None, color=NAVY, dashed=False, orange=False):
        dash = ' stroke-dasharray="8 6"' if dashed else ''
        marker = "arrowOrange" if orange else "arrow"
        self.parts.append(f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="{color}" stroke-width="2.5" marker-end="url(#{marker})"{dash}/>')
        if label:
            mx, my = (x1+x2)/2, (y1+y2)/2-10
            self.parts.append(f'<rect x="{mx-55}" y="{my-16}" width="110" height="25" rx="12" fill="white"/><text x="{mx}" y="{my+2}" font-size="14" fill="{GRAY}" text-anchor="middle">{escape(label)}</text>')

    def line(self, x1, y1, x2, y2, color=LINE, width=2, dashed=False):
        dash = ' stroke-dasharray="8 6"' if dashed else ''
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{dash}/>')

    def save(self, name: str):
        self.parts.append(f'<text x="1370" y="865" text-anchor="end" font-size="14" fill="#98A2B3">ClassMind · 高途智能排课脑</text></svg>')
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / name
        path.write_text("\n".join(self.parts), encoding="utf-8")
        return path


def architecture():
    s = SVG("ClassMind 总体系统架构", "四层解耦架构：协作入口、应用交互、业务服务与约束求解")
    layers = [(170,"协作与交互层",ORANGE_SOFT,ORANGE),(330,"API 与业务层",BLUE_SOFT,BLUE),(490,"算法与校验层",GREEN_SOFT,GREEN),(650,"数据与基础设施层",LIGHT,GRAY)]
    for y, label, fill, color in layers:
        s.parts.append(f'<rect x="70" y="{y}" width="1300" height="122" rx="20" fill="{fill}" stroke="{color}" stroke-opacity="0.35"/>')
        s.text(100,y+34,label,18,color,700)
    for i,(title,sub) in enumerate([("决策驾驶舱","指标与方案"),("智能排课","全日课表"),("调课中心","最小影响"),("资源概览","基础数据")]):
        s.box(290+i*255,190,210,76,title,[sub],WHITE,ORANGE,10+i*10,12,18)
    s.box(300,350,330,76,"HTTP API 网关",["路由 · 校验 · 静态服务"],WHITE,BLUE,50,12,20)
    s.box(805,350,330,76,"业务编排服务",["评分 · 方案组合 · 差异分析"],WHITE,BLUE,60,12,20)
    for i,(title,sub) in enumerate([("CP-SAT 求解器","硬约束 + 软目标"),("独立校验器","结果二次复核"),("数据 I/O","JSON ↔ Problem")]):
        s.box(235+i*355,510,300,76,title,[sub],WHITE,GREEN,70+i*10,12,19)
    for i,title in enumerate(["业务数据类","演示数据 JSON","OR-Tools 9.15"]):
        s.box(235+i*355,690,300,66,title,[],WHITE,LINE,100+i*10,12,18)
    for x in [395,650,905,1160]: s.arrow(x,266,x,348,"REST")
    s.arrow(630,388,803,388,"调用")
    s.arrow(970,426,385,508,"求解请求")
    s.arrow(970,426,740,508,"复核")
    s.arrow(465,586,385,688,"模型")
    s.arrow(740,586,740,688,"读取")
    s.arrow(1010,586,1095,688,"依赖")
    return s.save("01_ClassMind_总体系统架构.svg")


def business_flow():
    s = SVG("智能排课业务闭环", "从数据准备到发布、调课与持续复盘的端到端流程")
    steps=[("数据准备",["教师 · 教室","班级 · 课程"]),("数据校验",["字段完整性","引用一致性"]),("生成方案",["CP-SAT 求解","零硬冲突"]),("教务决策",["评分与解释","选择方案"]),("课表发布",["全日周课表","通知相关人"]),("动态调课",["局部重排","差异清单"])]
    xs=[70,300,530,760,990,1220]
    for i,(title,lines) in enumerate(steps):
        s.box(xs[i],255,170,150,title,lines,WHITE,ORANGE if i in (2,5) else LINE,i+1,18,20,True)
        if i<5:s.arrow(xs[i]+170,330,xs[i+1]-8,330)
    s.parts.append(f'<path d="M1305,410 C1305,650 155,650 155,420" fill="none" stroke="{BLUE}" stroke-width="3" stroke-dasharray="10 7" marker-end="url(#arrow)"/>')
    s.text(720,625,"版本记录与反馈回流",18,BLUE,700,"middle")
    s.box(330,500,330,86,"异常分支",["不可行诊断 → 放宽约束 → 重新求解"],BLUE_SOFT,BLUE,70,14,18)
    s.box(780,500,330,86,"审计分支",["保留数据快照 · 方案版本 · 操作日志"],GREEN_SOFT,GREEN,80,14,18)
    s.arrow(615,405,495,498,"无解",BLUE,True)
    s.arrow(1075,405,945,498,"发布",GREEN,True)
    s.pill(590,720,260,"可计算 · 可解释 · 可协同")
    return s.save("02_智能排课业务闭环.svg")


def data_flow():
    s = SVG("核心数据流与对象转换", "JSON业务数据经不可变模型、求解器与校验器转换为可视化课表")
    nodes=[("多维表格/JSON",["原始业务记录"],ORANGE_SOFT,ORANGE),("load_problem",["结构解析"],BLUE_SOFT,BLUE),("Problem",["不可变数据类"],WHITE,NAVY),("solve_schedule",["CP-SAT 优化"],GREEN_SOFT,GREEN),("SolveResult",["课表 + 指标"],WHITE,NAVY),("API Response",["UTF-8 JSON"],BLUE_SOFT,BLUE),("四个子页面",["决策与操作"],ORANGE_SOFT,ORANGE)]
    x=55
    for i,(title,lines,fill,stroke) in enumerate(nodes):
        s.box(x,300,165,120,title,lines,fill,stroke,10+i*10,14,18)
        if i<len(nodes)-1:s.arrow(x+165,360,x+190,360)
        x+=190
    s.box(470,520,240,90,"数据校验器",["输入引用 · 字段范围"],WHITE,GREEN,90,14,19)
    s.box(760,520,240,90,"课表校验器",["冲突 · 容量 · 资质"],WHITE,GREEN,100,14,19)
    s.arrow(517,420,590,518,"校验",GREEN,True)
    s.arrow(887,420,880,518,"复核",GREEN,True)
    s.parts.append(f'<path d="M880,610 C880,720 517,720 517,425" fill="none" stroke="{ORANGE}" stroke-width="2.5" stroke-dasharray="9 7" marker-end="url(#arrowOrange)"/>')
    s.text(700,700,"失败时返回可操作的诊断信息",17,ORANGE,700,"middle")
    for i,label in enumerate(["Teacher","Room","ClassGroup","CourseRequest","TimeSlot"]): s.pill(210+i*205,195,160,label, LIGHT, NAVY)
    return s.save("03_核心数据流与对象转换.svg")


def constraint_model():
    s = SVG("CP-SAT 排课约束模型", "决策变量、硬约束与软目标共同组成可解释的组合优化模型")
    s.box(530,210,380,120,"决策变量  xₗ,ₜ,ᵣ,ₛ",["课次 l 是否由教师 t 在教室 r、时段 s 上课","布尔变量 ∈ {0,1}"],ORANGE_SOFT,ORANGE,10,18,24,True)
    hard=[("每课恰好一次","Σ x = 1"),("教师零冲突","同教师同刻 ≤ 1"),("教室零冲突","同教室同刻 ≤ 1"),("班级零冲突","同班级同刻 ≤ 1"),("业务可行性","资质 · 容量 · 设备 · 可用")]
    coords=[(80,200),(80,370),(80,540),(1140,285),(1140,500)]
    for i,((title,sub),(x,y)) in enumerate(zip(hard,coords)):
        s.box(x,y,230,105,title,[sub],WHITE,BLUE,20+i*10,14,18)
        if x<500:s.arrow(x+230,y+52,528,270, None, BLUE)
        else:s.arrow(x,y+52,912,270,None,BLUE)
    s.parts.append(f'<rect x="360" y="440" width="720" height="245" rx="22" fill="{GREEN_SOFT}" stroke="{GREEN}" stroke-width="2"/>')
    s.text(720,482,"软目标函数：最小化加权成本 Z",24,GREEN,700,"middle")
    soft=[("学生偏好","时段体验"),("教师偏好","授课稳定"),("容量适配","资源效率"),("时段紧凑","减少空档"),("方案变更","调课影响")]
    for i,(title,sub) in enumerate(soft):
        x=390+i*135
        s.box(x,520,115,105,title,[sub],WHITE,GREEN,70+i*10,12,16)
    s.arrow(720,330,720,438,"可行解",GREEN)
    s.pill(550,730,340,"输出：OPTIMAL / FEASIBLE + 零硬冲突",GREEN_SOFT,GREEN)
    return s.save("04_CP-SAT排课约束模型.svg")


def reschedule_flow():
    s = SVG("最小影响调课算法", "教师请假后锁定未受影响课程，以课程变更数为最高优先级局部重排")
    steps=[("接收请假",["教师 t*","时段 s*"]),("求解基线",["balanced","得到 S₀"]),("注入新约束",["unavailable","加入 s*"]),("局部重排",["reschedule","变更权重 100"]),("差异计算",["before / after","影响班级"]),("确认与通知",["新课表 S'","变更清单 Δ"])]
    xs=[70,300,530,760,990,1220]
    for i,(title,lines) in enumerate(steps):
        fill=ORANGE_SOFT if i in (0,3) else WHITE
        stroke=ORANGE if i in (0,3) else LINE
        s.box(xs[i],245,170,145,title,lines,fill,stroke,i+1,14,20,True)
        if i<5:s.arrow(xs[i]+170,317,xs[i+1]-8,317)
    s.parts.append(f'<rect x="310" y="500" width="820" height="150" rx="22" fill="{LIGHT}" stroke="{LINE}"/>')
    s.text(720,540,"核心优化优先级",20,NAVY,700,"middle")
    priorities=[("P1","硬冲突 = 0",ORANGE),("P2","变更课次最少",BLUE),("P3","偏好与容量最优",GREEN)]
    for i,(tag,text,color) in enumerate(priorities):
        x=390+i*230
        s.parts.append(f'<circle cx="{x}" cy="590" r="28" fill="{color}"/><text x="{x}" y="597" font-size="17" fill="white" font-weight="700" text-anchor="middle">{tag}</text>')
        s.text(x+42,597,text,17,NAVY,600)
    s.box(475,700,490,74,"典型结果",["仅移动受影响课次，其他课程位置保持不变"],GREEN_SOFT,GREEN,90,14,19)
    return s.save("05_最小影响调课算法.svg")


def deployment_api():
    s = SVG("前后端与 API 部署关系", "零构建前端通过本地HTTP服务调用业务接口与CP-SAT核心")
    s.parts.append(f'<rect x="70" y="175" width="360" height="580" rx="24" fill="{ORANGE_SOFT}" stroke="{ORANGE}" stroke-width="2"/>')
    s.text(250,215,"浏览器前端",24,ORANGE,700,"middle")
    pages=[("/","决策驾驶舱"),("/schedule.html","智能排课"),("/reschedule.html","调课中心"),("/resources.html","资源概览")]
    for i,(url,title) in enumerate(pages):
        s.box(105,255+i*105,290,78,title,[url],WHITE,ORANGE,10+i*10,12,18)
    s.parts.append(f'<rect x="540" y="175" width="360" height="580" rx="24" fill="{BLUE_SOFT}" stroke="{BLUE}" stroke-width="2"/>')
    s.text(720,215,"Python HTTP 服务",24,BLUE,700,"middle")
    apis=[("GET /api/health","健康检查"),("GET /api/demo","业务数据"),("GET /api/plans","三套方案"),("POST /api/solve","通用求解"),("POST /api/reschedule","局部调课"),("GET /api/dashboard","指标负载")]
    for i,(url,title) in enumerate(apis):
        y=252+i*75
        s.parts.append(f'<rect x="580" y="{y}" width="280" height="54" rx="10" fill="white" stroke="{LINE}"/><text x="600" y="{y+23}" font-size="14" fill="{BLUE}" font-weight="700">{escape(url)}</text><text x="600" y="{y+43}" font-size="13" fill="{GRAY}">{escape(title)}</text>')
    s.parts.append(f'<rect x="1010" y="175" width="360" height="580" rx="24" fill="{GREEN_SOFT}" stroke="{GREEN}" stroke-width="2"/>')
    s.text(1190,215,"核心服务与数据",24,GREEN,700,"middle")
    modules=[("service.py","业务编排"),("solver.py","CP-SAT 求解"),("validator.py","独立校验"),("models.py","不可变模型"),("data/demo.json","演示数据")]
    for i,(module,title) in enumerate(modules):
        s.box(1050,260+i*90,280,64,module,[title],WHITE,GREEN,70+i*10,12,17)
    for y in [292,397,502,607]:s.arrow(432,y,538,y,"fetch",ORANGE)
    for y in [280,355,430,505,580]:s.arrow(902,y,1008,y,"调用",GREEN)
    s.pill(570,790,300,"127.0.0.1:8766 · 本地可运行",BLUE_SOFT,BLUE)
    return s.save("06_前后端与API部署关系.svg")


def main():
    outputs=[architecture(),business_flow(),data_flow(),constraint_model(),reschedule_flow(),deployment_api()]
    readme = "# ClassMind 架构矢量图\n\n全部为纯 SVG，可无损缩放并直接插入 LaTeX。\n\n" + "\n".join(f"- `{path.name}`" for path in outputs) + "\n"
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print("\n".join(str(path) for path in outputs))


if __name__ == "__main__":
    main()
