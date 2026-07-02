# 北京买房可行性规划计算器

本项目是一个本机使用的北京购房可行性规划工具，包含 React 前端和 FastAPI 后端。家庭财务数据默认保存在本机 SQLite 数据库中，不上传云端。

公开仓库只保留空白家庭模板和公开政策参数，不内置任何真实家庭收入、资产、贷款、老人、出生年月等私人信息。

## 功能

- 家庭收入、支出、资产、负债和购房资格画像
- 多购房方案对比
- 商贷、公积金贷、组合贷月供测算
- 首付、税费、中介费、装修等一次性资金测算
- 购后现金流、负债收入比、应急金覆盖月数
- 利率上行、收入下降、房价上行压力测试
- 版本化规则包和政策来源抓取预览

## 本地启动

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 前端

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

打开 Vite 输出的本地地址即可使用。默认前端会请求 `http://127.0.0.1:8000`。

## 首次初始化

首次启动后，系统会创建一个空白家庭和一个示例房源。建议按以下顺序配置：

1. 在“家庭收入”页填写家庭画像、成员名称、工资阶段、基础支出、现金资产、投资资产和公积金余额。
2. 如有需要，继续添加助学贷款、其他定时支出、老人专项扣除、职业冲击和退休养老金假设。
3. 在“购房计划”页修改目标房源总价、面积、房屋性质、贷款方式和装修资金模式。
4. 在“理财计划”“买车计划”页按自己的目标生成或手动调整策略。
5. 点击“保存本地”，数据会写入本机 SQLite 数据库。

如果你已经在本机使用过旧版本，原有数据库不会自动清空。需要重新初始化时，请先备份后删除本机数据库文件，或设置新的 `HOUSE_PLANNER_DB` 路径。

## 测试

```powershell
cd backend
.\.venv\Scripts\python -m pytest -n auto
```

```powershell
cd frontend
npm run build
```

## 数据位置

默认 SQLite 数据库位于系统应用数据目录：

- Windows: `%APPDATA%\house-planner\planner.db`
- 其他系统: `~/.house-planner/planner.db`

可以通过 `HOUSE_PLANNER_DB` 环境变量指定数据库路径。

## 本地真实数据与公开发布

推荐保持一条清晰的双轨流程：

1. 日常功能开发在 `codex/public-release` 分支进行。
2. 本机页面显示的真实家庭数据只保存在 SQLite 数据库里，默认位置是 `%APPDATA%\house-planner\planner.db`，不进入 Git。
3. 代码里的默认值、测试样例和 README 只能使用空白模板、公开政策参数或合成示例。
4. 推送公开版前运行：

```powershell
.\scripts\push_public.ps1
```

这个脚本会依次执行隐私扫描、后端测试、前端构建，并把 `codex/public-release` 推送到 GitHub `main`。

如只想快速验证隐私扫描：

```powershell
python scripts/privacy_scan.py --ref HEAD
python scripts/privacy_scan.py
```

本仓库还提供 `.githooks/pre-push`，用于在推送前拦截以下情况：

- 从非 `codex/public-release` 分支推送到 `main`
- 推送不是基于公开 root commit 的历史
- 待推送内容包含数据库、构建产物、依赖目录或已知私人家庭信息片段

首次克隆或换机器后，可以启用本仓库的 Git hook：

```powershell
git config core.hooksPath .githooks
```

## 隐私说明

- 不要把本机 SQLite 数据库、导出方案、截图、`.env`、日志或个人配置文件提交到公开仓库。
- `.gitignore` 已排除常见数据库、构建产物、虚拟环境和环境变量文件。
- 公开仓库历史应从清理后的快照重新开始，避免旧提交中残留私人家庭数据。
