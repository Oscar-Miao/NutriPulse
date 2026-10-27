# NutriPulse · Flutter 本地 Demo

当前分支使用 Flutter 重写 Android 客户端，入口位于 `client/`。Python 本地服务端及数据库结构沿用原版本。原生 Android 基线保留在 Git 的 `main` 分支；当前工作在 `flutter-migration` 分支中。

第一次运行请看 [启动说明](启动说明.md)。版本上传与切换见 [Git 分支使用说明](Git分支使用说明.md)。迁移范围、验证方式和边界见 [Flutter 迁移验收](docs/Flutter迁移验收.md)。

## 启动

电脑服务窗口：

```powershell
cd E:\AndroidProject\AppDemo\server
python -m pip install -r requirements.txt
python run.py
```

启动 Android 模拟器后，在另一个 PowerShell 窗口运行：

```powershell
cd E:\AndroidProject\AppDemo
.\tools\run_flutter.ps1
```

这台电脑的 Flutter SDK 安装在 `tmp/flutter-sdk`，已由 `.gitignore` 排除。使用其他位置的 SDK 时，执行 `.\tools\run_flutter.ps1 -FlutterSdk C:\develop\flutter`。脚本会在 `client` 目录运行 Flutter，并应用这台电脑需要的 Gradle 临时目录配置。

如果 Flutter 已加入 PATH，也可直接在 `client` 目录执行 `flutter pub get` 和 `flutter run`。Android Studio 应打开 **client 文件夹**，并安装 Flutter / Dart 插件。

## 项目结构

```text
AppDemo/
├─ client/
│  ├─ lib/core/          API、状态、时间口径、原生平台通道
│  ├─ lib/ui/            配色、卡片、表单、待确认请求
│  ├─ lib/features/      饮食、健身、推荐对话、统计、个人配置
│  ├─ android/           Flutter Android 宿主与系统能力桥接
│  ├─ test/              Dart 单元与组件测试
│  └─ tool/              对隔离服务的接口验收工具、模拟 Agent
├─ server/               现有 Python API / SQLite / Agent 网关
├─ docs/                 迁移验收、原生版本历史验收资料
└─ tools/                Windows 启动脚本、文档工具
```

界面沿用 Stitch 风格：饮食绿 `#2ECC71`、健身橙红 `#FF5252`、蛋白蓝 `#3498DB`、脂肪黄 `#F1C40F`、冰蓝 `#00BEC5`、背景 `#F8F9FA`；白色卡片 16dp 圆角，阴影透明度 0.04。

## 功能

- 饮食：日历、热量与宏量营养看板、四餐账本、食品检索和常吃食物、计划转实际、编辑删除与撤销、饮水修正、资讯轮播；拍照/相册归一化、AI 识餐复核、本机加密照片草稿。
- 健身：运动项目/强度/分钟数估算、自定义消耗、次数组与计时组、自重和外部负重、RPE/RIR、休息倒计时、六套计划筛选与跟练、动作替代、训练后营养建议。
- 推荐：按服务端营养预算与偏好推荐、份量缩放、菜谱及替代食材、反馈、盲盒转盘、多轮 Agent 对话、确认后预记入饮食。
- 统计：日/周/月/年范围、摄入/消耗/BMR/净差复合图、宏量供能、体脂与周训练容量双轴、独立体重趋势、习惯记录、诊断与历史版本、PDF 导出。
- 个人：身体档案、测量、目标预览与确认、BMR/TDEE、过敏忌口与饮食预算、训练偏好、设备授权与历史管理、JSON 导出和确认清空、连接诊断及本地电脑配对。
- Android 系统接入使用 Flutter MethodChannel：相机/相册、文件导出、Keystore 加密存储、Health Connect 读取与撤销。原应用包名 `com.example.appdemo` 保留，可覆盖安装调试版。

所有 Agent 请求仍由联网的本地电脑服务发起；客户端只调用本地 API。真实 Agent 网关需按 [服务端说明](server/README.md) 配置。未配置时，识餐和对话返回明确错误；推荐和诊断的规则来源由服务端标注。

## 验证与构建

在 `client` 目录：

```powershell
flutter analyze
flutter test
flutter build apk --debug
```

APK：`client/build/app/outputs/flutter-apk/app-debug.apk`。构建产物不提交 Git。

真实接口验收工具只对独立测试数据库运行，步骤见 [迁移验收](docs/Flutter迁移验收.md)。服务端测试保持原有方式：在 `server` 执行 `python -m unittest discover -s tests -v`。

## 当前运行边界

当前配置和构建目标为 Android，最低 Android 8 / API 26。Health Connect 依赖设备系统、授权及其他运动应用先写入数据；不会直接读取 Apple Watch。尚未用真实穿戴设备或真实联网 Agent 验证结果质量。所有热量、营养与运动消耗均为估算。

个人数据仍存放在 `server/data/`，未加入 Git。Flutter 不迁移或覆盖服务端个人数据库。本机待重试写入和访问凭据加密保存；同一次保存重试保留原请求内容与去重键。被忽略的个人数据需要单独备份。
