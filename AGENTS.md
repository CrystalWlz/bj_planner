# Codex Project Guide

本项目是一个本机运行的北京家庭购房、买车、理财和现金流规划工具。前端是 React + Vite，后端是 FastAPI + SQLite。家庭数据默认只存在本机数据库中，仓库代码、测试和文档应保持为可公开的示例与规则逻辑。

## 目录结构

- `backend/app/schemas.py`：Pydantic 数据模型和 API 请求/返回结构。
- `backend/app/calculator.py`：核心测算逻辑，包括收入税费、公积金、购房策略、买车策略、理财现金流和压力测试。
- `backend/app/database.py`：SQLite 存取和初始化。默认数据库在 `%APPDATA%\house-planner\planner.db`，可用 `HOUSE_PLANNER_DB` 覆盖。
- `backend/app/main.py`：FastAPI 路由。
- `backend/tests/`：后端 API 和计算器测试。
- `frontend/src/App.tsx`：主要前端页面和交互逻辑。
- `frontend/src/types.ts`：前端类型，应与 `backend/app/schemas.py` 对齐。
- `frontend/src/api.ts`：前端 API 调用。
- `frontend/src/styles.css`：全局样式。
- `scripts/privacy_scan.py`：推送前隐私扫描。
- `scripts/push_public.ps1`：发布检查和推送脚本。

## 隐私与发布原则

- 不要把本机 SQLite 数据库、导出文件、截图、日志、`.env`、虚拟环境、依赖目录或构建产物提交到 Git。
- 不要在代码、测试、README、AGENTS 或提交信息里写入真实家庭成员称呼、收入、资产、债务、出生年月、学校/单位身份等私人信息。
- 测试样例只能使用泛化名称，例如 `样例成员A`、`阶段性贷款A`、`示例房源`。
- 公开代码使用通用业务概念：`phased_loans` 表示阶段性贷款，不使用能暗示具体贷款来源的内部命名。
- 北京政策、公开规则和公开来源链接可以保留；个人配置只能存在本机数据库。
- 不要频繁推送。除非用户明确要求，完成工作后只做本地提交。
- 推送只能走 `codex/public-release` 分支到 GitHub `main`，优先使用 `.\scripts\push_public.ps1`。

## 常用命令

后端测试：

```powershell
$Env:PYTHONPATH = "backend"
python -m pytest backend/tests/test_api.py backend/tests/test_calculator.py -q -n auto
```

前端构建：

```powershell
Push-Location frontend
npm run build
Pop-Location
```

隐私扫描：

```powershell
python scripts/privacy_scan.py --ref HEAD
python scripts/privacy_scan.py
```

发布脚本：

```powershell
.\scripts\push_public.ps1
```

本地预览可用临时数据库，避免动到真实数据：

```powershell
$Env:HOUSE_PLANNER_DB = "$Env:TEMP\bj_planner_public_preview.sqlite"
$Env:PYTHONPATH = "backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

```powershell
Push-Location frontend
$Env:VITE_API_BASE = "http://127.0.0.1:8010"
npm run dev -- --host 127.0.0.1 --port 5175
Pop-Location
```

## 开发注意事项

- 修改后端 schema 时，同步更新 `frontend/src/types.ts`、前端读取逻辑和测试。
- 新增或改名持久化字段时，不要在公开代码中长期保留带隐私暗示的旧字段兼容逻辑。若本机旧数据需要迁移，优先做一次性本机数据转换，并确保转换脚本不进入公开仓库。
- 前端输入框要避免在中文输入法组合输入时打断输入；不要在普通文本输入的每次按键中做破坏性格式化。
- 数字字段要设置合理的 `min`、`max`、`step`，并在后端 schema 中同步校验。
- 自动生成策略和手动策略都要能反映到可视化。用户在上方目标里修改参数后，下方策略和图表应能重新计算。
- 可视化展示的是当前选中的方案，不是单纯当前状态。
- 现金不能被解释为可为负余额。压力情景中低于 0 应展示为现金缺口，并把方案标为不可行或需要调整。
- 买车第二辆车是可选子计划：默认不展示配置字段，用户点击添加后才纳入现金流和时间线。
- 年终奖现金流按发放月一次性入账，不均摊到每个月。
- 工资阶段用于模拟换工作、工资、公积金比例、年终奖和社保扣缴方式变化。
- 公积金账户变化要考虑缴存、利息、租房季度提取、交易前/交易后提取和买后提取或冲还贷。
- 理财计划要考虑现金安全垫、定投买入、卖出手续费、收益复利和买房时投资变现。

## 代码风格

- 优先沿用现有单文件 React 页面结构，做小步重构，避免无关的大规模抽象。
- 前端显示文字用中文；内部字段名用稳定英文业务概念。
- 对重复业务规则优先放在 calculator 的纯函数里，并配后端测试。
- UI 改动后尽量用浏览器预览验证关键页面：家庭收入、购房计划、买车计划、理财计划和可视化。
- 保持页面第一屏是实际工具，不做营销式落地页。
- 不要把政策规则和私人配置混在一起；规则包是公开参数，家庭数据是本机私有数据。

## 完成工作前检查

至少按改动范围选择执行：

- 后端逻辑或 schema 改动：跑后端 pytest。
- 前端类型、页面或可视化改动：跑 `npm run build`。
- 任何可能进入 Git 的改动：跑 `python scripts/privacy_scan.py`。
- 准备发布：跑 `.\scripts\push_public.ps1`，不要手工绕过隐私扫描和 pre-push 保护。
